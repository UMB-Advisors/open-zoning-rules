"""Turn cached primary-source bytes into deterministic text and model segments."""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pdfplumber
import pypdfium2

from ozr.common import cache_dir, read_json, segment_dir, text_path, write_json
from ozr.gates import TABLE_TEXT_MARKER, term_in

USE_TABLE_RE = re.compile(
    r"(?:table(?:\s+\d+(?:-\d+)*)?(?:\s+table)?\s+of (?:(?:permitted|principal|allowed) )?uses|"
    r"use table|schedule of (?:district )?"
    r"(?:uses|regulations)|(land )?use matrix|permitted uses|permissible uses|uses permitted)",
    re.IGNORECASE,
)
DEFINITIONS_RE = re.compile(r"\bdefinitions\b", re.IGNORECASE)
NOT_LISTED_RE = re.compile(
    r"(?:uses? not (?:specifically |expressly )?(?:listed|permitted|named|mentioned)|"
    r"any use not (?:listed|shown)|not listed (?:in|on) (?:the|this) (?:table|schedule))",
    re.IGNORECASE,
)
DISTRICT_LIST_RE = re.compile(r"(?:districts? (?:are|is) (?:hereby )?established|zoning districts)", re.IGNORECASE)
# Case-sensitive: table symbols are capitals, and a lower-case "s" or "c" in prose is not one.
SYMBOL_RE = re.compile(r"(?<!\w)(?:P|C|S|SE|SUP|CU|X|PS|P\*)(?!\w)")


class _TextParser(HTMLParser):
    """Small HTML-to-text parser for primary source pages."""

    _BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def cell_text(value: str | None) -> str:
    """Flatten a PDF table cell without breaking hyphenated fragments."""
    if value is None:
        return ""
    fragments = [re.sub(r"\s+", " ", fragment).strip() for fragment in value.splitlines()]
    fragments = [fragment for fragment in fragments if fragment]
    text = ""
    for fragment in fragments:
        separator = "" if not text or text.endswith("-") or fragment.startswith("-") else " "
        text += separator + fragment
    return text


def table_rows(table: list[list[str | None]]) -> list[str]:
    """Render non-empty extracted table rows as deterministic pipe-delimited text."""
    rows: list[str] = []
    for row in table:
        cells = [cell_text(value) for value in row if value is not None]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def pdf_pages(data: bytes) -> tuple[list[str], list[str]]:
    """Extract raw and ruling-reconstructed table text from each PDF page."""
    raw_pages: list[str] = []
    table_pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            try:
                raw_pages.append(page.extract_text() or "")
                rules = list(page.lines) + [rect for rect in page.rects if min(rect["width"], rect["height"]) <= 2]
                horizontal = [rule for rule in rules if rule["width"] >= rule["height"]]
                vertical = [rule for rule in rules if rule["width"] < rule["height"]]
                if not horizontal or not vertical:
                    table_pages.append("")
                    continue
                settings = {
                    "vertical_strategy": "explicit",
                    "horizontal_strategy": "explicit",
                    "explicit_vertical_lines": vertical,
                    "explicit_horizontal_lines": horizontal,
                }
                table_blocks: list[str] = []
                for table in page.extract_tables(settings):
                    rows = table_rows(table)
                    if rows:
                        table_blocks.append("\n".join(rows))
                table_pages.append("\n\n".join(table_blocks))
            finally:
                page.close()
    return raw_pages, table_pages


def page_texts(data: bytes) -> list[str]:
    """Extract one text string per PDF page, or one page from HTML/plain text."""
    if data.startswith(b"%PDF"):
        return pdf_pages(data)[0]
    parser = _TextParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    return [re.sub(r"\n{2,}", "\n", unescape("".join(parser.parts))).strip()]


def _relative_cache_path(path: Path) -> str:
    cache = next(parent for parent in (path, *path.parents) if parent.name == "cache")
    return str(path.relative_to(cache))


def render_pages(data: bytes, pages: list[int], out_dir: Path, source_id: str = "source") -> list[dict]:
    """Render selected one-based PDF pages as PNGs below a segment directory."""
    if not data.startswith(b"%PDF"):
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    document = pypdfium2.PdfDocument(data)
    images: list[dict] = []
    try:
        for page_number in pages:
            page = document[page_number - 1]
            try:
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
                path = out_dir / f"{source_id}-p{page_number}.png"
                image.save(path, "PNG")
                bitmap.close()
            finally:
                page.close()
            images.append(
                {
                    "page": page_number,
                    "path": _relative_cache_path(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    finally:
        document.close()
    return images


def _terms(taxonomy: dict) -> list[str]:
    values: list[str] = []
    for item in taxonomy.get("classes", []):
        if isinstance(item, dict):
            for field in ("synonyms", "definition_terms"):
                entries = item.get(field, [])
                if isinstance(entries, list):
                    values.extend(entry for entry in entries if isinstance(entry, str))
    return values


def _has_code(text: str, code: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(code)}(?!\w)", text, re.IGNORECASE) is not None


def _located_pages(pages: list[str], district_codes: list[str], taxonomy: dict) -> dict[str, list[int]]:
    located = {"use_table": [], "definitions": [], "not_listed": [], "district_list": []}
    terms = _terms(taxonomy)
    for number, page in enumerate(pages, 1):
        codes = sum(_has_code(page, code) for code in district_codes)
        has_use_heading = USE_TABLE_RE.search(page) is not None
        if has_use_heading or (len(SYMBOL_RE.findall(page)) >= 15 and codes >= 2):
            located["use_table"].append(number)
        if has_use_heading and number < len(pages):
            located["use_table"].append(number + 1)
        if DEFINITIONS_RE.search(page) and any(term_in(page, term) for term in terms):
            located["definitions"].append(number)
        if NOT_LISTED_RE.search(page):
            located["not_listed"].append(number)
        if DISTRICT_LIST_RE.search(page) or (len(district_codes) >= 2 and codes * 2 >= len(district_codes)):
            located["district_list"].append(number)
    return {kind: sorted(set(page_numbers)) for kind, page_numbers in located.items()}


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def segment_jurisdiction(root: Path, jid: str) -> dict:
    """Create deterministic source text and target segments for one jurisdiction."""
    jurisdiction = read_json(root / "jurisdictions" / jid / "jurisdiction.json")
    sources_document = read_json(root / "jurisdictions" / jid / "sources.json")
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    if not isinstance(jurisdiction, dict) or not isinstance(sources_document, dict) or not isinstance(taxonomy, dict):
        raise ValueError(f"invalid jurisdiction inputs: {jid}")
    district_codes = [item["district_code"] for item in jurisdiction.get("districts", []) if isinstance(item, dict)]
    manifest_sources: list[dict] = []
    segments: list[dict] = []
    missing_bytes: list[str] = []
    found: set[str] = set()
    for source in sources_document.get("sources", []):
        if not isinstance(source, dict) or source.get("kind") not in {"ordinance", "amendment"}:
            continue
        source_id = source.get("source_id")
        digest = source.get("sha256")
        if not isinstance(source_id, str) or not isinstance(digest, str) or not (cache_dir(root) / digest).is_file():
            if isinstance(source_id, str):
                missing_bytes.append(source_id)
            continue
        data = (cache_dir(root) / digest).read_bytes()
        if data.startswith(b"%PDF"):
            pages, page_tables = pdf_pages(data)
        else:
            pages, page_tables = page_texts(data), []
        full_text = "\n\n".join(pages)
        if any(page_tables):
            table_blocks = [
                f"[page {number}]\n{table_text}" for number, table_text in enumerate(page_tables, 1) if table_text
            ]
            full_text += TABLE_TEXT_MARKER + "\n\n".join(table_blocks)
        full_sha = _write_text(text_path(root, source_id), full_text)
        manifest_sources.append(
            {
                "source_id": source_id,
                "sha256": digest,
                "pages": len(pages),
                "tables": sum(bool(table_text) for table_text in page_tables),
                "text_sha256": full_sha,
            }
        )
        locations = _located_pages(pages, district_codes, taxonomy)
        for kind, page_numbers in locations.items():
            if not page_numbers:
                continue
            found.add(kind)
            page_blocks = []
            for number in page_numbers:
                page_text = f"=== {source_id} page {number} ===\n{pages[number - 1]}"
                if kind == "use_table" and page_tables and page_tables[number - 1]:
                    page_text += f"\n\n[reconstructed table text]\n{page_tables[number - 1]}"
                page_blocks.append(page_text)
            text = "\n\n".join(page_blocks)
            path = segment_dir(root, jid) / f"{kind}-{source_id}.txt"
            text_sha = _write_text(path, text)
            images = render_pages(data, page_numbers, segment_dir(root, jid), source_id) if kind == "use_table" else []
            segments.append(
                {
                    "kind": kind,
                    "source_id": source_id,
                    "pages": page_numbers,
                    "text": _relative_cache_path(path),
                    "text_sha256": text_sha,
                    "images": images,
                }
            )
    manifest = {
        "jurisdiction_id": jid,
        "sources": manifest_sources,
        "segments": segments,
        "missing": [kind for kind in ("use_table", "definitions", "not_listed", "district_list") if kind not in found],
        "missing_bytes": missing_bytes,
    }
    write_json(root / "jurisdictions" / jid / "segments.json", manifest)
    return manifest


def segment_state_rules(root: Path) -> None:
    """Write full text for cached statute sources without creating model segments."""
    path = root / "state_rules" / "sources.json"
    if not path.exists():
        return
    document = read_json(path)
    if not isinstance(document, dict):
        return
    for source in document.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id, digest = source.get("source_id"), source.get("sha256")
        cache_path = cache_dir(root) / digest if isinstance(digest, str) else None
        if isinstance(source_id, str) and cache_path is not None and cache_path.is_file():
            _write_text(text_path(root, source_id), "\n\n".join(page_texts(cache_path.read_bytes())))


def load_segments(root: Path, jid: str) -> list[dict]:
    """Load a manifest's segments with cached text and absolute image paths."""
    manifest = read_json(root / "jurisdictions" / jid / "segments.json")
    if not isinstance(manifest, dict):
        return []
    loaded: list[dict] = []
    for segment in manifest.get("segments", []):
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            continue
        record = dict(segment)
        record["text"] = (cache_dir(root) / segment["text"]).read_text(encoding="utf-8")
        record["images"] = [
            {**image, "path": str((cache_dir(root) / image["path"]).resolve())}
            for image in segment.get("images", [])
            if isinstance(image, dict) and isinstance(image.get("path"), str)
        ]
        loaded.append(record)
    return loaded


def cli(args: argparse.Namespace) -> int:
    """Run segmentation selected by the shared command-line parser."""
    for jid in args.jurisdiction_ids:
        manifest = segment_jurisdiction(args.root, jid)
        print(f"{jid}: {len(manifest['segments'])} segments")
    if args.state_rules:
        segment_state_rules(args.root)
    return 0
