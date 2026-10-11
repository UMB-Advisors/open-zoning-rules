"""Regression coverage for the Z0.10 review, round 2.

The first tests are the review's reproductions, with their assertions unchanged: each asserts the correct
behaviour and failed on f80f209. Tests marked CACHE read the source-text cache, which CI does not have.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ozr.gates import (
    TABLE_TEXT_MARKER,
    _amendment_quote_errors,
    _column_binds_district,
    _grid_values,
    _validator,
    superseded_errors,
    table_errors,
)

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
CACHE = pytest.mark.skipif(not (ROOT / "cache" / "text").is_dir(), reason="needs the source-text cache")


def _prose(quote: str, status: str = "permitted", district: str = "I-1") -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": district,
        "use_class": "warehouse_distribution",
        "status": status,
        "evidence": {"kind": "prose", "quote": quote, "section": "Sec. 1"},
        "source": {"id": "us-00000-zo", "url": "https://planning.example.org/code"},
    }


KEY = [
    {"symbol": "P", "status": "permitted", "quote": "P - Permitted Uses"},
    {"symbol": "SE", "status": "conditional", "quote": "SE - Special Exception Uses (Board)"},
]
LEGEND_TEXT = "Sec. 1 Key\nP - Permitted Uses\nSE - Special Exception Uses (Board)\n"


def test_n1_prose_quote_spanning_two_legend_entries_is_still_a_legend_quote() -> None:
    """Finding 1 fix uses substring containment against ONE key entry; a quote straddling two entries passes."""
    cell = _prose("Permitted Uses SE - Special Exception")
    errors = table_errors(cell, LEGEND_TEXT, TAXONOMY, {"table_key": KEY})
    assert errors, "a quote made only of legend text must be rejected as prose evidence"


def test_n2_legend_rule_inert_without_table_key_even_when_grid_places_row() -> None:
    """Finding 1 alternative ('require table evidence when the grid can place the row') was not built.

    A jurisdiction with a use table but no quoted table_key (us-12069 today) accepts a prose cell for a
    row the reconstructed grid can place.
    """
    text = (
        'Sec. 1 Uses shown as "P" are permitted.\n'
        + TABLE_TEXT_MARKER
        + "[page 3]\nUse | I-1 | I-2\nWarehouse | P | P\n"
    )
    cell = _prose('Uses shown as "P" are permitted.')
    errors = table_errors(cell, text, TAXONOMY, {})
    assert errors, "prose evidence for a row the grid can place must be rejected or required to cite the table"


def test_n3_formatting_binding_is_ambiguous_between_footnoted_r1_and_r16() -> None:
    """Formatting-only binding strips separators, so 'R-1 6' (R-1, footnote 6) also binds to district R16."""
    jurisdiction: dict = {}
    bound = [code for code in ("R1", "R16") if _column_binds_district(code, "R-1 6", jurisdiction, "")]
    assert len(bound) <= 1, f"one column header bound to several districts: {bound}"


def _amendment(**overrides) -> dict:
    record = {
        "id": "us-00000-a1",
        "jurisdiction_id": "us-00000",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "dates": {"adopted": "2025-03-18"},
        "use_classes": ["datacenter"],
        "districts": ["MR-HI"],
        "quote": "x",
        "source": {"id": "us-00000-amend"},
        "results": [
            {
                "use_class": "datacenter",
                "districts": ["MRHI"],
                "status": "permitted",
                "source_id": "us-00000-amend",
                "section": "Sec. 1",
                "quote": "Data Center uses are permitted",
            }
        ],
    }
    record.update(overrides)
    return record


def _dc_cell(district: str = "MRHI") -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": district,
        "use_class": "datacenter",
        "status": "permitted",
        "evidence": {"kind": "table", "quote": "Data Center | MR-HI | P", "section": "Sec. 1"},
        "source": {"id": "us-00000-zo"},
    }


SOURCES = {"us-00000-zo": {"source_id": "us-00000-zo", "source_date": "2023-11-21"}}
JUR = {"code_version": "2023-12-13", "districts": [{"district_code": "MRHI"}]}


def test_n4_superseded_gate_fails_open_on_unknown_district_code() -> None:
    """An amendment whose district spelling is not a district code of the jurisdiction silently matches nothing."""
    errors = superseded_errors(_dc_cell(), [_amendment()], SOURCES, JUR, "")
    assert errors, "an amendment naming no known district (or an unknown one) must fail closed, not be skipped"


def test_n5_superseded_gate_fails_open_on_unrecognised_status() -> None:
    """A record with status 'Adopted' (or missing kind) is skipped rather than rejected."""
    errors = superseded_errors(_dc_cell(), [_amendment(status="Adopted", districts=["MRHI"])], SOURCES, JUR, "")
    assert errors, "an amendment record the gate cannot interpret must fail closed"


def test_control_superseded_gate_fires_on_exact_record() -> None:
    errors = superseded_errors(_dc_cell(), [_amendment(districts=["MRHI"])], SOURCES, JUR, "")
    assert errors and "us-00000-a1" in errors[0]


def test_control_real_loudoun_mrhi_is_withheld_superseded() -> None:
    withheld = json.loads((ROOT / "releases" / "v0.1.0" / "withheld.json").read_text())
    rows = withheld if isinstance(withheld, list) else withheld.get("withheld", [])
    row = next(r for r in rows if r["key"] == "us-51107/MRHI/datacenter")
    assert row["gate"] == "superseded" and "ZOAM-2024-0001" in " ".join(row["reason"])


# ---- codex findings, confirmed against the code ----


def _real(jid: str) -> tuple[dict, str]:
    jurisdiction = json.loads((ROOT / "jurisdictions" / jid / "jurisdiction.json").read_text())
    return jurisdiction, (ROOT / "cache" / "text" / f"{jid}-zo-art3.txt").read_text(encoding="utf-8")


@CACHE
def test_c1_real_fauquier_legend_plus_page_footer_passes_all_cell_gates() -> None:
    """Codex #1 on real data: legend line suffix + adjacent page footer is not caught by substring containment."""
    from ozr.contamination import load_denylist
    from ozr.gates import cell_errors

    jurisdiction, text = _real("us-51061")
    rejected = json.loads((ROOT / "jurisdictions" / "us-51061" / "cells.extracted.json").read_text())["rejected"]
    cell = next(
        r["cell"]
        for r in rejected
        if isinstance(r, dict)
        and r.get("cell", {}).get("district_code") == "RR-2"
        and r["cell"].get("use_class") == "datacenter"
    )
    cell = json.loads(json.dumps(cell))
    cell["evidence"]["quote"] = "Use not allowed as listed in the zoning district represented by that column. III - 4"
    cell.update({"confidence": "C", "review": "agree"})
    errors = cell_errors(cell, text, TAXONOMY, jurisdiction, load_denylist(), absence_text=text)
    assert any("table key" in e for e in errors), errors


def test_c3_prohibited_by_default_prose_over_ocr_code_keeps_grade_b() -> None:
    """Codex #3 / finding 6: a 'prohibited' cell resting on the unlisted-use clause escapes the OCR cap."""
    from ozr.contamination import load_denylist
    from ozr.gates import OCR_TEXT_MARKER, cell_errors

    text = "Sec. 1 Uses not listed are prohibited.\n" + OCR_TEXT_MARKER + "[page 9]\nDala center | P\n"
    jurisdiction = {
        "unlisted_rule": "prohibited_by_default",
        "unlisted_rule_quote": {"quote": "Uses not listed are prohibited.", "section": "Sec. 1"},
    }
    cell = {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": "datacenter",
        "status": "prohibited",
        "confidence": "B",
        "review": "agree",
        "parcel_specific": False,
        "evidence": {"kind": "prose", "quote": "Uses not listed are prohibited.", "section": "Sec. 1"},
        "source": {"id": "us-00000-zo", "url": "https://planning.example.org/code"},
    }
    errors = cell_errors(cell, text, TAXONOMY, jurisdiction, load_denylist(), absence_text=text)
    assert errors, "a default-rule prohibition over an OCR code must be capped at C or rejected"


def test_c4_same_page_conflicting_blank_row_is_discarded() -> None:
    """Codex #4 / finding 7: a blank placement under a repeated same-page header is dropped by the heading heuristic."""
    text = "Sec. 1\n" + TABLE_TEXT_MARKER + "[page 3]\nUse | I-1\nWarehouse | P\nUse | I-1\nWarehouse | \n"
    from ozr.gates import _table_grid_errors

    errors = _table_grid_errors("k", "Warehouse", "I-1", "P", text)
    assert errors, "the two placements disagree (P and blank); the cell must not pass"


def test_c6_absence_hit_section_from_another_source(tmp_path: Path) -> None:
    """Codex #6 / finding 16: the explanation's section is searched across the joined text, not the quote's source."""
    from ozr.gates import absence_errors, jurisdiction_text

    (tmp_path / "a.txt").write_text("Sec. 1: no data center use is listed here.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Sec. 99: unrelated material.", encoding="utf-8")
    text = jurisdiction_text(tmp_path, ["a", "b"])
    cell = {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": "datacenter",
        "status": "unlisted",
        "evidence": {"kind": "absence", "quote": "x", "section": "Sec. 1"},
        "absence_hits": [
            {"term": "data center", "quote": "no data center use is listed here", "section": "Sec. 99", "reason": "r"}
        ],
    }
    errors = absence_errors(cell, text, TAXONOMY, {"unlisted_rule": "none"})
    assert errors, "the explanation's section must be found in the same source as its quote"


def test_c7_encoded_slash_dot_segment_passes_host_allowed() -> None:
    """Codex #7 / finding 11: '%2e%2e%2f' inside one segment survives the per-segment check."""
    from ozr.triage import host_allowed

    url = "https://services.arcgis.com/GOOD/%2e%2e%2fOTHER/arcgis/rest/services/Z/FeatureServer/0"
    assert not host_allowed(url, {"hosts": [], "arcgis_org_ids": ["GOOD"]}, "GOOD")


def test_c8_amendment_source_url_not_resolved_against_registered_source(tmp_path: Path) -> None:
    """Codex #8: an amendment whose source.url differs from the registered source (non-primary host) passes.

    (A denylisted host would still be caught by the repo-wide `python -m ozr.contamination` scan, not by the
    release gate; a non-denylisted non-primary host is caught by neither.)
    """
    from ozr.gates import _amendment_quote_errors

    (tmp_path / "us-00000-amend.txt").write_text("the board adopted the amendment text", encoding="utf-8")
    sources = {"us-00000-amend": {"source_id": "us-00000-amend", "url": "https://www.county.example.gov/a"}}
    amendment = {
        "id": "a1",
        "quote": "adopted the amendment text",
        "source": {"id": "us-00000-amend", "url": "https://mirror.example.com/copied-code"},
    }
    errors = _amendment_quote_errors([amendment], sources, tmp_path)
    assert errors, "amendment source url must match its registered primary source"


@CACHE
def test_c2_generic_incorporation_quote_exempts_real_mrhi_cell() -> None:
    """Codex #2: any quote found in the cited source counts as proof of incorporation (here a bare use name)."""
    base = ROOT / "jurisdictions" / "us-51107"
    amendment = json.loads((base / "amendments.json").read_text())[0]
    amendment["incorporated_in"] = [{"source_id": "us-51107-zo-ch3", "quote": "Data Center"}]
    sources = {s["source_id"]: s for s in json.loads((base / "sources.json").read_text())["sources"]}
    jurisdiction = json.loads((base / "jurisdiction.json").read_text())
    extracted = json.loads((base / "cells.extracted.json").read_text())
    cell = next(
        c
        for c in extracted["cells"] + [r["cell"] for r in extracted["rejected"] if isinstance(r, dict) and "cell" in r]
        if c["district_code"] == "MRHI" and c["use_class"] == "datacenter"
    )
    text = (ROOT / "cache" / "text" / f"{cell['source']['id']}.txt").read_text(encoding="utf-8")
    assert superseded_errors(cell, [amendment], sources, jurisdiction, text), (
        "a quote that predates the amendment cannot prove the cited text incorporates it"
    )


@CACHE
def test_rejected_grok_art4_unlisted_cells_have_no_grid_placement() -> None:
    """Grok's published-data claim (us-51061 M-G/M-R datacenter, lp_gas cite the Marshall key line): the Article 4
    table and OCR layers place no data center or LP gas row, so the cells rest on absence, not a legend symbol."""
    from ozr.gates import text_layers

    _, table, ocr = text_layers((ROOT / "cache" / "text" / "us-51061-zo-art4.txt").read_text(encoding="utf-8"))
    lines = (table + "\n" + ocr).lower().splitlines()
    assert not [line for line in lines if "data center" in line or "lp gas" in line or "propane" in line]


def test_round2_legend_span_overlap_and_absence_key_exception() -> None:
    cell = _prose("Uses SE - Special", status="unlisted")
    cell["evidence"]["kind"] = "absence"
    assert any("table key" in error for error in table_errors(cell, LEGEND_TEXT, TAXONOMY, {"table_key": KEY}))
    blank = "If Blank, Use Not Allowed (Uses not listed also not allowed)"
    assert not table_errors(cell, blank, TAXONOMY, {"table_key": [{"quote": "P means permitted"}]})


def test_round2_heading_rows_and_column_readings() -> None:
    table = "[page 1]\nCode | Use | I-1\n | Warehouse | \n518 | Warehouse | P\n"
    assert _grid_values("Warehouse", "I-1", table) == ["p"]
    assert _column_binds_district("R1", "R-1 6", {"districts": [{"district_code": "R1"}]}, "")
    ambiguous = {"districts": [{"district_code": "R1"}, {"district_code": "R16"}]}
    assert not _column_binds_district("R1", "R-1 6", ambiguous, "")
    assert not _column_binds_district("R16", "R-1 6", ambiguous, "")
    assert _column_binds_district("MRHI", "MR-HI", {"districts": [{"district_code": "MRHI"}]}, "")


def test_round2_prose_unlisted_rule_and_grid_rejections() -> None:
    from ozr.contamination import load_denylist
    from ozr.gates import cell_errors

    text = "Sec. 1 Uses not listed are prohibited.\n" + TABLE_TEXT_MARKER + "Use | I-1\nWarehouse | P\n"
    jurisdiction = {
        "unlisted_rule": "prohibited_by_default",
        "unlisted_rule_quote": {"quote": "Uses not listed are prohibited."},
    }
    cell = _prose("Uses not listed are prohibited.")
    cell.update({"confidence": "B", "review": "agree", "parcel_specific": False})
    assert any(
        "unlisted-use rule" in error for error in cell_errors(cell, text, TAXONOMY, jurisdiction, load_denylist())
    )
    elsewhere = _prose("Warehouse operations require a permit.")
    assert not any(
        "unlisted-use rule" in error
        for error in table_errors(elsewhere, "Sec. 1 Warehouse operations require a permit.", TAXONOMY, jurisdiction)
    )
    grid_cell = _prose("Warehouse operations require a permit.")
    assert any("table grid places" in error for error in table_errors(grid_cell, text, TAXONOMY, {}))


def test_round2_incorporation_and_amendment_source_rules(tmp_path: Path) -> None:
    cell = _dc_cell()
    cell["evidence"]["quote"] = "Sec. 3 Data Center amendment applied"
    amendment = _amendment(
        districts=["MRHI"],
        incorporated_in=[
            {"source_id": "us-00000-zo", "quote": "Data Center amendment", "section": "Sec. 3", "reason": "applied"}
        ],
    )
    assert not superseded_errors(cell, [amendment], SOURCES, JUR, "Sec. 3 Data Center amendment")
    amendment["incorporated_in"] = [{"source_id": "us-00000-zo", "quote": "Data Center amendment"}]
    assert superseded_errors(cell, [amendment], SOURCES, JUR, "Sec. 3 Data Center amendment")
    (tmp_path / "amend.txt").write_text("Sec. 3 adopted text", encoding="utf-8")
    assert any(
        "incorporated_in source missing" in error
        for error in _amendment_quote_errors(
            [
                {
                    "id": "a",
                    "quote": "adopted",
                    "source": {"id": "amend", "url": "https://x"},
                    "incorporated_in": [{"source_id": "missing", "quote": "x", "section": "Sec. 3", "reason": "r"}],
                }
            ],
            {"amend": {"source_id": "amend", "url": "https://x"}},
            tmp_path,
        )
    )


def test_round2_amendment_schema_semantics_and_source_exemption() -> None:
    from ozr.gates import _amendment_semantic_errors

    schema = _validator("amendment.schema.json")
    for jurisdiction_id in ("us-51061", "us-51107"):
        real = json.loads((ROOT / "jurisdictions" / jurisdiction_id / "amendments.json").read_text())
        assert list(schema.iter_errors(real)) == []
    valid = _amendment(source={"id": "us-00000-amend", "url": "https://example.com/a"})
    assert list(schema.iter_errors([valid])) == []
    invalid = dict(valid, status="Adopted")
    assert list(schema.iter_errors([invalid]))
    errors = _amendment_semantic_errors([dict(valid, districts=["MR-HI"])], {"us-00000": JUR}, {"datacenter"})
    assert any("district" in error for error in errors)
    amendment = _amendment(
        districts=["MRHI"],
        quote="actual amendment text",
        source={"id": "us-00000-amend", "url": "https://example.com/a"},
    )
    sources = dict(SOURCES, **{"us-00000-amend": {"source_date": "2025-01-01"}})
    title_cell = _dc_cell()
    title_cell["source"] = {"id": "us-00000-amend"}
    title_cell["evidence"]["quote"] = "Board meeting title"
    assert superseded_errors(title_cell, [amendment], sources, JUR, "Board meeting title")
    title_cell["evidence"]["quote"] = "Data Center uses are permitted"
    assert not superseded_errors(title_cell, [amendment], sources, JUR, "Data Center uses are permitted")


def test_round2_host_allowed_rejects_backslashes() -> None:
    from ozr.triage import host_allowed

    policy = {"hosts": [], "arcgis_org_ids": ["GOOD"]}
    assert not host_allowed("https://services.arcgis.com/GOOD\\bad", policy, "GOOD")
    assert not host_allowed("https://services.arcgis.com/GOOD/%5cbad", policy, "GOOD")
    assert host_allowed("https://services.arcgis.com/GOOD/arcgis/rest/services/Z/FeatureServer/0", policy, "GOOD")


@CACHE
def test_round2_real_published_controls_still_pass() -> None:
    """Douglas HI/LI/LI-R datacenter (heading row skipped), Fauquier battery (incorporated_in) and Loudoun IP/GI
    (cell quotes the amendment) pass every cell gate and the SUPERSEDED gate."""
    from ozr.contamination import load_denylist
    from ozr.gates import cell_errors, jurisdiction_text

    wanted = {
        "us-13097/HI/datacenter",
        "us-13097/LI/datacenter",
        "us-13097/LI-R/datacenter",
        "us-51061/RA/battery_storage",
        "us-51061/BP/battery_storage",
        "us-51061/I-1/battery_storage",
        "us-51061/I-2/battery_storage",
        "us-51107/IP/datacenter",
        "us-51107/GI/datacenter",
    }
    text_dir = ROOT / "cache" / "text"
    seen = set()
    for jid in sorted({key.split("/")[0] for key in wanted}):
        base = ROOT / "jurisdictions" / jid
        jurisdiction = json.loads((base / "jurisdiction.json").read_text())
        sources = {s["source_id"]: s for s in json.loads((base / "sources.json").read_text())["sources"]}
        amendments = json.loads((base / "amendments.json").read_text()) if (base / "amendments.json").is_file() else []
        exempt = {sid for sid in jurisdiction["sources"] if sources.get(sid, {}).get("kind") == "gis_layer"}
        absence = jurisdiction_text(text_dir, jurisdiction["sources"], exempt=exempt)
        for cell in json.loads((base / "cells.json").read_text()):
            key = f"{cell['jurisdiction_id']}/{cell['district_code']}/{cell['use_class']}"
            if key not in wanted:
                continue
            seen.add(key)
            text = (text_dir / f"{cell['source']['id']}.txt").read_text(encoding="utf-8")
            assert (
                cell_errors(
                    cell, text, TAXONOMY, jurisdiction, load_denylist(), absence_text=absence, amendments=amendments
                )
                == []
            ), key
            assert superseded_errors(cell, amendments, sources, jurisdiction, text) == [], key
    assert seen == wanted
