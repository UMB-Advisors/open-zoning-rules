"""Focused Z09 OCR, manual-import, and OCR-layer regression tests."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from ozr import fetch
from ozr.contamination import load_denylist
from ozr.gates import (
    OCR_TEXT_MARKER,
    TABLE_TEXT_MARKER,
    _one_cell_errors,
    _table_grid_errors,
    match_layer,
    matched_layers,
    text_layers,
)
from ozr.grade import grade_jurisdiction
from ozr.ocr import grid_rules, is_image_only, ocr_page
from ozr.segment import segment_jurisdiction
from pdfgen import make_pdf
from PIL import Image, ImageDraw, ImageFont


def _source(root, source_id: str = "us-00000-analyst") -> dict:
    document = json.loads((root / "jurisdictions" / "us-00000" / "sources.json").read_text())
    return next(source for source in document["sources"] if source["source_id"] == source_id)


def _manual(root, data: bytes, extension: str = "pdf") -> tuple[dict, str]:
    source = _source(root)
    digest = hashlib.sha256(data).hexdigest()
    source["sha256"] = digest
    path = root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    next(item for item in document["sources"] if item["source_id"] == source["source_id"])["sha256"] = digest
    path.write_text(json.dumps(document))
    manual = root / "cache" / "manual" / "us-00000"
    manual.mkdir(parents=True)
    (manual / f"{digest}.{extension}").write_bytes(data)
    return source, digest


def test_manual_fetch_imports_verified_bytes(tiny_root):
    _, digest = _manual(tiny_root, b"manual ordinance")
    calls: list[str] = []
    result = fetch.fetch_jurisdiction(tiny_root, "us-00000", lambda url: calls.append(url) or (url, b"law"))
    assert result[1] == {"source_id": "us-00000-analyst", "status": "imported"}
    assert (tiny_root / "cache" / digest).read_bytes() == b"manual ordinance"
    assert calls == ["https://planning.example.org/zoning/ordinance.pdf"]


def test_manual_fetch_rejects_tampered_bytes(tiny_root):
    _, digest = _manual(tiny_root, b"expected")
    manual = tiny_root / "cache" / "manual" / "us-00000" / f"{digest}.pdf"
    manual.write_bytes(b"tampered")
    result = fetch.fetch_jurisdiction(tiny_root, "us-00000")
    assert result[1]["status"] == "error"
    assert not (tiny_root / "cache" / digest).exists()


def test_manual_fetch_refuses_non_primary_host(tiny_root):
    source, _ = _manual(tiny_root, b"manual")
    source["url"] = "https://other.example.org/code.pdf"
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    next(item for item in document["sources"] if item["source_id"] == source["source_id"])["url"] = source["url"]
    path.write_text(json.dumps(document))
    assert fetch.fetch_jurisdiction(tiny_root, "us-00000")[1]["status"] == "refused"


def test_manual_fetch_without_file_stays_skipped(tiny_root):
    assert fetch.fetch_jurisdiction(tiny_root, "us-00000")[1] == {
        "source_id": "us-00000-analyst",
        "status": "skipped",
        "reason": "analyst_fetch",
    }


def _image_table_pdf() -> bytes:
    image = Image.new("L", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for x in (40, 520, 700, 860):
        draw.line((x, 40, x, 500), fill="black", width=5)
    for y in (40, 180, 340, 500):
        draw.line((40, y, 860, y), fill="black", width=5)
    draw.text((70, 80), "Data Center", fill="black", font=font)
    draw.text((550, 80), "BP", fill="black", font=font)
    draw.text((90, 220), "Warehouse", fill="black", font=font)
    draw.text((575, 220), "P", fill="black", font=font)
    draw.text((575, 380), "P", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, "PDF", resolution=150)
    return output.getvalue()


def test_image_only_detection_and_grid_rules():
    assert is_image_only("III - 9", 1)
    assert not is_image_only("III - 9", 0)
    assert not is_image_only("x" * 197, 2)
    image = Image.new("L", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    for x in (10, 100, 190):
        draw.line((x, 10, x, 110), fill="black", width=2)
    for y in (10, 60, 110):
        draw.line((10, y, 190, y), fill="black", width=2)
    horizontal, vertical = grid_rules(image)
    assert len(horizontal) == 3
    assert len(vertical) == 3


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is required")
def test_ocr_page_reads_image_table_grid():
    text = ocr_page(_image_table_pdf(), 1)
    assert "Data" in text and "Center" in text and "P" in text
    assert " | " in text


def test_ocr_layers_do_not_cross_boundaries():
    text = "raw-end" + OCR_TEXT_MARKER + "ocr-start"
    assert text_layers(text) == ("raw-end", "", "ocr-start")
    assert match_layer(text, "raw-end ocr-start") is None
    text = "raw" + TABLE_TEXT_MARKER + "table-end" + OCR_TEXT_MARKER + "ocr-start"
    assert match_layer(text, "table-end ocr-start") is None
    assert match_layer(text, "ocr-start") == "ocr"


def test_text_pdf_without_images_is_byte_identical(tiny_root):
    data = make_pdf([["Zoning districts are hereby established: I-1 Light Industrial"]])
    digest = hashlib.sha256(data).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(data)
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    document["sources"] = [document["sources"][0]]
    document["sources"][0]["sha256"] = digest
    path.write_text(json.dumps(document))
    segment_jurisdiction(tiny_root, "us-00000")
    assert (tiny_root / "cache" / "text" / "us-00000-zo.txt").read_text() == (
        "Zoning districts are hereby established: I-1 Light Industrial"
    )


def _table_cell(symbol: str = "P") -> dict:
    return {
        "evidence": {
            "kind": "table",
            "row_label": "Data Center",
            "column_header": "BP",
            "symbol": symbol,
        }
    }


def test_ocr_grid_is_used_only_when_table_grid_cannot_place_cell():
    ocr = "[ocr engine: test]\n[page 1]\nUse | BP\nData Center | P"
    text = "raw" + TABLE_TEXT_MARKER + "Use | BP\nData Center | SE" + OCR_TEXT_MARKER + ocr
    cell = _table_cell()
    assert _table_grid_errors("key", "Data Center", "BP", "SE", text) == []
    assert _table_grid_errors("key", "Data Center", "BP", "P", text)
    only_ocr = "raw" + OCR_TEXT_MARKER + ocr
    assert _table_grid_errors("key", "Data Center", "BP", "P", only_ocr) == []
    assert _table_grid_errors("key", "Data Center", "BP", "SE", only_ocr)
    assert matched_layers(cell, only_ocr)["symbol"] == "ocr"


def _release_cell() -> dict:
    cells = json.loads((Path(__file__).parent / "fixtures" / "release" / "cells.json").read_text())
    return next(cell for cell in cells if cell["use_class"] == "warehouse_distribution")


def _ocr_source_text() -> str:
    return OCR_TEXT_MARKER + "[ocr engine: test]\n[page 1]\nSec. 4-2\nUse | I-1 Light Industrial\nWarehouse | P"


def test_ocr_only_evidence_is_capped_to_grade_c(tiny_root):
    base = tiny_root / "jurisdictions" / "us-00000"
    cell = _release_cell()
    for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json"):
        (base / name).write_text(json.dumps({"cells": [cell], "rejected": [], "missing": []}))
    text_path = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    text_path.parent.mkdir(parents=True)
    text_path.write_text(_ocr_source_text())
    grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")
    published = json.loads((base / "cells.json").read_text())
    assert published[0]["review"] == "agree"
    assert published[0]["confidence"] == "C"


def test_release_cell_check_requires_c_for_ocr_only_evidence(tiny_root):
    cell = _release_cell()
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "us-00000-zo.txt").write_text(_ocr_source_text())
    jurisdiction = json.loads((tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json").read_text())
    source = _source(tiny_root, "us-00000-zo")
    taxonomy = json.loads((tiny_root / "taxonomy" / "v1.json").read_text())
    denied = load_denylist(tiny_root / "policy" / "denylist.txt")
    cell["confidence"] = "B"
    errors = _one_cell_errors(
        cell, text_dir, taxonomy, jurisdiction, denied, None, None, [], {source["source_id"]: source}, {}, ""
    )
    assert any("evidence matched only in OCR text" in error for error in errors)
    cell["confidence"] = "C"
    errors = _one_cell_errors(
        cell, text_dir, taxonomy, jurisdiction, denied, None, None, [], {source["source_id"]: source}, {}, ""
    )
    assert not any("evidence matched only in OCR text" in error for error in errors)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is required")
def test_segment_adds_marked_ocr_layer_for_image_only_page(tiny_root):
    data = _image_table_pdf()
    digest = hashlib.sha256(data).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(data)
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    document["sources"] = [document["sources"][0]]
    document["sources"][0]["sha256"] = digest
    path.write_text(json.dumps(document))
    manifest = segment_jurisdiction(tiny_root, "us-00000")
    text = (tiny_root / "cache" / "text" / "us-00000-zo.txt").read_text()
    raw, table, ocr = text_layers(text)
    assert manifest["sources"][0]["ocr_pages"] == [1]
    assert raw.strip() == "" and table == ""
    assert ocr.startswith("[ocr engine: tesseract ")
    assert "[page 1]\n" in ocr and " | " in ocr
