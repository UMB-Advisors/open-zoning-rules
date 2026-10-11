"""Regression coverage for the Z0.11 structural gate rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ozr.gates import (
    TABLE_TEXT_MARKER,
    _amendment_interpretation_error,
    _validator,
    cell_errors,
    jurisdiction_text,
    superseded_errors,
)

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
CACHE = pytest.mark.skipif(not (ROOT / "cache" / "text").is_dir(), reason="needs the source-text cache")
DENYLIST = frozenset()
JUR = {"districts": [{"district_code": "I-1"}]}


def _cell(status: str = "permitted", quote: str = "Warehouse operations are allowed") -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": "warehouse_distribution",
        "status": status,
        "confidence": "C",
        "review": "agree",
        "parcel_specific": False,
        "evidence": {"kind": "prose", "quote": quote, "section": "Sec. 1"},
        "source": {"id": "a", "url": "https://example.org/a"},
    }


def test_prose_must_name_its_taxonomy_use() -> None:
    text = "Sec. 1 Warehouse operations are allowed"
    errors = cell_errors(_cell(quote="Operations are allowed"), text, TAXONOMY, JUR, DENYLIST)
    assert any("prose names the use" in error for error in errors)
    assert not any("prose names the use" in error for error in cell_errors(_cell(), text, TAXONOMY, JUR, DENYLIST))
    for status in ("conditional", "prohibited"):
        assert any(
            "prose names the use" in error
            for error in cell_errors(_cell(status, "Allowed only by permit"), text, TAXONOMY, JUR, DENYLIST)
        )


def test_adopted_amendments_need_a_declared_result() -> None:
    amendment = {
        "id": "a1",
        "jurisdiction_id": "us-00000",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "dates": {"adopted": "2025-01-01"},
        "use_classes": ["warehouse_distribution"],
        "districts": ["I-1"],
    }
    sources = {"a": {"source_date": "2020-01-01"}}
    assert superseded_errors(_cell(), [amendment], sources, JUR, "") == []
    amendment["results"] = [
        {
            "use_class": "warehouse_distribution",
            "districts": ["I-1"],
            "status": "conditional",
            "source_id": "a",
            "section": "Sec. 1",
            "quote": "Warehouse operations require a permit",
        }
    ]
    assert superseded_errors(_cell(), [amendment], sources, JUR, "Sec. 1 Warehouse operations require a permit")


def test_moratoria_never_supersede_or_interpret_results() -> None:
    amendment = {
        "id": "m1",
        "jurisdiction_id": "us-00000",
        "kind": "moratorium",
        "status": "active",
        "use_classes": ["warehouse_distribution"],
        "districts": ["not-a-code"],
        "results": [],
    }
    assert superseded_errors(_cell(), [amendment], {"a": {"source_date": "2020-01-01"}}, JUR, "") == []
    schema = _validator("amendment.schema.json")
    assert list(schema.iter_errors([amendment]))


def test_interpretation_rejects_conflicting_or_uncovered_results() -> None:
    amendment = {
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "use_classes": ["warehouse_distribution"],
        "districts": ["I-1"],
        "results": [
            {
                "use_class": "warehouse_distribution",
                "districts": ["I-1"],
                "status": "permitted",
                "source_id": "a",
                "section": "s",
                "quote": "Warehouse use",
            },
            {
                "use_class": "warehouse_distribution",
                "districts": ["I-1"],
                "status": "conditional",
                "source_id": "a",
                "section": "s",
                "quote": "Warehouse use",
            },
        ],
    }
    assert "conflict" in (_amendment_interpretation_error(amendment, JUR) or "")


def test_ordinance_grid_is_scanned_per_source_and_exempted_by_result(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Sec. 1 Warehouse operations are allowed", encoding="utf-8")
    (tmp_path / "b.txt").write_text(TABLE_TEXT_MARKER + "[page 1]\nUse | I-1\nWarehouse | P\n", encoding="utf-8")
    joined = jurisdiction_text(tmp_path, ["a", "b"])
    errors = cell_errors(
        _cell(), "Sec. 1 Warehouse operations are allowed", TAXONOMY, JUR, DENYLIST, absence_text=joined
    )
    assert any("ordinance grid" in error for error in errors)


def test_schema_refuses_blank_reference_and_validates_real_amendments() -> None:
    schema = _validator("amendment.schema.json")
    for jid in ("us-51061", "us-51107"):
        assert (
            list(schema.iter_errors(json.loads((ROOT / "jurisdictions" / jid / "amendments.json").read_text()))) == []
        )
    record = {
        "id": "a",
        "jurisdiction_id": "x",
        "kind": "moratorium",
        "status": "active",
        "use_classes": ["x"],
        "districts": ["x"],
        "quote": "x",
        "reference": " ",
        "source": {"id": "x", "url": "https://example.org"},
    }
    assert list(schema.iter_errors([record]))


def _jur(jid):
    return json.loads((ROOT / "jurisdictions" / jid / "jurisdiction.json").read_text(encoding="utf-8"))


def _sources(jid):
    doc = json.loads((ROOT / "jurisdictions" / jid / "sources.json").read_text(encoding="utf-8"))
    return {s["source_id"]: s for s in doc["sources"]}


def _text(source_id):
    return (ROOT / "cache" / "text" / f"{source_id}.txt").read_text(encoding="utf-8")


def _joined(jid):
    ids = [sid for sid, s in _sources(jid).items() if (ROOT / "cache" / "text" / f"{sid}.txt").is_file()]
    return jurisdiction_text(ROOT / "cache" / "text", ids)


def _real(jid, district, use_class, status, quote, section, source_id):
    return {
        "jurisdiction_id": jid,
        "district_code": district,
        "use_class": use_class,
        "status": status,
        "confidence": "C",
        "review": "agree",
        "parcel_specific": False,
        "local_uses": [],
        "evidence": {"kind": "prose", "quote": quote, "section": section},
        "source": {"id": source_id, "url": _sources(jid)[source_id]["url"]},
    }


def _gate(cell):
    from ozr.contamination import load_denylist

    jid = cell["jurisdiction_id"]
    return cell_errors(
        cell, _text(cell["source"]["id"]), TAXONOMY, _jur(jid), load_denylist(), absence_text=_joined(jid)
    )


@CACHE
def test_r1_second_legend_not_in_table_key_passes_as_prose_evidence():
    cell = _real(
        "us-51061", "M-G", "datacenter", "permitted", "P Permitted Use SP Special Permit", "4-1002", "us-51061-zo-art4"
    )
    errors = _gate(cell)
    assert errors, "a legend line is not evidence for a listed status"


@CACHE
def test_r3_second_unlisted_clause_supports_prohibited():
    cell = _real(
        "us-51061", "M-G", "datacenter", "prohibited", "Uses not listed also not allowed", "4-1002", "us-51061-zo-art4"
    )
    errors = _gate(cell)
    assert errors, "an unlisted-use clause must not turn unlisted into prohibited"


@CACHE
def test_r4_prose_from_another_article_escapes_grid_placement():
    from ozr.gates import _grid_values, text_layers

    jid = "us-51061"
    _, table, ocr = text_layers(_text("us-51061-zo-art3"))
    assert _grid_values("5. a. Warehousing including Self-Storage Facilities", "RA", table + ocr) == [""]
    cell = _real(
        jid, "RA", "warehouse_distribution", "permitted", "Warehousing facilities", "4-603", "us-51061-zo-art4"
    )
    errors = _gate(cell)
    assert errors, "prose from another article must not override the district's use-table placement"


def _mrhi(status, quote, section):
    return _real("us-51107", "MRHI", "datacenter", status, quote, section, "us-51107-dc-phase1")


def _amendments():
    return json.loads((ROOT / "jurisdictions" / "us-51107" / "amendments.json").read_text(encoding="utf-8"))


@CACHE
def test_r2a_page_title_with_reference_exempts_permitted_mrhi():
    title = "Data Center Standards and Location Phase 1: CPAM-2024-0001 and ZOAM-2024-0001"
    cell = _mrhi("permitted", title, "ZOAM-2024-0001")
    # The whole-ordinance scan now also rejects this prose cell because the Loudoun use table
    # places a data center row under MR-HI.
    assert not [e for e in _gate(cell) if "ordinance grid" not in e], "precondition: the cell passes every cell gate"
    errors = superseded_errors(cell, _amendments(), _sources("us-51107"), _jur("us-51107"), _text("us-51107-dc-phase1"))
    assert errors, "a page title naming the amendment is not evidence of the post-amendment status"


@CACHE
def test_r2b_amendment_quote_with_wrong_status_is_exempt():
    amendment = _amendments()[0]
    cell = _mrhi("permitted", amendment["quote"], "ZOAM-2024-0001")
    # The whole-ordinance scan now also rejects this prose cell because the Loudoun use table
    # places a data center row under MR-HI.
    assert not [e for e in _gate(cell) if "ordinance grid" not in e], "precondition: the cell passes every cell gate"
    errors = superseded_errors(cell, [amendment], _sources("us-51107"), _jur("us-51107"), _text("us-51107-dc-phase1"))
    assert errors, "a cell citing an amendment that requires SPEX cannot be published 'permitted'"


@CACHE
def test_control_r2_mrhi_conditional_citing_amendment_is_exempt():
    amendment = _amendments()[0]
    cell = _mrhi("conditional", amendment["quote"], "ZOAM-2024-0001")
    assert not superseded_errors(cell, [amendment], _sources("us-51107"), _jur("us-51107"), _text("us-51107-dc-phase1"))


def _real_mrhi_cell():
    extracted = json.loads((ROOT / "jurisdictions" / "us-51107" / "cells.extracted.json").read_text(encoding="utf-8"))
    pool = extracted["cells"] + [r["cell"] for r in extracted["rejected"] if isinstance(r, dict) and "cell" in r]
    return next(c for c in pool if c["district_code"] == "MRHI" and c["use_class"] == "datacenter")


@CACHE
def test_x1_district_header_as_incorporation_quote_exempts_real_mrhi():
    cell = _real_mrhi_cell()
    assert cell["status"] == "permitted" and "MR-HI" in cell["evidence"]["quote"]
    amendment = _amendments()[0]
    amendment["incorporated_in"] = [
        {
            "source_id": cell["source"]["id"],
            "quote": "MR-HI",
            "section": cell["evidence"]["section"],
            "reason": "The district column incorporates the amendment.",
        }
    ]
    errors = superseded_errors(cell, [amendment], _sources("us-51107"), _jur("us-51107"), _text(cell["source"]["id"]))
    assert errors, "a district header cannot prove the cited text carries the amendment"


@CACHE
def test_g1_one_letter_incorporation_quote_exempts():
    cell = _real_mrhi_cell()
    amendment = _amendments()[0]
    amendment["incorporated_in"] = [
        {"source_id": cell["source"]["id"], "quote": "P", "section": cell["evidence"]["section"], "reason": "symbol"}
    ]
    errors = superseded_errors(cell, [amendment], _sources("us-51107"), _jur("us-51107"), _text(cell["source"]["id"]))
    assert errors, "a one-letter symbol cannot prove incorporation"


@CACHE
def test_r2a_conditional_title_still_supersedes():
    title = "Data Center Standards and Location Phase 1: CPAM-2024-0001 and ZOAM-2024-0001"
    cell = _mrhi("conditional", title, "ZOAM-2024-0001")
    sources = _sources("us-51107")
    sources[cell["source"]["id"]] = {**sources[cell["source"]["id"]], "source_date": "2020-01-01"}
    assert superseded_errors(cell, _amendments(), sources, _jur("us-51107"), _text("us-51107-dc-phase1"))


@CACHE
def test_x1_g1_conditional_incorporation_quotes_do_not_exempt():
    cell = _real_mrhi_cell()
    cell = {**cell, "status": "conditional"}
    for quote in ("MR-HI", "P"):
        amendment = _amendments()[0]
        amendment["incorporated_in"] = [
            {
                "source_id": cell["source"]["id"],
                "quote": quote,
                "section": cell["evidence"]["section"],
                "reason": "symbol",
            }
        ]
        assert superseded_errors(cell, [amendment], _sources("us-51107"), _jur("us-51107"), _text(cell["source"]["id"]))


def test_incorporation_needs_class_term_and_more_than_code_or_symbol():
    jurisdiction = {
        "districts": [{"district_code": "MRHI"}, {"district_code": "I-1"}],
        "table_key": [{"symbol": "SE", "status": "conditional", "quote": "SE Special Exception"}],
    }
    cell = _cell("conditional", "Data Center Tier 9 | MR-HI | SE")
    cell.update({"district_code": "MRHI", "use_class": "datacenter", "source": {"id": "zo"}})
    amendment = {
        "id": "a1",
        "jurisdiction_id": "us-00000",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "dates": {"adopted": "2025-01-01"},
        "use_classes": ["datacenter"],
        "districts": ["MRHI"],
        "results": [
            {
                "use_class": "datacenter",
                "districts": ["MRHI"],
                "status": "conditional",
                "source_id": "amend",
                "section": "Sec. 1",
                "quote": "Data Center Tier 9",
            }
        ],
    }
    sources = {"zo": {"source_date": "2020-01-01"}}
    for quote in ("SE", "MR-HI", "Data Center"):
        amendment["incorporated_in"] = [{"source_id": "zo", "quote": quote, "section": "Sec. 1", "reason": "r"}]
        assert superseded_errors(cell, [amendment], sources, jurisdiction, "Sec. 1 Data Center Tier 9 | MR-HI | SE")
    amendment["incorporated_in"] = [
        {"source_id": "zo", "quote": "Data Center Tier 9", "section": "Sec. 1", "reason": "r"}
    ]
    assert not superseded_errors(cell, [amendment], sources, jurisdiction, "Sec. 1 Data Center Tier 9 | MR-HI | SE")
    cell["status"] = "permitted"
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "Sec. 1 Data Center Tier 9 | MR-HI | SE")


def test_adopted_record_without_results_never_supersedes():
    amendment = {
        "id": "a1",
        "jurisdiction_id": "us-00000",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "dates": {"adopted": "2025-01-01"},
        "use_classes": ["warehouse_distribution"],
        "districts": ["I-1"],
    }
    assert superseded_errors(_cell(), [amendment], {"a": {"source_date": "2020-01-01"}}, JUR, "") == []


def test_moratorium_never_supersedes():
    amendment = {
        "id": "m1",
        "jurisdiction_id": "us-00000",
        "kind": "moratorium",
        "status": "active",
        "dates": {"adopted": "2025-01-01"},
        "use_classes": ["*"],
        "districts": ["*"],
    }
    sources = {"a": {"source_date": "2020-01-01"}}
    assert superseded_errors(_cell(), [amendment], sources, JUR, "") == []
    amendment["results"] = []
    assert superseded_errors(_cell(), [amendment], sources, JUR, "") == []
    assert list(_validator("amendment.schema.json").iter_errors([amendment]))


def test_prose_names_the_use_for_each_listed_status():
    for status in ("permitted", "conditional", "prohibited"):
        assert any(
            "prose names the use" in error
            for error in cell_errors(_cell(status, "Allowed by permit"), "Allowed by permit", TAXONOMY, JUR, DENYLIST)
        )
        assert not any(
            "prose names the use" in error
            for error in cell_errors(
                _cell(status, "Warehouse allowed by permit"), "Warehouse allowed by permit", TAXONOMY, JUR, DENYLIST
            )
        )
    absence = _cell()
    absence.update({"status": "unlisted", "evidence": {"kind": "absence", "quote": "Allowed", "section": "Sec. 1"}})
    table = _cell()
    table["evidence"]["kind"] = "table"
    assert not any("prose names the use" in error for error in cell_errors(absence, "Allowed", TAXONOMY, JUR, DENYLIST))
    assert not any("prose names the use" in error for error in cell_errors(table, "Allowed", TAXONOMY, JUR, DENYLIST))


def test_ordinance_grid_exemption_by_declared_result(tmp_path: Path):
    (tmp_path / "a.txt").write_text("Sec. 1 Warehouse operations are allowed", encoding="utf-8")
    (tmp_path / "b.txt").write_text(TABLE_TEXT_MARKER + "[page 1]\nUse | I-1\nWarehouse | P\n", encoding="utf-8")
    joined = jurisdiction_text(tmp_path, ["a", "b"])
    amendment = {
        "id": "a1",
        "jurisdiction_id": "us-00000",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "use_classes": ["warehouse_distribution"],
        "districts": ["I-1"],
        "results": [
            {
                "use_class": "warehouse_distribution",
                "districts": ["I-1"],
                "status": "permitted",
                "source_id": "a",
                "section": "Sec. 1",
                "quote": "Warehouse operations are allowed",
            }
        ],
    }
    assert not any(
        "ordinance grid" in error
        for error in cell_errors(
            _cell(),
            "Sec. 1 Warehouse operations are allowed",
            TAXONOMY,
            JUR,
            DENYLIST,
            absence_text=joined,
            amendments=[amendment],
        )
    )
    amendment["results"][0]["status"] = "conditional"
    assert any(
        "ordinance grid" in error
        for error in cell_errors(
            _cell(),
            "Sec. 1 Warehouse operations are allowed",
            TAXONOMY,
            JUR,
            DENYLIST,
            absence_text=joined,
            amendments=[amendment],
        )
    )


def test_ordinance_grid_alias_does_not_bind_across_sources(tmp_path: Path):
    jurisdiction = {
        "districts": [{"district_code": "I-1"}],
        "column_aliases": [{"district_code": "I-1", "column_header": "Ind", "quote": "Ind means the I-1 district"}],
    }
    (tmp_path / "a.txt").write_text("Ind means the I-1 district", encoding="utf-8")
    (tmp_path / "b.txt").write_text(TABLE_TEXT_MARKER + "[page 1]\nUse | Ind\nWarehouse | P\n", encoding="utf-8")
    cell = _cell()
    assert not any(
        "ordinance grid" in error
        for error in cell_errors(
            cell,
            "Ind means the I-1 district",
            TAXONOMY,
            jurisdiction,
            DENYLIST,
            absence_text=jurisdiction_text(tmp_path, ["a", "b"]),
        )
    )
    (tmp_path / "b.txt").write_text(
        "Ind means the I-1 district\n" + TABLE_TEXT_MARKER + "[page 1]\nUse | Ind\nWarehouse | P\n", encoding="utf-8"
    )
    assert any(
        "ordinance grid" in error
        for error in cell_errors(
            cell,
            "Ind means the I-1 district",
            TAXONOMY,
            jurisdiction,
            DENYLIST,
            absence_text=jurisdiction_text(tmp_path, ["a", "b"]),
        )
    )


def test_release_result_quote_checks(tmp_path: Path):
    from ozr.gates import _amendment_quote_errors

    (tmp_path / "amend.txt").write_text("Sec. 1 ZOAM-1 Data Center Tier 9", encoding="utf-8")
    sources = {"amend": {"source_id": "amend", "url": "https://example.org/amend"}}
    record = {
        "id": "a1",
        "reference": "ZOAM-1",
        "quote": "ZOAM-1",
        "source": {"id": "amend", "url": "https://example.org/amend"},
        "results": [{"use_class": "datacenter", "source_id": "amend", "section": "Sec. 1", "quote": "ZOAM-1"}],
    }
    assert any("reference or title" in error for error in _amendment_quote_errors([record], sources, tmp_path))
    record["results"][0]["quote"] = "Tier 9"
    assert any("names no taxonomy term" in error for error in _amendment_quote_errors([record], sources, tmp_path))
    record["results"][0]["quote"] = "Data Center Tier 9"
    record["results"][0]["source_id"] = "other"
    assert any("is not the amendment source" in error for error in _amendment_quote_errors([record], sources, tmp_path))
