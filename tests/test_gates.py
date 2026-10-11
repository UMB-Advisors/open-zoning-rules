"""Gates over synthetic ordinance text for a fictional jurisdiction."""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from ozr.contamination import load_denylist
from ozr.gates import (
    TABLE_TEXT_MARKER,
    absence_errors,
    absence_hits,
    add_months,
    apply_grade_rules,
    canonical,
    cell_errors,
    contains,
    coverage_errors,
    enum_errors,
    match_layer,
    quote_errors,
    section_errors,
)

TAXONOMY = json.loads((Path(__file__).resolve().parents[1] / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
UNLISTED_CLAUSE = "Any use not listed in Table 4-2 is prohibited."
DEFINITION = "Storage equipment means equipment that stores electricity for later dispatch."
ORDINANCE = (
    f"""\
Article 4 Use Table

Sec. 4-2 Table of Permitted Uses

Columns: I-1 and I-2.

Warehouse is listed under I-1 and I-2.
Battery energy storage system is listed under I-1 and I-2.

Sec. 4-3 Uses not listed

{UNLISTED_CLAUSE}

Sec. 2-1 Definitions

{DEFINITION} The plant on Bessemer Road is a substation.

Article\u00a04 regulates ware\u00adhouse design and manufac-
  turing of goods.
"""
    + TABLE_TEXT_MARKER
    + """\
Use | I-1 | I-2
Warehouse | P | P
"""
)
DISTRICTS = ["I-1", "I-2"]
USE_CLASSES = ["datacenter", "warehouse_distribution"]


def jurisdiction(rule: str = "prohibited_by_default") -> dict:
    """Return a fictional jurisdiction record."""
    document = {
        "jurisdiction_id": "us-00000",
        "name": "Example County",
        "type": "county",
        "state": "WA",
        "unlisted_rule": rule,
        "code_version": "2026-01-15",
        "sources": ["src-ordinance"],
    }
    if rule == "prohibited_by_default":
        document["unlisted_rule_quote"] = {"quote": UNLISTED_CLAUSE, "section": "Sec. 4-3"}
    document["table_key"] = [
        {"symbol": "P", "status": "permitted", "quote": "Columns: I-1 and I-2.", "section": "Sec. 4-2"}
    ]
    return document


def make_cell(**overrides: object) -> dict:
    """Return a valid warehouse cell for district I-2."""
    record = {
        "jurisdiction_id": "us-00000",
        "district_code": "I-2",
        "use_class": "warehouse_distribution",
        "status": "permitted",
        "local_uses": ["Warehouse"],
        "evidence": {
            "kind": "table",
            "quote": "Warehouse | I-2 | P",
            "section": "Sec. 4-2",
            "row_label": "Warehouse",
            "column_header": "I-2",
            "symbol": "P",
        },
        "source": {
            "id": "src-ordinance",
            "url": "https://planning.example.org/code/article-4",
            "date": "2026-01-15",
        },
        "confidence": "A",
        "review": "agree",
        "parcel_specific": False,
        "checked_at": "2026-10-09",
        "stale": False,
        "history": [],
    }
    record.update(overrides)
    return record


def unlisted_cell(use_class: str, hits: list[dict] | None = None) -> dict:
    """Return an unlisted absence cell."""
    record = make_cell(
        use_class=use_class,
        status="unlisted",
        local_uses=[],
        evidence={"kind": "absence", "quote": "Sec. 4-2 Table of Permitted Uses", "section": "Sec. 4-2"},
    )
    if hits is not None:
        record["absence_hits"] = hits
    return record


def explained_hits(use_class: str) -> list[dict]:
    """Cite every absence hit with one source sentence."""
    return [
        {
            "term": term,
            "quote": "Battery energy storage system is listed under I-1 and I-2.",
            "section": "Sec. 4-2",
            "reason": "The row names storage equipment and does not establish this class.",
        }
        for term in absence_hits(ORDINANCE, use_class, TAXONOMY)
    ]


def covering_cells() -> list[dict]:
    """Return one cell for every district and requested use class."""
    return [
        make_cell(district_code=district, use_class=use_class) for district in DISTRICTS for use_class in USE_CLASSES
    ]


def test_canonical_normalises_hyphenation_nbsp_and_soft_hyphen() -> None:
    assert canonical("manufac-\n  turing") == "manufacturing"
    assert canonical("manufac-\nturing") == "manufacturing"
    assert canonical("light-\nindustrial") == canonical("light-industrial") == "lightindustrial"
    assert canonical("light\u2010industrial") == "lightindustrial"
    assert canonical("light\u2011industrial") == "lightindustrial"
    assert canonical("ware\u00adhouse") == "warehouse"
    assert canonical("Article\u00a04") == "Article 4"
    assert canonical("Warehouse") == "Warehouse"
    assert canonical("Sec. 4-2") == "Sec. 4-2"
    assert not contains("See Sec. 42 for signs.", "Sec. 4-2")
    assert contains(ORDINANCE, "Article 4 regulates warehouse design and manufacturing of goods.")
    assert not contains(ORDINANCE, "Article 4 regulates warehouse design and manufacturing of parts.")


def test_wrong_quote_fails_after_normalisation() -> None:
    evidence = {
        "kind": "prose",
        "quote": "Article 4 regulates warehouse design and manufacturing of goods.",
        "section": "Article 4",
    }
    record = make_cell(use_class="datacenter", evidence=evidence)
    assert quote_errors(record, ORDINANCE) == []
    evidence["quote"] = "Article 4 regulates warehouse design and manufacturing of parts."
    errors = quote_errors(record, ORDINANCE)
    assert errors == ["us-00000/I-2/datacenter: quote not found in source"]


def test_table_evidence_requires_row_and_column_in_text_and_quote() -> None:
    assert quote_errors(make_cell(), ORDINANCE) == []
    missing_header = make_cell()
    missing_header["evidence"] = {
        "kind": "table",
        "quote": "Warehouse is listed under I-1.",
        "section": "Sec. 4-2",
        "row_label": "Warehouse",
        "column_header": "I-2",
        "symbol": "P",
    }
    assert quote_errors(missing_header, ORDINANCE) == [
        "us-00000/I-2/warehouse_distribution: column header not in quote"
    ]
    missing_row = make_cell()
    missing_row["evidence"] = {
        "kind": "table",
        "quote": "Data center is listed under I-2.",
        "section": "Sec. 4-2",
        "row_label": "Data center",
        "column_header": "I-2",
        "symbol": "P",
    }
    assert quote_errors(missing_row, ORDINANCE) == [
        "us-00000/I-2/warehouse_distribution: row label not found in source"
    ]


def test_match_layer_reports_raw_or_table_and_ignores_the_boundary() -> None:
    text = "alpha beta" + TABLE_TEXT_MARKER + "gamma delta"
    assert match_layer(text, "beta") == "raw"
    assert match_layer(text, "gamma") == "table"
    assert match_layer(text, "beta gamma") is None
    assert match_layer(text, "beta" + TABLE_TEXT_MARKER + "gamma") is None
    record = make_cell()
    record["evidence"] = {
        "kind": "table",
        "quote": "Warehouse | I-2 | P",
        "section": "alpha",
        "row_label": "Warehouse",
        "column_header": "I-2",
        "symbol": "P",
    }
    table_text = "alpha I-2" + TABLE_TEXT_MARKER + "Warehouse | I-2 | P"
    assert quote_errors(record, table_text) == []
    record["evidence"]["row_label"] = "No such row"
    assert "us-00000/I-2/warehouse_distribution: row label not found in source" in quote_errors(record, table_text)


def test_empty_quote_is_an_error() -> None:
    record = make_cell()
    record["evidence"] = {**record["evidence"], "quote": ""}
    assert "us-00000/I-2/warehouse_distribution: no quote" in quote_errors(record, ORDINANCE)
    record["evidence"] = {**record["evidence"], "quote": "   "}
    assert "us-00000/I-2/warehouse_distribution: no quote" in quote_errors(record, ORDINANCE)


def test_definition_quote_must_be_in_source() -> None:
    record = make_cell()
    record["definition_evidence"] = {"quote": DEFINITION, "section": "Sec. 2-1"}
    assert quote_errors(record, ORDINANCE) == []
    assert section_errors(record, ORDINANCE) == []
    record["definition_evidence"] = {"quote": DEFINITION.replace("dispatch", "sale"), "section": "Sec. 9-9"}
    assert quote_errors(record, ORDINANCE) == [
        "us-00000/I-2/warehouse_distribution: definition quote not found in source"
    ]
    assert section_errors(record, ORDINANCE) == [
        "us-00000/I-2/warehouse_distribution: definition section not found in source"
    ]


def test_section_must_be_nonempty_and_in_source() -> None:
    assert section_errors(make_cell(), ORDINANCE) == []
    missing = make_cell()
    missing["evidence"] = {**missing["evidence"], "section": "Sec. 9-9"}
    assert section_errors(missing, ORDINANCE) == ["us-00000/I-2/warehouse_distribution: section not found in source"]
    empty = make_cell()
    empty["evidence"] = {**empty["evidence"], "section": ""}
    assert section_errors(empty, ORDINANCE) == ["us-00000/I-2/warehouse_distribution: no section"]


def test_enum_rejects_unknown_values_and_unlisted_table_evidence() -> None:
    assert enum_errors(make_cell(), TAXONOMY) == []
    bad_class = make_cell(use_class="spaceship")
    assert enum_errors(bad_class, TAXONOMY) == ["us-00000/I-2/spaceship: use_class not in taxonomy"]
    bad_status = make_cell(status="maybe")
    assert enum_errors(bad_status, TAXONOMY) == ["us-00000/I-2/warehouse_distribution: status not in taxonomy"]
    unlisted_table = make_cell(status="unlisted")
    assert enum_errors(unlisted_table, TAXONOMY) == [
        "us-00000/I-2/warehouse_distribution: unlisted requires evidence kind absence"
    ]


def test_absence_gate_explains_hits_and_ignores_bessemer() -> None:
    assert absence_hits(ORDINANCE, "datacenter", TAXONOMY) == []
    assert absence_errors(unlisted_cell("datacenter"), ORDINANCE, TAXONOMY, jurisdiction()) == []
    assert absence_hits(ORDINANCE, "battery_storage", TAXONOMY) == [
        "battery",
        "battery energy storage",
        "energy storage system",
    ]
    assert "BESS" not in absence_hits("The plant is on Bessemer Road.", "battery_storage", TAXONOMY)
    assert absence_hits("Install a BESS near the substation.", "battery_storage", TAXONOMY) == ["BESS"]
    assert "data center" in absence_hits("The code lists data centers in one row.", "datacenter", TAXONOMY)
    bare = unlisted_cell("battery_storage")
    assert absence_errors(bare, ORDINANCE, TAXONOMY, jurisdiction()) == [
        "us-00000/I-2/battery_storage: absence gate: 'battery' occurs 1 times in the code and 1 are not explained",
        "us-00000/I-2/battery_storage: absence gate: 'battery energy storage' occurs 1 times in the code "
        "and 1 are not explained",
        "us-00000/I-2/battery_storage: absence gate: 'energy storage system' occurs 1 times in the code "
        "and 1 are not explained",
    ]
    cited = unlisted_cell("battery_storage", explained_hits("battery_storage"))
    assert absence_errors(cited, ORDINANCE, TAXONOMY, jurisdiction()) == []
    bad_rule = jurisdiction()
    bad_rule["unlisted_rule_quote"] = {"quote": "Any use not listed in Table 4-2 is encouraged.", "section": "Sec. 4-3"}
    errors = absence_errors(unlisted_cell("datacenter"), ORDINANCE, TAXONOMY, bad_rule)
    assert errors == ["us-00000/I-2/datacenter: unlisted rule quote not found in source"]


def test_coverage_requires_each_district_class_once() -> None:
    assert coverage_errors(DISTRICTS, covering_cells(), USE_CLASSES) == []
    missing = [
        record
        for record in covering_cells()
        if not (record["district_code"] == "I-2" and record["use_class"] == "datacenter")
    ]
    assert coverage_errors(DISTRICTS, missing, USE_CLASSES) == ["us-00000/I-2/datacenter: missing cell"]
    unknown = [*covering_cells(), make_cell(district_code="I-9")]
    assert coverage_errors(DISTRICTS, unknown, USE_CLASSES) == ["us-00000/I-9/warehouse_distribution: unknown district"]
    duplicate = [*covering_cells(), make_cell(district_code="I-1", use_class="datacenter")]
    assert coverage_errors(DISTRICTS, duplicate, USE_CLASSES) == ["us-00000/I-1/datacenter: duplicate cell"]


def test_grade_boundary_drop_and_idempotence() -> None:
    checked = make_cell(checked_at="2025-10-09", confidence="A", stale=False)
    on_boundary = apply_grade_rules(checked, date(2026, 10, 9))
    assert on_boundary["stale"] is False
    assert on_boundary["confidence"] == "A"
    one_day_later = apply_grade_rules(checked, date(2026, 10, 10))
    assert one_day_later["stale"] is True
    assert one_day_later["confidence"] == "B"
    assert (
        apply_grade_rules(make_cell(checked_at="2025-10-09", confidence="B"), date(2026, 10, 10))["confidence"] == "C"
    )
    stayed = apply_grade_rules(make_cell(checked_at="2025-10-09", confidence="C"), date(2026, 10, 10))
    assert stayed["confidence"] == "C"
    assert stayed["stale"] is True
    assert apply_grade_rules(one_day_later, date(2026, 10, 10)) == one_day_later
    pending = apply_grade_rules(
        make_cell(checked_at="2026-10-09", confidence="A"), date(2026, 10, 9), pending_amendment=True
    )
    assert pending["stale"] is True
    assert pending["confidence"] == "B"


def test_parcel_specific_caps_confidence_without_mutating_input() -> None:
    original = make_cell(checked_at="2026-10-09", confidence="B", parcel_specific=True, stale=False)
    snapshot = copy.deepcopy(original)
    graded = apply_grade_rules(original, date(2026, 10, 9))
    assert graded is not original
    assert graded["confidence"] == "C"
    assert graded["stale"] is False
    assert original == snapshot
    capped_a = apply_grade_rules(make_cell(confidence="A", parcel_specific=True), date(2026, 10, 9))
    assert capped_a["confidence"] == "C"


def test_add_months_clamps_to_the_last_day() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_cell_errors_flags_a_banned_host() -> None:
    clean = make_cell()
    assert cell_errors(clean, ORDINANCE, TAXONOMY, jurisdiction(), load_denylist()) == []
    url = "https://library.municode.com/example/code"
    banned = make_cell()
    banned["source"] = {**banned["source"], "url": url}
    assert cell_errors(banned, ORDINANCE, TAXONOMY, jurisdiction(), load_denylist()) == [
        f"us-00000/I-2/warehouse_distribution: banned host: {url}"
    ]
