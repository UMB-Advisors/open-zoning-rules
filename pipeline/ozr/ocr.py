"""Deterministic OCR for scanned PDF pages with ruled tables."""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
from functools import lru_cache

import numpy as np
import pypdfium2
from PIL import Image, ImageOps

IMAGE_ONLY_MAX_CHARS = 20


def is_image_only(text: str, image_count: int) -> bool:
    """Return whether a page has an image but no meaningful text layer."""
    return image_count >= 1 and len(re.sub(r"\s+", "", text)) <= IMAGE_ONLY_MAX_CHARS


@lru_cache(maxsize=1)
def engine_header() -> str:
    """Return the fixed OCR engine and rendering configuration."""
    version = subprocess.run(["tesseract", "--version"], capture_output=True, check=True, text=True).stdout.splitlines()
    languages = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, check=True, text=True
    ).stdout.splitlines()
    match = re.search(r'"(.+?)"', languages[0])
    if match is None:
        raise RuntimeError("cannot find tesseract tessdata directory")
    trained = os.path.join(match.group(1), "eng.traineddata")
    with open(trained, "rb") as file:
        digest = hashlib.sha256(file.read()).hexdigest()
    pdfium = str(pypdfium2.PDFIUM_INFO) if hasattr(pypdfium2, "PDFIUM_INFO") else str(pypdfium2.V_PDFIUM)
    return (
        f"[ocr engine: {version[0]}; {version[1]}; eng.traineddata sha256={digest}; pdfium={pdfium}; "
        "render=300dpi; threshold=160/170; psm=6,7; OMP_THREAD_LIMIT=1; --oem 1 -l eng]"
    )


def _tesseract(image: Image.Image, psm: str) -> str:
    """OCR one prepared image through tesseract's stdin/stdout interface and return its raw output."""
    encoded = io.BytesIO()
    image.save(encoded, "PNG")
    environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--oem", "1", "--psm", psm, "-l", "eng"],
        input=encoded.getvalue(),
        capture_output=True,
        env=environment,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode(errors="replace")


def _longest_runs(values: np.ndarray) -> np.ndarray:
    """Return each row's longest consecutive true run."""
    result = np.zeros(values.shape[0], dtype=int)
    for index, row in enumerate(values):
        edges = np.flatnonzero(np.diff(np.pad(row.astype(np.int8), (1, 1))))
        result[index] = max((edges[point + 1] - edges[point] for point in range(0, len(edges), 2)), default=0)
    return result


def _clusters(indices: np.ndarray) -> list[tuple[int, int]]:
    if not len(indices):
        return []
    groups: list[tuple[int, int]] = []
    first = previous = int(indices[0])
    for index in indices[1:]:
        current = int(index)
        if current > previous + 2:
            groups.append((first, previous))
            first = current
        previous = current
    groups.append((first, previous))
    return groups


def grid_rules(image: Image.Image) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return clustered horizontal and vertical rules, or empty lists when no grid exists."""
    dark = np.asarray(image.convert("L")) < 160
    horizontal = _clusters(np.flatnonzero(_longest_runs(dark) >= 0.4 * dark.shape[1]))
    if len(horizontal) < 2:
        return [], []
    top, bottom = horizontal[0][0], horizontal[-1][1]
    band = dark[top : bottom + 1, :].T
    vertical = _clusters(np.flatnonzero(_longest_runs(band) >= 0.3 * (bottom - top)))
    return (horizontal, vertical) if len(vertical) >= 2 else ([], [])


def _cell_text(image: Image.Image, first_column: bool) -> str:
    if np.count_nonzero(np.asarray(image.convert("L")) < 160) < 15:
        return ""
    scale, psm = (2, "6") if first_column else (3, "7")
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
    if not first_column:
        image = image.point(lambda value: 0 if value < 170 else 255)
    return " ".join(_tesseract(ImageOps.expand(image, border=20, fill="white"), psm).split())


def _grid_text(image: Image.Image) -> str | None:
    horizontal, vertical = grid_rules(image)
    if not horizontal:
        return None
    rows: list[str] = []
    for top_rule, bottom_rule in zip(horizontal, horizontal[1:], strict=False):
        cells = []
        for index, (left_rule, right_rule) in enumerate(zip(vertical, vertical[1:], strict=False)):
            box = (left_rule[1] + 4, top_rule[1] + 4, right_rule[0] - 3, bottom_rule[0] - 3)
            crop = image.crop(box) if box[2] > box[0] and box[3] > box[1] else Image.new("L", (1, 1), "white")
            cells.append(_cell_text(crop, index == 0))
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _render(data: bytes, page_number: int) -> Image.Image:
    document = pypdfium2.PdfDocument(data)
    try:
        page = document[page_number - 1]
        try:
            bitmap = page.render(scale=300 / 72)
            try:
                return bitmap.to_pil().convert("L")
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def ocr_page(data: bytes, page_number: int) -> str:
    """Return deterministic grid-aware OCR text for one one-based PDF page."""
    image = _render(data, page_number)
    grid = _grid_text(image)
    if grid is not None:
        return grid
    return "\n".join(line.strip() for line in _tesseract(image, "6").splitlines() if line.strip())
