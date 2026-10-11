"""Deterministic evidence, coverage, and grade gates."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from calendar import monthrange
from collections.abc import Iterable
from datetime import date
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from ozr.contamination import check_url, load_denylist
from ozr.contract import check_answer, check_release, to_record

# A line-break hyphen sits between two letters; the hyphen and the break are one token.
_LINE_HYPHEN = re.compile(r"(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])")
# Hyphens between letters are removed too, so a broken word and its closed form compare equal.
# Hyphens next to digits stay, so "Sec. 4-2" never matches "Sec. 42".
_WORD_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")
_WHITESPACE = re.compile(r"\s+")
_HYPHEN_MAP = str.maketrans({"\u2010": "-", "\u2011": "-"})
_GRADE_DROP = {"A": "B", "B": "C", "C": "C"}
_CONFIDENCE = {"A", "B", "C"}
_REVIEW = {"agree", "disputed", "single", "human_correction"}
_KINDS = {"table", "prose", "absence"}
TABLE_TEXT_MARKER = "\n\n=== reconstructed table text (from PDF rulings) ===\n"
OCR_TEXT_MARKER = "\n\n=== OCR text (tesseract; pages with no text layer; may misread) ===\n"
SOURCE_BOUNDARY = "\n\n␞\n\n"


class MissingSourceText(ValueError):
    """Raised when declared non-geometry source text has not been cached."""

    def __init__(self, source_ids: Iterable[str]) -> None:
        self.source_ids = tuple(sorted(source_ids))
        super().__init__(f"missing cached text for source ids: {', '.join(self.source_ids)}")


@lru_cache(maxsize=65536)
def canonical(text: str) -> str:
    """Return comparison text: hyphens closed, whitespace collapsed, case preserved."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")
    text = text.translate(_HYPHEN_MAP)
    text = _LINE_HYPHEN.sub("", text)
    text = _WORD_HYPHEN.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def contains(haystack: str, needle: str) -> bool:
    """Return whether the canonical needle is a non-empty substring of the haystack."""
    needle = canonical(needle)
    return bool(needle) and needle in canonical(haystack)


def text_layers(text: str) -> tuple[str, str, str]:
    """Split raw PDF, reconstructed table, and OCR text without crossing boundaries."""
    before_ocr, marker, ocr = text.partition(OCR_TEXT_MARKER)
    raw, table_marker, table = before_ocr.partition(TABLE_TEXT_MARKER)
    return raw, table if table_marker else "", ocr if marker else ""


def match_layer(text: str, needle: str) -> str | None:
    """Return the text layer containing a needle without crossing their boundary."""
    raw, table, ocr = text_layers(text)
    if contains(raw, needle):
        return "raw"
    if contains(table, needle):
        return "table"
    if contains(ocr, needle):
        return "ocr"
    return None


def _label_in(text: str, needle: str) -> bool:
    """Return whether a label occurs without adjoining letters or digits."""
    needle = canonical(needle)
    return bool(needle) and re.search(rf"(?<![^\W_]){re.escape(needle)}(?![^\W_])", canonical(text)) is not None


def _label_match_layer(text: str, needle: str) -> str | None:
    raw, table, ocr = text_layers(text)
    if _label_in(raw, needle):
        return "raw"
    if _label_in(table, needle):
        return "table"
    if _label_in(ocr, needle):
        return "ocr"
    return None


def matched_layers(cell: dict, text: str) -> dict[str, str]:
    """Record the layer supporting each applicable evidence field."""
    evidence = _mapping(cell.get("evidence"))
    fields: list[tuple[str, object]] = [("section", evidence.get("section"))]
    if evidence.get("kind") in {"prose", "absence"}:
        fields.append(("quote", evidence.get("quote")))
    fields.extend((field, evidence.get(field)) for field in ("row_label", "column_header"))
    definition = _mapping(cell.get("definition_evidence"))
    fields.extend(
        (field, definition.get(key))
        for field, key in (("definition_quote", "quote"), ("definition_section", "section"))
    )
    matched = {field: layer for field, value in fields if not _blank(value) and (layer := match_layer(text, value))}
    if evidence.get("kind") == "table" and (layer := table_grid_layer(cell, text)) is not None:
        matched["symbol"] = layer
    return matched


def _cell_key(cell: dict) -> str:
    jurisdiction_id = cell.get("jurisdiction_id", "")
    district_code = cell.get("district_code", "")
    use_class = cell.get("use_class", "")
    return f"{jurisdiction_id}/{district_code}/{use_class}"


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _blank(value: object) -> bool:
    return not isinstance(value, str) or canonical(value) == ""


def quote_errors(cell: dict, text: str) -> list[str]:
    """Return substring-gate errors for evidence and definition quotes."""
    key = _cell_key(cell)
    evidence = _mapping(cell.get("evidence"))
    errors: list[str] = []
    quote = evidence.get("quote")
    quote_missing = _blank(quote)
    if quote_missing:
        errors.append(f"{key}: no quote")
    kind = evidence.get("kind")
    if kind == "table":
        errors.extend(_table_label_errors(key, evidence, "" if quote_missing else quote, text))
    elif kind in {"prose", "absence"} and not quote_missing and match_layer(text, quote) is None:
        errors.append(f"{key}: quote not found in source")
    if "definition_evidence" in cell:
        errors.extend(_definition_quote_errors(key, cell.get("definition_evidence"), text))
    return errors


def _table_label_errors(key: str, evidence: dict, quote: str, text: str) -> list[str]:
    errors: list[str] = []
    for field, name in (("row_label", "row label"), ("column_header", "column header")):
        value = evidence.get(field)
        if _blank(value):
            errors.append(f"{key}: no {name}")
            continue
        if _label_match_layer(text, value) is None:
            errors.append(f"{key}: {name} not found in source")
        if quote and not _label_in(quote, value):
            errors.append(f"{key}: {name} not in quote")
    return errors


def _definition_quote_errors(key: str, definition: object, text: str) -> list[str]:
    quote = _mapping(definition).get("quote")
    if _blank(quote):
        return [f"{key}: definition evidence: no quote"]
    if match_layer(text, quote) is None:
        return [f"{key}: definition quote not found in source"]
    return []


def section_errors(cell: dict, text: str) -> list[str]:
    """Return errors when a cited section is empty or missing from the source."""
    key = _cell_key(cell)
    evidence = _mapping(cell.get("evidence"))
    errors = _one_section_errors(key, evidence.get("section"), text, "section", "no section")
    if "definition_evidence" in cell:
        definition = _mapping(cell.get("definition_evidence"))
        errors.extend(
            _one_section_errors(
                key,
                definition.get("section"),
                text,
                "definition section",
                "definition evidence: no section",
            )
        )
    return errors


def _one_section_errors(key: str, section: object, text: str, found_name: str, empty_name: str) -> list[str]:
    if _blank(section):
        return [f"{key}: {empty_name}"]
    if _label_match_layer(text, section) is None:
        return [f"{key}: {found_name} not found in source"]
    return []


def enum_errors(cell: dict, taxonomy: dict) -> list[str]:
    """Return errors for closed fields and the unlisted/absence pairing."""
    key = _cell_key(cell)
    evidence = _mapping(cell.get("evidence"))
    kind = evidence.get("kind")
    status = cell.get("status")
    class_ids = {item.get("id") for item in taxonomy.get("classes", []) if isinstance(item, dict)}
    statuses = {item.get("value") for item in taxonomy.get("statuses", []) if isinstance(item, dict)}
    errors: list[str] = []
    if cell.get("use_class") not in class_ids:
        errors.append(f"{key}: use_class not in taxonomy")
    if status not in statuses:
        errors.append(f"{key}: status not in taxonomy")
    if cell.get("confidence") not in _CONFIDENCE:
        errors.append(f"{key}: confidence not in A/B/C")
    if cell.get("review") not in _REVIEW:
        errors.append(f"{key}: review not in agree/disputed/single/human_correction")
    if kind not in _KINDS:
        errors.append(f"{key}: evidence kind not in table/prose/absence")
    if status == "unlisted" and kind != "absence":
        errors.append(f"{key}: unlisted requires evidence kind absence")
    if kind == "absence" and status != "unlisted":
        errors.append(f"{key}: absence evidence requires status unlisted")
    return errors


def absence_hits(text: str, use_class: str, taxonomy: dict) -> list[str]:
    """Return taxonomy terms of the class that occur in the code, in sorted order."""
    record = _class_record(taxonomy, use_class)
    if record is None:
        return []
    found = {term for term in _class_terms(record) if _term_in(text, term)}
    return sorted(found)


def _class_record(taxonomy: dict, use_class: str) -> dict | None:
    for item in taxonomy.get("classes", []):
        if isinstance(item, dict) and item.get("id") == use_class:
            return item
    return None


def _class_terms(record: dict) -> list[str]:
    terms: list[str] = []
    for field in ("synonyms", "definition_terms"):
        values = record.get(field) or []
        if isinstance(values, list):
            terms.extend(value for value in values if isinstance(value, str))
    return terms


@lru_cache(maxsize=65536)
def _term_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "").translate(_HYPHEN_MAP)
    text = _LINE_HYPHEN.sub("", text)
    return re.sub(r"[-\s]+", " ", text).strip()


def _term_pattern(term: str) -> re.Pattern[str] | None:
    needle = _term_text(term)
    if not needle:
        return None
    words = needle.split()
    last = re.escape(words[-1])
    suffix = r"(?:es|s)?"
    if len(words[-1]) >= 2 and words[-1][-1].lower() == "y" and words[-1][-2].lower() not in "aeiou":
        last = rf"(?:{last}(?:es|s)?|{re.escape(words[-1][:-1])}ies)"
        suffix = ""
    return re.compile(
        rf"\b{re.escape(' '.join(words[:-1]) + (' ' if len(words) > 1 else ''))}{last}{suffix}\b", re.IGNORECASE
    )


@lru_cache(maxsize=65536)
def _term_occurrences(text: str, term: str) -> tuple[tuple[int, int], ...]:
    pattern = _term_pattern(term)
    if pattern is None:
        return ()
    return tuple(match.span() for match in pattern.finditer(_term_text(text)))


def _term_in(haystack: str, term: str) -> bool:
    return bool(_term_occurrences(haystack, term))


def term_in(haystack: str, term: str) -> bool:
    """Return whether a taxonomy term occurs as a whole word."""
    return _term_in(haystack, term)


def absence_errors(cell: dict, text: str, taxonomy: dict, jurisdiction: dict) -> list[str]:
    """Return absence-gate errors for an unlisted cell."""
    if cell.get("status") != "unlisted":
        return []
    key = _cell_key(cell)
    explained = cell.get("absence_hits")
    entries = explained if isinstance(explained, list) else []
    errors = []
    for term in absence_hits(text, str(cell.get("use_class", "")), taxonomy):
        occurrences = _term_occurrences(text, term)
        explained_count = sum(
            any(_hit_explains(entry, term, text, occurrence) for entry in entries) for occurrence in occurrences
        )
        if explained_count != len(occurrences):
            errors.append(
                f"{key}: absence gate: '{term}' occurs {len(occurrences)} times in the code and "
                f"{len(occurrences) - explained_count} are not explained"
            )
    if jurisdiction.get("unlisted_rule") == "prohibited_by_default":
        errors.extend(_unlisted_rule_errors(key, jurisdiction.get("unlisted_rule_quote"), text))
    return errors


@lru_cache(maxsize=65536)
def _quote_spans(text: str, quote: str) -> tuple[tuple[int, int], ...]:
    """Return every span of a term-normalised quote in the term-normalised text."""
    needle = _term_text(quote)
    if not needle:
        return ()
    return tuple(match.span() for match in re.finditer(re.escape(needle), _term_text(text)))


def _hit_explains(entry: object, term: str, text: str, occurrence: tuple[int, int]) -> bool:
    record = _mapping(entry)
    quote = record.get("quote")
    entry_term = record.get("term")
    if not isinstance(entry_term, str) or _term_text(entry_term).casefold() != _term_text(term).casefold():
        return False
    if _blank(quote) or _blank(record.get("section")) or _blank(record.get("reason")):
        return False
    if _label_match_layer(text, record["section"]) is None:
        return False
    normalized_quote = _term_text(quote)
    term_spans = _term_occurrences(quote, term)
    # The quote must name the term and say something besides it: a bare term would "explain" every occurrence.
    if not any(re.search(r"[^\W_]", normalized_quote[:start] + normalized_quote[end:]) for start, end in term_spans):
        return False
    return any(start <= occurrence[0] and occurrence[1] <= end for start, end in _quote_spans(text, quote))


def _unlisted_rule_errors(key: str, quoted: object, text: str) -> list[str]:
    quote = _mapping(quoted).get("quote")
    if _blank(quote):
        return [f"{key}: no unlisted rule quote"]
    if match_layer(text, quote) is None:
        return [f"{key}: unlisted rule quote not found in source"]
    return []


def table_errors(cell: dict, text: str, taxonomy: dict, jurisdiction: dict) -> list[str]:
    """Return table quote, symbol-key, and reconstructed-grid errors."""
    evidence = _mapping(cell.get("evidence"))
    kind = evidence.get("kind")
    if kind in {"prose", "absence"}:
        quote = evidence.get("quote")
        entries = jurisdiction.get("table_key")
        if isinstance(quote, str) and isinstance(entries, list):
            normalized_quote = canonical(quote).casefold()
            for entry in entries:
                key_quote = _mapping(entry).get("quote")
                normalized_key = canonical(key_quote).casefold() if isinstance(key_quote, str) else ""
                if (
                    normalized_quote
                    and normalized_key
                    and (normalized_quote in normalized_key or normalized_key in normalized_quote)
                ):
                    return [
                        f"{_cell_key(cell)}: prose evidence quotes the table key; cite the table cell as table evidence"
                    ]
        return []
    if kind != "table":
        return []
    key = _cell_key(cell)
    row = evidence.get("row_label")
    column = evidence.get("column_header")
    symbol = evidence.get("symbol")
    quote = evidence.get("quote")
    if not all(isinstance(value, str) for value in (row, column, symbol, quote)):
        return [f"{key}: table evidence needs string row_label, column_header, symbol and quote"]
    errors: list[str] = []
    fields = quote.split("|")
    if len(fields) != 3 or [canonical(value) for value in fields] != [
        canonical(row),
        canonical(column),
        canonical(symbol),
    ]:
        errors.append(f"{key}: table quote is not '<row_label> | <column_header> | <symbol>'")
    if not _table_symbol_maps(symbol, cell.get("status"), taxonomy, jurisdiction, text):
        errors.append(
            f"{key}: table symbol '{symbol}' does not map to status '{cell.get('status')}' through the table key"
        )
    if not _column_binds_district(cell.get("district_code"), column, jurisdiction, text):
        errors.append(
            f"{key}: column header '{column}' is not the column for district '{cell.get('district_code')}' "
            "(no formatting match or quoted column alias)"
        )
    errors.extend(_table_grid_errors(key, row, column, symbol, text))
    return errors


def _table_symbol_maps(symbol: str, status: object, taxonomy: dict, jurisdiction: dict, text: str) -> bool:
    entries = jurisdiction.get("table_key")
    if isinstance(entries, list) and entries:
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("symbol"), str):
                continue
            if canonical(entry["symbol"]) != canonical(symbol) or entry.get("status") != status:
                continue
            quote = entry.get("quote")
            if isinstance(quote, str) and match_layer(text, quote) is not None:
                return True
        return False
    if not canonical(symbol):
        return False
    for item in taxonomy.get("statuses", []):
        if item.get("value") == status and canonical(symbol) in {
            canonical(form) for form in item.get("local_forms", [])
        }:
            return True
    return False


def _column_binds_district(district_code: object, column: str, jurisdiction: dict, text: str) -> bool:
    if not isinstance(district_code, str):
        return False
    if _formatting_equal(district_code, column):
        return True
    footnote = re.fullmatch(r"(?P<district>.+?)\s+\d{1,2}(?:\s*,\s*\d{1,2})*", column)
    if footnote and _formatting_equal(district_code, footnote["district"]):
        return True
    aliases = jurisdiction.get("column_aliases")
    if not isinstance(aliases, list):
        return False
    return any(
        isinstance(alias, dict)
        and alias.get("district_code") == district_code
        and isinstance(alias.get("column_header"), str)
        and canonical(alias["column_header"]).casefold() == canonical(column).casefold()
        and isinstance(alias.get("quote"), str)
        and match_layer(text, alias["quote"]) is not None
        for alias in aliases
    )


def _formatting_equal(left: str, right: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", canonical(left).casefold()) == re.sub(r"[^a-z0-9]", "", canonical(right).casefold())


@lru_cache(maxsize=16)
def _grid_rows(table: str) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Parse the reconstructed table layer once into comparable cell rows."""
    blocks: list[list[tuple[str, ...]]] = [[]]
    for line in table.splitlines():
        if line.startswith("[page "):
            blocks.append([])
        elif line.strip() and not line.startswith("[ocr engine:"):
            blocks[-1].append(tuple(canonical(cell).casefold() for cell in line.split(" | ")))
    return tuple(tuple(block) for block in blocks if block)


def _grid_values(row_label: str, column_header: str, table: str) -> list[str]:
    rows = _grid_rows(table)
    wanted_row, wanted_column = canonical(row_label).casefold(), canonical(column_header).casefold()
    values: list[str] = []
    for block in rows:
        matching = [row for row in block if wanted_row in row]
        has_data_row = any(
            any(value for index, value in enumerate(row) if index != row.index(wanted_row)) for row in matching
        )
        for row_index, row in enumerate(block):
            if wanted_row not in row:
                continue
            if has_data_row and not any(value for index, value in enumerate(row) if index != row.index(wanted_row)):
                continue
            for header_index in range(row_index - 1, -1, -1):
                header = block[header_index]
                if wanted_column not in header or wanted_row in header:
                    continue
                if any(len(candidate) != len(row) for candidate in block[header_index : row_index + 1]):
                    break
                values.append(row[header.index(wanted_column)])
                break
    return values


def table_grid_layer(cell: dict, text: str) -> str | None:
    """Return the first table layer that can place a table evidence cell."""
    evidence = _mapping(cell.get("evidence"))
    if evidence.get("kind") != "table":
        return None
    row, column = evidence.get("row_label"), evidence.get("column_header")
    if not isinstance(row, str) or not isinstance(column, str):
        return None
    _, table, ocr = text_layers(text)
    return next((name for name, layer in (("table", table), ("ocr", ocr)) if _grid_values(row, column, layer)), None)


def ocr_only(cell: dict, text: str) -> bool:
    """Return whether any applicable evidence field was matched only in OCR text."""
    return "ocr" in matched_layers(cell, text).values()


def _table_grid_errors(key: str, row_label: str, column_header: str, symbol: str, text: str) -> list[str]:
    _, table, ocr = text_layers(text)
    values = [*_grid_values(row_label, column_header, table), *_grid_values(row_label, column_header, ocr)]
    if not values:
        return [f"{key}: table grid: cannot place '{row_label}' under '{column_header}' in the reconstructed table"]
    expected = canonical(symbol).casefold()
    actual = set(values)
    if actual != {expected}:
        rendered = ", ".join("BLANK" if value == "" else value for value in sorted(actual))
        return [
            f"{key}: table grid: '{column_header}' column holds '{rendered}' on the '{row_label}' row, not '{symbol}'"
        ]
    return []


def coverage_errors(
    district_codes: list[str], cells: list[dict], use_classes: list[str], jurisdiction_id: str = ""
) -> list[str]:
    """Return duplicate, unknown-district, and missing-cell errors for one jurisdiction."""
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for cell in cells:
        key = (str(cell.get("jurisdiction_id", "")), str(cell.get("district_code", "")), str(cell.get("use_class", "")))
        if key in seen:
            errors.append(f"{key[0]}/{key[1]}/{key[2]}: duplicate cell")
        else:
            seen.add(key)
        if key[1] not in district_codes:
            errors.append(f"{key[0]}/{key[1]}/{key[2]}: unknown district")
    jurisdiction_id = jurisdiction_id or (str(cells[0].get("jurisdiction_id", "")) if cells else "")
    covered = {(key[1], key[2]) for key in seen}
    for district_code in district_codes:
        for use_class in use_classes:
            if (district_code, use_class) not in covered:
                errors.append(f"{jurisdiction_id}/{district_code}/{use_class}: missing cell")
    return errors


def add_months(d: date, months: int) -> date:
    """Return the date `months` calendar months from d, clamping the day."""
    index = d.month - 1 + months
    year_delta, month_index = divmod(index, 12)
    year = d.year + year_delta
    month = month_index + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def apply_grade_rules(
    cell: dict,
    today: date,
    stale_after_months: int = 12,
    pending_amendment: bool = False,
) -> dict:
    """Return a new cell with confidence capped and staleness applied."""
    graded = dict(cell)
    if graded.get("parcel_specific") is True and graded.get("confidence") in {"A", "B"}:
        graded["confidence"] = "C"
    checked = date.fromisoformat(cell["checked_at"])
    is_stale = pending_amendment or today > add_months(checked, stale_after_months)
    if is_stale:
        if cell.get("stale") is not True:
            graded["confidence"] = _GRADE_DROP.get(graded.get("confidence"), graded.get("confidence"))
        graded["stale"] = True
    else:
        graded["stale"] = False
    return graded


def cell_errors(
    cell: dict,
    text: str,
    taxonomy: dict,
    jurisdiction: dict,
    denylist: frozenset[str],
    *,
    absence_text: str | None = None,
) -> list[str]:
    """Return every cell gate error, including a banned or non-https source URL."""
    errors = [
        *enum_errors(cell, taxonomy),
        *quote_errors(cell, text),
        *section_errors(cell, text),
        *table_errors(cell, text, taxonomy, jurisdiction),
        *absence_errors(cell, absence_text if absence_text is not None else text, taxonomy, jurisdiction),
    ]
    key = _cell_key(cell)
    url = _mapping(cell.get("source")).get("url")
    if _blank(url):
        errors.append(f"{key}: no source url")
    else:
        errors.extend(f"{key}: {error}" for error in check_url(url, denylist))
    return errors


_ROOT = Path(__file__).resolve().parents[2]
_ITEM_SCHEMAS = {
    "cells.json": "record.schema.json",
    "jurisdictions.json": "jurisdiction.schema.json",
    "state_rules.json": "state_rule.schema.json",
}
_OBJECT_SCHEMAS = {
    "manifest.json": "manifest.schema.json",
    "sources.json": "sources.schema.json",
}


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(schema_name: str) -> Draft202012Validator:
    document = json.loads((_ROOT / "schema" / schema_name).read_text(encoding="utf-8"))
    return Draft202012Validator(document)


def _schema_messages(filename: str, schema_name: str, instance: object) -> list[str]:
    validator = _validator(schema_name)
    return [f"schema: {filename}: {error.message}" for error in validator.iter_errors(instance)]


def _schema_file_errors(filename: str, instance: object) -> list[str]:
    if filename in _OBJECT_SCHEMAS:
        return _schema_messages(filename, _OBJECT_SCHEMAS[filename], instance)
    if not isinstance(instance, list):
        return [f"schema: {filename}: expected an array"]
    schema_name = _ITEM_SCHEMAS[filename]
    errors: list[str] = []
    for item in instance:
        errors.extend(_schema_messages(filename, schema_name, item))
    return errors


def _cell_identity(cell: dict) -> tuple[object, object, object]:
    return (cell.get("jurisdiction_id"), cell.get("district_code"), cell.get("use_class"))


def _apply_cell_overrides(cells: list[dict], overrides: list[dict] | None) -> list[dict]:
    if not overrides:
        return cells
    index = {_cell_identity(cell): position for position, cell in enumerate(cells)}
    updated = list(cells)
    for override in overrides:
        key = _cell_identity(override)
        if key in index:
            updated[index[key]] = override
        else:
            index[key] = len(updated)
            updated.append(override)
    return updated


def _manifest_version(manifest: object) -> str:
    if not isinstance(manifest, dict):
        return ""
    version = manifest.get("version")
    return version if isinstance(version, str) else ""


def _contract_messages(manifest: object, cells: list[dict]) -> list[str]:
    errors = [f"contract: {error}" for error in check_release(manifest)]
    version = _manifest_version(manifest)
    for cell in cells:
        errors.extend(f"contract: {error}" for error in check_answer(to_record(cell, version)))
    return errors


def _hash_errors(release_dir: Path, manifest: object, skip_cells: bool) -> list[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        return []
    errors: list[str] = []
    others = manifest.get("other_files") if isinstance(manifest.get("other_files"), list) else []
    for entry in [*manifest["files"], *others]:
        if not isinstance(entry, dict):
            errors.append("hash: file entry is not an object")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or path == "":
            errors.append("hash: file path is missing")
            continue
        if skip_cells and path == "cells.json":
            continue
        target = release_dir / path
        if not target.is_file():
            errors.append(f"hash: {path}: file missing")
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            errors.append(f"hash: {path}: sha256 does not match")
    return errors


def _denylist_errors(manifest: object, denylist: frozenset[str]) -> list[str]:
    if not isinstance(manifest, dict):
        return ["denylist: manifest denylist does not match policy"]
    listed = manifest.get("denylist")
    if isinstance(listed, list) and all(isinstance(item, str) for item in listed) and set(listed) == set(denylist):
        return []
    return ["denylist: manifest denylist does not match policy"]


def _url_messages(label: str, record: dict, fields: tuple[str, ...], denylist: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        url = record.get(field)
        if not isinstance(url, str):
            continue
        errors.extend(f"{label}: {error}" for error in check_url(url, denylist))
    return errors


def _source_list(sources_doc: object) -> list[dict]:
    if not isinstance(sources_doc, dict) or not isinstance(sources_doc.get("sources"), list):
        return []
    return [item for item in sources_doc["sources"] if isinstance(item, dict)]


def _dicts(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _published(manifest: object) -> date | None:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("published"), str):
        return None
    try:
        return date.fromisoformat(manifest["published"])
    except ValueError:
        return None


def _stale_after(manifest: object) -> int | None:
    if not isinstance(manifest, dict):
        return None
    months = manifest.get("stale_after_months")
    if isinstance(months, int) and not isinstance(months, bool):
        return months
    return None


def _source_text(text_dir: Path, source_id: object, cache: dict[str, str]) -> str | None:
    if not isinstance(source_id, str) or source_id == "":
        return None
    if source_id not in cache:
        path = text_dir / f"{source_id}.txt"
        if not path.is_file():
            return None
        cache[source_id] = path.read_text(encoding="utf-8")
    return cache[source_id]


def jurisdiction_text(text_dir: Path, source_ids: Iterable[str], *, exempt: Iterable[str] = ()) -> str:
    """Return source texts in order, separated so evidence cannot span sources.

    Declared source text must be cached unless its id is exempt (for example, a GIS layer).
    """
    cache: dict[str, str] = {}
    exempt_ids = set(exempt)
    ids = [source_id for source_id in source_ids if isinstance(source_id, str)]
    missing = [
        source_id
        for source_id in ids
        if source_id not in exempt_ids and _source_text(text_dir, source_id, cache) is None
    ]
    if missing:
        raise MissingSourceText(missing)
    return SOURCE_BOUNDARY.join(
        text for source_id in ids if (text := _source_text(text_dir, source_id, cache)) is not None
    )


def superseded_errors(cell: dict, amendments: list[dict], sources: dict, jurisdiction: dict, text: str) -> list[str]:
    """Return adopted-amendment errors for cells citing a superseded source."""
    key = _cell_key(cell)
    source_id = _mapping(cell.get("source")).get("id")
    source = sources.get(source_id, {}) if isinstance(sources, dict) else {}
    cited_date = _iso_date(source.get("source_date")) or _iso_date(jurisdiction.get("code_version"))
    errors: list[str] = []
    for amendment in amendments:
        if (
            not isinstance(amendment, dict)
            or amendment.get("kind") != "adopted_text_amendment"
            or amendment.get("status") != "adopted"
        ):
            continue
        if amendment.get("jurisdiction_id") != cell.get("jurisdiction_id"):
            continue
        classes, districts = amendment.get("use_classes", []), amendment.get("districts", [])
        if not isinstance(classes, list) or not isinstance(districts, list):
            continue
        if ("*" not in classes and cell.get("use_class") not in classes) or (
            "*" not in districts and cell.get("district_code") not in districts
        ):
            continue
        dates = _mapping(amendment.get("dates"))
        effective = _iso_date(dates.get("effective")) or _iso_date(dates.get("adopted"))
        amendment_source = _mapping(amendment.get("source")).get("id")
        incorporated = amendment.get("incorporated_in", [])
        included = isinstance(incorporated, list) and any(
            isinstance(item, dict)
            and item.get("source_id") == source_id
            and isinstance(item.get("quote"), str)
            and match_layer(text, item["quote"]) is not None
            for item in incorporated
        )
        if source_id == amendment_source or included:
            continue
        if effective is None or cited_date is None or effective > cited_date:
            reference = amendment.get("reference")
            name = f"{amendment.get('id')} ({reference})" if reference else amendment.get("id")
            effective_text = effective.isoformat() if effective else "undated"
            cited_text = cited_date.isoformat() if cited_date else "undated"
            errors.append(
                f"superseded: {key}: adopted amendment {name} (effective {effective_text}) postdates cited source "
                f"{source_id} ({cited_text}) and touches {cell.get('use_class')} in {cell.get('district_code')}; "
                "the cell's evidence does not cite it"
            )
    return errors


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _grade_errors(cell: dict) -> list[str]:
    if cell.get("parcel_specific") is True and cell.get("confidence") != "C":
        return [f"{_cell_key(cell)}: parcel_specific confidence is C"]
    return []


def _staleness_errors(cell: dict, published: date, months: int) -> list[str]:
    checked_at = cell.get("checked_at")
    if not isinstance(checked_at, str):
        return []
    try:
        checked = date.fromisoformat(checked_at)
    except ValueError:
        return [f"staleness: {_cell_key(cell)}: checked_at is not a date"]
    if published > add_months(checked, months) and cell.get("stale") is not True:
        return [f"staleness: {_cell_key(cell)}: checked_at is more than {months} months before publication"]
    return []


def _preemption_errors(cell: dict, jurisdiction: dict, rules: list[dict]) -> list[str]:
    if "preemption" not in cell:
        return []
    preemption = cell.get("preemption")
    key = _cell_key(cell)
    if not isinstance(preemption, dict):
        return [f"preemption: {key}: preemption is not an object"]
    rule_id = preemption.get("state_rule_id")
    matches = [rule for rule in rules if rule.get("id") == rule_id]
    if len(matches) != 1:
        return [f"preemption: {key}: state rule {rule_id} does not resolve"]
    rule = matches[0]
    errors: list[str] = []
    if rule.get("use_class") != cell.get("use_class"):
        errors.append(f"preemption: {key}: state rule {rule_id} use_class does not match")
    if rule.get("effect") != preemption.get("effect"):
        errors.append(f"preemption: {key}: state rule {rule_id} effect does not match")
    if rule.get("state") != jurisdiction.get("state"):
        errors.append(f"preemption: {key}: state rule {rule_id} state does not match")
    return errors


def _one_cell_errors(
    cell: dict,
    text_dir: Path,
    taxonomy: dict,
    jurisdiction: dict,
    denylist: frozenset[str],
    published: date | None,
    months: int | None,
    rules: list[dict],
    sources: dict[object, dict],
    cache: dict[str, str],
    absence_text: str,
    amendments: list[dict] | None = None,
) -> list[str]:
    key = _cell_key(cell)
    source_id = _mapping(cell.get("source")).get("id")
    text = _source_text(text_dir, source_id, cache)
    errors: list[str] = []
    if text is None:
        errors.append(f"{key}: unknown source id {source_id}")
        text = ""
    registered = sources.get(source_id)
    if registered is None or registered.get("url") != _mapping(cell.get("source")).get("url"):
        errors.append(f"{key}: source {source_id} is not in sources.json with this url")
    errors.extend(cell_errors(cell, text, taxonomy, jurisdiction, denylist, absence_text=absence_text))
    if ocr_only(cell, text) and cell.get("confidence") != "C":
        errors.append(f"grade: {key}: evidence matched only in OCR text, confidence must be C")
    if cell.get("status") == "unlisted" and OCR_TEXT_MARKER in absence_text and cell.get("confidence") != "C":
        errors.append(f"grade: {key}: absence evidence over a code with an OCR layer, confidence must be C")
    errors.extend(_grade_errors(cell))
    if published is not None and months is not None:
        errors.extend(_staleness_errors(cell, published, months))
    errors.extend(_preemption_errors(cell, jurisdiction, rules))
    errors.extend(superseded_errors(cell, amendments or [], sources, jurisdiction, text))
    return errors


def _coverage_messages(
    jurisdictions: list[dict], cells: list[dict], class_ids: list[str], withheld: list[dict], root: Path
) -> list[str]:
    errors: list[str] = []
    published_keys = {_cell_key(cell) for cell in cells}
    withheld_by_key = {item.get("key"): item for item in withheld if isinstance(item.get("key"), str)}
    for key in sorted(published_keys & set(withheld_by_key)):
        errors.append(f"coverage: {key}: listed as withheld but published")
    for jurisdiction in jurisdictions:
        codes = [
            district.get("district_code")
            for district in _dicts(jurisdiction.get("districts"))
            if isinstance(district.get("district_code"), str)
        ]
        owned = [cell for cell in cells if cell.get("jurisdiction_id") == jurisdiction.get("jurisdiction_id")]
        for error in coverage_errors(codes, owned, class_ids, str(jurisdiction.get("jurisdiction_id", ""))):
            if not error.endswith(": missing cell"):
                errors.append(f"coverage: {error}")
                continue
            key = error.removesuffix(": missing cell")
            withheld_entry = withheld_by_key.get(key)
            if withheld_entry is None:
                errors.append(f"coverage: {error}")
                continue
            jid = str(jurisdiction.get("jurisdiction_id", ""))
            grade_path = root / "jurisdictions" / jid / "cells.withheld.json"
            grade_document = _read_json(grade_path) if grade_path.is_file() else {}
            grade_entries = grade_document.get("withheld", []) if isinstance(grade_document, dict) else []
            if any(
                isinstance(entry, dict)
                and entry.get("key") == key
                and entry.get("run_id") == withheld_entry.get("run_id")
                for entry in grade_entries
            ):
                continue
            errors.append(f"coverage: {key}: withheld without a matching grade failure record")
    return errors


def _state_rule_quote_errors(rules: list[dict], sources: list[dict], text_dir: Path) -> list[str]:
    by_url: dict[str, dict] = {}
    for source in sources:
        url = source.get("url")
        if isinstance(url, str):
            by_url.setdefault(url, source)
    errors: list[str] = []
    cache: dict[str, str] = {}
    for rule in rules:
        if rule.get("effect") == "none_found":
            continue
        rule_id = rule.get("id", "?")
        source = by_url.get(rule.get("url")) if isinstance(rule.get("url"), str) else None
        if source is None:
            errors.append(f"preemption: {rule_id}: quote source url does not match a source")
            continue
        text = _source_text(text_dir, source.get("source_id"), cache)
        quote = rule.get("quote")
        if text is None or not isinstance(quote, str) or not contains(text, quote):
            errors.append(f"preemption: {rule_id}: quote not found in source")
    return errors


def _amendment_quote_errors(amendments: list[dict], sources: dict[object, dict], text_dir: Path) -> list[str]:
    cache: dict[str, str] = {}
    errors: list[str] = []
    for amendment in amendments:
        amendment_id = amendment.get("id", "?")
        references = [_mapping(amendment.get("source"))]
        incorporated = amendment.get("incorporated_in", [])
        if isinstance(incorporated, list):
            references.extend(item for item in incorporated if isinstance(item, dict))
        for reference in references:
            source_id = reference.get("id", reference.get("source_id"))
            quote = amendment.get("quote") if reference is references[0] else reference.get("quote")
            text = _source_text(text_dir, source_id, cache)
            if text is None or not isinstance(quote, str) or match_layer(text, quote) is None:
                errors.append(f"amendment: {amendment_id}: quote not found in source {source_id}")
    return errors


def release_errors(
    release_dir: Path,
    text_dir: Path,
    policy_denylist: frozenset[str] | None = None,
    cell_overrides: list[dict] | None = None,
    *,
    root: Path | None = None,
) -> list[str]:
    """Return schema, contract, hash, coverage, and evidence errors for one release."""
    denylist = load_denylist() if policy_denylist is None else policy_denylist
    manifest = _read_json(release_dir / "manifest.json")
    cells_doc = _read_json(release_dir / "cells.json")
    jurisdictions_doc = _read_json(release_dir / "jurisdictions.json")
    sources_doc = _read_json(release_dir / "sources.json")
    state_rules_doc = _read_json(release_dir / "state_rules.json")
    amendments_doc = _read_json(release_dir / "amendments.json") if (release_dir / "amendments.json").is_file() else []
    withheld_doc = _read_json(release_dir / "withheld.json") if (release_dir / "withheld.json").is_file() else []
    cells = _apply_cell_overrides(_dicts(cells_doc), cell_overrides)
    jurisdictions = _dicts(jurisdictions_doc)
    rules = _dicts(state_rules_doc)
    amendments = _dicts(amendments_doc)
    withheld = _dicts(withheld_doc)
    root = _ROOT if root is None else root
    sources = _source_list(sources_doc)
    taxonomy = _read_json(_ROOT / "taxonomy" / "v1.json")
    if not isinstance(taxonomy, dict):
        taxonomy = {}
    class_ids = [item["id"] for item in _dicts(taxonomy.get("classes")) if isinstance(item.get("id"), str)]
    by_jurisdiction = {item.get("jurisdiction_id"): item for item in jurisdictions}
    by_source = {item.get("source_id"): item for item in sources}
    errors = [
        *_schema_file_errors("manifest.json", manifest),
        *_schema_file_errors("cells.json", cells),
        *_schema_file_errors("jurisdictions.json", jurisdictions_doc),
        *_schema_file_errors("sources.json", sources_doc),
        *_schema_file_errors("state_rules.json", state_rules_doc),
        *_contract_messages(manifest, cells),
        *_hash_errors(release_dir, manifest, cell_overrides is not None),
        *_denylist_errors(manifest, denylist),
    ]
    manifest_files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if (release_dir / "withheld.json").is_file() and not any(
        isinstance(entry, dict) and entry.get("path") == "withheld.json" for entry in manifest_files
    ):
        errors.append("withheld: withheld.json is not listed in the manifest files")
    for source in sources:
        label = str(source.get("source_id", "source"))
        errors.extend(_url_messages(label, source, ("url", "final_url"), denylist))
    for rule in rules:
        errors.extend(_url_messages(str(rule.get("id", "state rule")), rule, ("url",), denylist))
    published = _published(manifest)
    months = _stale_after(manifest)
    cache: dict[str, str] = {}
    jurisdiction_texts: dict[str, str] = {}
    for jurisdiction in jurisdictions:
        jid = str(jurisdiction.get("jurisdiction_id", ""))
        source_ids = [source for source in jurisdiction.get("sources", []) if isinstance(source, str)]
        exempt = {source_id for source_id in source_ids if by_source.get(source_id, {}).get("kind") == "gis_layer"}
        try:
            jurisdiction_texts[jid] = jurisdiction_text(text_dir, source_ids, exempt=exempt)
        except MissingSourceText as error:
            errors.append(f"text: {jid}: {error}")
            jurisdiction_texts[jid] = jurisdiction_text(text_dir, source_ids, exempt=exempt | set(error.source_ids))
    for cell in cells:
        jurisdiction = by_jurisdiction.get(cell.get("jurisdiction_id"), {})
        errors.extend(
            _one_cell_errors(
                cell,
                text_dir,
                taxonomy,
                jurisdiction,
                denylist,
                published,
                months,
                rules,
                by_source,
                cache,
                jurisdiction_texts.get(str(jurisdiction.get("jurisdiction_id", "")), ""),
                amendments,
            )
        )
    errors.extend(_coverage_messages(jurisdictions, cells, class_ids, withheld, root))
    errors.extend(_state_rule_quote_errors(rules, sources, text_dir))
    errors.extend(_amendment_quote_errors(amendments, by_source, text_dir))
    return errors
