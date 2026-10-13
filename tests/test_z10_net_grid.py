"""Regression coverage for Z10 source, grid, and measurement gates."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from ozr.contamination import check_url, load_denylist
from ozr.gates import OCR_TEXT_MARKER, TABLE_TEXT_MARKER, cell_errors
from ozr.measure import measure
from ozr.triage import host_allowed

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
DENYLIST = load_denylist()
KEY = {
    "jurisdiction_id": "us-00000",
    "unlisted_rule": "none",
    "table_key": [
        {"symbol": "P", "status": "permitted", "quote": "P - Permitted", "section": "Sec. 1"},
        {"symbol": "SE", "status": "conditional", "quote": "SE - Special exception", "section": "Sec. 1"},
        {"symbol": "", "status": "prohibited", "quote": "BLANK - Use not allowed", "section": "Sec. 1"},
    ],
}
LEGEND = "Sec. 1\nP - Permitted\nSE - Special exception\nBLANK - Use not allowed\nWarehouse R-1 I-1 C-1"


def _table(symbol: str, status: str, row: str = "Warehouse", column: str = "I-1") -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": column,
        "use_class": "warehouse_distribution",
        "status": status,
        "confidence": "C",
        "review": "single",
        "evidence": {
            "kind": "table",
            "quote": f"{row} | {column} | {symbol}",
            "section": "Sec. 1",
            "row_label": row,
            "column_header": column,
            "symbol": symbol,
        },
        "source": {"url": "https://planning.example.org/code"},
    }


def _text(table: str, ocr: str = "") -> str:
    return LEGEND + TABLE_TEXT_MARKER + table + (OCR_TEXT_MARKER + ocr if ocr else "")


def test_prose_table_key_quote_requires_table_evidence() -> None:
    cell = _table("", "prohibited")
    cell["evidence"] = {"kind": "prose", "quote": "BLANK - Use not allowed", "section": "Sec. 1"}
    errors = cell_errors(cell, _text("Use | I-1\nWarehouse | P"), TAXONOMY, KEY, DENYLIST)
    assert any("prose evidence quotes the table key" in error for error in errors)
    cell["evidence"]["quote"] = "Warehouse R-1 I-1 C-1"
    errors = cell_errors(cell, _text("Use | I-1\nWarehouse | P"), TAXONOMY, KEY, DENYLIST)
    assert not any("prose evidence quotes the table key" in error for error in errors)


def test_table_key_disables_taxonomy_symbol_fallback() -> None:
    key = {**KEY, "table_key": [KEY["table_key"][0], KEY["table_key"][2]]}
    cell = _table("X", "prohibited")
    errors = cell_errors(cell, _text("Use | I-1\nWarehouse | X"), TAXONOMY, key, DENYLIST)
    assert any("does not map" in error for error in errors)


def test_grid_checks_blank_and_ocr_intersections() -> None:
    cell = _table("P", "permitted")
    errors = cell_errors(
        cell, _text("[page 1]\nUse | I-1\nWarehouse | P\n[page 2]\nUse | I-1\nWarehouse | "), TAXONOMY, KEY, DENYLIST
    )
    assert any("table grid" in error for error in errors)
    errors = cell_errors(
        cell,
        _text("Use | I-1\nWarehouse | P", "[ocr engine: test]\n[page 9]\nUse | I-1\nWarehouse | SE"),
        TAXONOMY,
        KEY,
        DENYLIST,
    )
    assert any("table grid" in error for error in errors)
    assert not any(
        "table grid" in error
        for error in cell_errors(
            cell,
            _text("Use | I-1\nWarehouse | P", "[ocr engine: test]\n[page 9]\nUse | I-1\nWarehouse | P"),
            TAXONOMY,
            KEY,
            DENYLIST,
        )
    )


def test_grid_ignores_same_page_blank_wrapped_heading_but_not_other_page_blank() -> None:
    cell = _table("S", "conditional")
    table = "[page 1]\nCode | Use | I-1\n | Warehouse | \n518 | Warehouse | S"
    assert not any("table grid" in error for error in cell_errors(cell, _text(table), TAXONOMY, KEY, DENYLIST))
    table = "[page 1]\nUse | I-1\nWarehouse | S\n[page 2]\nUse | I-1\nWarehouse | "
    assert any("table grid" in error for error in cell_errors(cell, _text(table), TAXONOMY, KEY, DENYLIST))


def test_grid_headers_do_not_cross_pages() -> None:
    cell = _table("P", "permitted")
    errors = cell_errors(
        cell,
        _text("[page 4]\nUse | I-1 | I-2\nStorage | S | S\n\n[page 5]\nWarehouse | P | S"),
        TAXONOMY,
        KEY,
        DENYLIST,
    )
    assert any("table grid" in error for error in errors)
    cell = _table("SE", "conditional", column="R-1")
    errors = cell_errors(
        cell,
        _text("[page 1]\nUse | R-1 | I-1\nStorage | P | \n\n[page 2]\nWarehouse | SE | X"),
        TAXONOMY,
        KEY,
        DENYLIST,
    )
    assert any("table grid" in error for error in errors)
    assert not any(
        "table grid" in error
        for error in cell_errors(cell, _text("[page 2]\nUse | R-1 | I-1\nWarehouse | SE | X"), TAXONOMY, KEY, DENYLIST)
    )


def test_column_headers_must_bind_district_or_quoted_alias() -> None:
    cell = _table("P", "permitted", column="I-1")
    cell["district_code"] = "I-2"
    errors = cell_errors(cell, _text("Use | I-1 | I-2\nWarehouse | P | X"), TAXONOMY, KEY, DENYLIST)
    assert any("is not the column for district" in error for error in errors)
    cell = _table("P", "permitted", column="C1 2")
    cell["district_code"] = "C-1"
    districts = {**KEY, "districts": [{"district_code": "C-1"}]}
    assert not any(
        "is not the column for district" in error
        for error in cell_errors(cell, _text("Use | C1 2\nWarehouse | P"), TAXONOMY, districts, DENYLIST)
    )
    cell = _table("P", "permitted", column="C-G")
    cell["district_code"] = "C-G-C"
    alias = {
        "district_code": "C-G-C",
        "column_header": "C-G",
        "quote": "C-G district alias",
        "section": "Sec. 1",
        "reason": "table abbreviation",
    }
    key = {**KEY, "column_aliases": [alias]}
    assert not any(
        "is not the column for district" in error
        for error in cell_errors(cell, _text("C-G district alias\nUse | C-G\nWarehouse | P"), TAXONOMY, key, DENYLIST)
    )
    alias["quote"] = "missing alias"
    assert any(
        "is not the column for district" in error
        for error in cell_errors(cell, _text("Use | C-G\nWarehouse | P"), TAXONOMY, key, DENYLIST)
    )
    cell = _table("P", "permitted", column="JLMA-206")
    cell["district_code"] = "JLMA20"
    assert any(
        "is not the column for district" in error
        for error in cell_errors(cell, _text("Use | JLMA-206\nWarehouse | P"), TAXONOMY, KEY, DENYLIST)
    )


def test_column_alias_schema_requires_exact_string_fields() -> None:
    schema = json.loads((ROOT / "schema" / "jurisdiction.schema.json").read_text(encoding="utf-8"))
    alias = {
        "district_code": "C-G-C",
        "column_header": "C-G",
        "quote": "alias",
        "section": "Sec. 1",
        "reason": "short form",
    }
    assert not list(Draft202012Validator(schema["properties"]["column_aliases"]["items"]).iter_errors(alias))
    assert list(
        Draft202012Validator(schema["properties"]["column_aliases"]["items"]).iter_errors({**alias, "extra": "x"})
    )


def test_percent_encoded_host_is_refused() -> None:
    assert check_url("https://library.%6dunicode.com/code", DENYLIST)


def test_arcgis_paths_reject_dot_segments() -> None:
    policy = {"hosts": [], "arcgis_org_ids": ["GOOD"]}
    assert not host_allowed(
        "https://services.arcgis.com/GOOD/../OTHER/arcgis/rest/services/Z/FeatureServer/0", policy, "GOOD"
    )
    assert host_allowed("https://services.arcgis.com/GOOD/arcgis/rest/services/Z/FeatureServer/0", policy, "GOOD")


def test_redirect_refusal_happens_before_banned_target_request(monkeypatch) -> None:
    from ozr import contamination

    class R:
        def __init__(self, code: int, location: str | None = None) -> None:
            self.code, self.headers = code, ({"Location": location} if location else {})

        def close(self) -> None:
            pass

    calls: list[str] = []
    monkeypatch.setattr(
        contamination,
        "_response",
        lambda url, method: calls.append(url) or R(302, "https://library.municode.com/x"),
    )
    errors = check_url("https://www.example.gov/a", DENYLIST, contamination.follow_redirects)
    assert calls == ["https://www.example.gov/a"]
    assert any("redirect target: banned host" in error for error in errors)


def test_fetch_online_redirect_chain_refuses_non_primary_target(tiny_root: Path, monkeypatch) -> None:
    from ozr import contamination, fetch

    class R:
        def __init__(self, code: int, location: str | None = None) -> None:
            self.code, self.headers = code, ({"Location": location} if location else {})

        def close(self) -> None:
            pass

    calls: list[str] = []
    monkeypatch.setattr(
        contamination,
        "_response",
        lambda url, method: calls.append(url) or R(302, "https://other.example.org/code"),
    )
    result = fetch.fetch_jurisdiction(tiny_root, "us-00000", online=True)
    assert result[0]["status"] == "refused"
    assert calls == ["https://planning.example.org/zoning/ordinance.pdf"]


def test_policy_errors_do_not_follow_refused_initial_url() -> None:
    from ozr.fetch import policy_errors

    calls: list[str] = []

    def chain(url: str) -> list[str]:
        calls.append(url)
        return [url]

    policy = {"hosts": ["planning.example.org"], "arcgis_org_ids": []}
    assert policy_errors("https://other.example.org/code", policy, None, DENYLIST, chain)
    assert policy_errors("https://library.municode.com/code", policy, None, DENYLIST, chain)
    assert calls == []


def _measure_cells(statuses: list[str]) -> list[dict]:
    return [
        {"jurisdiction_id": "us-00000", "district_code": f"D-{number}", "use_class": "x", "status": status}
        for number, status in enumerate(statuses)
    ]


def test_unlisted_recall_sufficiency_uses_gold_count(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    (tiny_root / "taxonomy" / "v1.json").write_text(json.dumps({"classes": [{"id": "x"}]}), encoding="utf-8")
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    jurisdiction["districts"] = [{"district_code": f"D-{number}", "family": "industrial"} for number in range(63)]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    gold = ["unlisted"] * 3 + ["prohibited"] * 60
    for name, statuses in (
        ("cells.extracted.json", ["unlisted"] * 63),
        ("cells.review.codex.json", gold),
        ("cells.review.grok.json", gold),
    ):
        (base / name).write_text(json.dumps({"cells": _measure_cells(statuses), "rejected": []}), encoding="utf-8")
    assert (
        measure(tiny_root, ["us-00000"], tiny_root / "none.json")["gates"]["unlisted_recall"]["result"]
        == "insufficient data"
    )


def test_unlisted_recall_fails_when_gold_is_sufficient(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    (tiny_root / "taxonomy" / "v1.json").write_text(json.dumps({"classes": [{"id": "x"}]}), encoding="utf-8")
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    jurisdiction["districts"] = [{"district_code": f"D-{number}", "family": "industrial"} for number in range(60)]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    gold = ["unlisted"] * 60
    for name, statuses in (
        ("cells.extracted.json", ["permitted"] * 60),
        ("cells.review.codex.json", gold),
        ("cells.review.grok.json", gold),
    ):
        (base / name).write_text(json.dumps({"cells": _measure_cells(statuses), "rejected": []}), encoding="utf-8")
    assert measure(tiny_root, ["us-00000"], tiny_root / "none.json")["gates"]["unlisted_recall"]["result"] == "fail"
