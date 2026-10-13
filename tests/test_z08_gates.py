"""Z08 evidence-gate regressions against synthetic and known extractor cells."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ozr.contamination import load_denylist
from ozr.gates import absence_errors, absence_hits, cell_errors, quote_errors, section_errors, term_in

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "tests" / "fixtures" / "known_cells"
CELLS = json.loads((FIXTURES / "cells.json").read_text(encoding="utf-8"))
DENYLIST = load_denylist()


def _unlisted(use_class: str, hits: list[dict] | None = None) -> dict:
    cell = {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": use_class,
        "status": "unlisted",
        "evidence": {"kind": "absence", "quote": "Uses", "section": "Sec. 1"},
        "source": {"url": "https://planning.example.org/code"},
    }
    if hits is not None:
        cell["absence_hits"] = hits
    return cell


def _table(symbol: str = "P", status: str = "permitted", quote: str | None = None) -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": "warehouse_distribution",
        "status": status,
        "evidence": {
            "kind": "table",
            "quote": quote or f"Warehouse | I-1 | {symbol}",
            "section": "Sec. 1",
            "row_label": "Warehouse",
            "column_header": "I-1",
            "symbol": symbol,
        },
        "source": {"url": "https://planning.example.org/code"},
    }


def _key(*entries: dict) -> dict:
    return {"jurisdiction_id": "us-00000", "unlisted_rule": "none", "table_key": list(entries)}


def test_term_matching_normalizes_hyphens_and_plural_y() -> None:
    assert "electric generating facility" in absence_hits(
        "Electric generating facilities | P", "utility_generation", TAXONOMY
    )
    assert absence_errors(
        _unlisted("utility_generation"), "Electric generating facilities | P", TAXONOMY, {"unlisted_rule": "none"}
    )
    assert "LP gas" in absence_hits("LP-gas and natural gas storage", "lp_gas", TAXONOMY)
    assert "LP-gas" in absence_hits("LP gas storage", "lp_gas", TAXONOMY)
    assert term_in("Heavy-Industry district", "heavy industry")


def test_token_bounded_table_labels_and_sections() -> None:
    cell = _table()
    cell["evidence"] = {**cell["evidence"], "column_header": "A", "section": "Sec. 4"}
    text = "Sec. 40 Uses\nAB\nWarehouse | AB | P"
    assert "us-00000/I-1/warehouse_distribution: column header not found in source" in quote_errors(cell, text)
    assert section_errors(cell, text) == ["us-00000/I-1/warehouse_distribution: section not found in source"]


def test_table_quote_shape_symbol_key_and_blank_symbol_key() -> None:
    grid = "Sec. 1\n=== reconstructed table text (from PDF rulings) ===\nUse | I-1\nWarehouse | P"
    bad_shape = _table(quote="Warehouse | I-1 | INVENTED")
    assert any("table quote is not" in error for error in cell_errors(bad_shape, grid, TAXONOMY, _key(), DENYLIST))
    invented = _table("INVENTED")
    assert any("does not map" in error for error in cell_errors(invented, grid, TAXONOMY, _key(), DENYLIST))
    blank_grid = "Sec. 1\n=== reconstructed table text (from PDF rulings) ===\nUse | I-1\nWarehouse | "
    blank = _table("", "prohibited")
    assert any("does not map" in error for error in cell_errors(blank, blank_grid, TAXONOMY, _key(), DENYLIST))
    key = _key({"symbol": "", "status": "prohibited", "quote": "No symbol means prohibited", "section": "Sec. 1"})
    assert not any(
        "does not map" in error
        for error in cell_errors(blank, blank_grid + "\nNo symbol means prohibited", TAXONOMY, key, DENYLIST)
    )


def test_reconstructed_grid_catches_known_douglas_cells() -> None:
    text = (FIXTURES / "us-13097-udc.excerpt.txt").read_text(encoding="utf-8")
    key = {
        "jurisdiction_id": "us-13097",
        "unlisted_rule": "none",
        "table_key": [
            {
                "symbol": "S",
                "status": "conditional",
                "quote": "S Use Requires Special Use Approval",
                "section": "Table 2.2",
            },
            {
                "symbol": "P",
                "status": "permitted",
                "quote": "P Use is Allowed by Right in the District Indicated",
                "section": "Table 2.2",
            },
            {
                "symbol": "",
                "status": "prohibited",
                "quote": "Use is not Allowed if no symbol appears",
                "section": "Table 2.2",
            },
        ],
    }
    for name in ("us-13097/OI/datacenter", "us-13097/C-H/datacenter"):
        assert any("table grid:" in error for error in cell_errors(CELLS[name], text, TAXONOMY, key, DENYLIST))
    positive = copy.deepcopy(CELLS["us-13097/C-H/datacenter"])
    positive["district_code"] = "LI"
    positive["evidence"].update({"column_header": "LI", "quote": positive["evidence"]["row_label"] + " | LI | S"})
    assert not any("table grid:" in error for error in cell_errors(positive, text, TAXONOMY, key, DENYLIST))


def test_absence_explanations_cover_each_occurrence() -> None:
    text = (FIXTURES / "us-51143-zo-ch35.excerpt.txt").read_text(encoding="utf-8")
    m2 = CELLS["us-51143/M-2/datacenter"]
    assert any(
        "absence gate: 'data center'" in error
        for error in absence_errors(m2, text, TAXONOMY, {"unlisted_rule": "none"})
    )
    bess = _unlisted(
        "battery_storage", [{"term": "BESS", "quote": "Bessemer Road", "section": "Sec. 1", "reason": "Road."}]
    )
    assert any(
        "absence gate: 'BESS'" in error
        for error in absence_errors(bess, "BESS\nBessemer Road", TAXONOMY, {"unlisted_rule": "none"})
    )
    covered = _unlisted(
        "battery_storage",
        [{"term": "BESS", "quote": "BESS is not this use", "section": "Sec. 1", "reason": "Context."}],
    )
    assert absence_errors(covered, "BESS is not this use", TAXONOMY, {"unlisted_rule": "none"}) == []


def test_cell_errors_uses_jurisdiction_absence_text() -> None:
    errors = cell_errors(
        _unlisted("utility_generation"),
        "Sec. 1 Uses",
        TAXONOMY,
        {"unlisted_rule": "none"},
        DENYLIST,
        absence_text="Electric generating facilities",
    )
    assert any("absence gate: 'electric generating facility'" in error for error in errors)
