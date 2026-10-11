"""Offline mutation checks for table-symbol sensitivity."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from ozr.gates import TABLE_TEXT_MARKER
from ozr.models import ModelResult
from ozr.mutation import SYMBOLS, _copy_root, _replace_pages, flip_map, mutate, run


def test_mutate_is_seeded_and_leaves_prose_symbols_alone() -> None:
    text = "Prose mentions a lone P but is not a table.\nWarehouse | I-1 | P\nOther P C SE\n"

    first, flips = mutate(text, random.Random(4), 2)
    second, again = mutate(text, random.Random(4), 2)

    assert first == second
    assert flips == again
    assert first.splitlines()[0] == "Prose mentions a lone P but is not a table."
    assert all(flip["line_before"] != flip["line_after"] for flip in flips)


def test_flip_map_uses_the_tables_own_conditional_symbol() -> None:
    symbols = flip_map(["Use1 P C P\nUse2 C C P\n"])
    assert symbols["P"] == "C"
    assert symbols["C"] == "P"
    assert flip_map(["Use1 P SE S | x\nUse2 S S P | x\n"])["P"] == "S"
    assert flip_map(["Use1 P X PS\n"]) == SYMBOLS


def test_targeted_mutate_flips_only_rows_holding_a_target_label() -> None:
    filler = "".join(f"Use{index} | P | SE | P\n" for index in range(20))
    text = filler + "Warehouse | P | C | SE\n"

    targeted, flips = mutate(text, random.Random(0), 1, targets={"Warehouse"})
    untargeted, untargeted_flips = mutate(text, random.Random(0), 1)

    changed_lines = [
        (before, after)
        for before, after in zip(text.splitlines(), targeted.splitlines(), strict=True)
        if before != after
    ]
    assert changed_lines == [("Warehouse | P | C | SE", "Warehouse | SE | P | P")]
    assert len(flips) == 3
    assert {flip["line_before"] for flip in flips} == {"Warehouse | P | C | SE"}
    assert untargeted_flips == [
        {
            "line_no": 19,
            "line_before": "Use18 | P | SE | P",
            "line_after": "Use18 | SE | SE | P",
            "from": "P",
            "to": "SE",
        }
    ]
    assert "Use18 | SE | SE | P" in untargeted


def test_mutate_leaves_dotted_citations_alone() -> None:
    text = "Wholesale and P P P Sec.3.01.02.C.24 F.S.\nIndustrial, Heavy C P, P, Sec.\n"

    mutated, flips = mutate(text, random.Random(0), 2, targets={"Wholesale and", "Industrial, Heavy"})

    assert "Sec.3.01.02.C.24 F.S." in mutated
    assert "Wholesale and SE SE SE Sec.3.01.02.C.24 F.S." in mutated
    assert "Industrial, Heavy P SE, SE, Sec." in mutated
    assert len(flips) == 6


def _mutation_root(tiny_root: Path, filler_rows: int = 0, conditional_symbol: str = "SE") -> Path:
    base = tiny_root / "jurisdictions" / "us-00000"
    filler = "".join(f"Filler{index} | P | {conditional_symbol} | P\n" for index in range(filler_rows))
    table = "Use | I-1 | I-2 | I-3\n" + filler + "Warehouse | P | P | P\n"
    raw = "Sec. 4-2\nSec. 4-3\nAny use not listed in Table 4-2 is prohibited.\n"
    segment = "=== us-00000-zo page 1 ===\n" + raw + "\n[reconstructed table text]\n" + table
    path = tiny_root / "cache" / "segments" / "us-00000" / "use_table-us-00000-zo.txt"
    path.parent.mkdir(parents=True)
    path.write_text(segment, encoding="utf-8")
    source = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    source.parent.mkdir(parents=True)
    source.write_text(raw + TABLE_TEXT_MARKER + "[page 1]\n" + table, encoding="utf-8")
    (base / "segments.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "kind": "use_table",
                        "source_id": "us-00000-zo",
                        "text": "segments/us-00000/use_table-us-00000-zo.txt",
                        "images": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return base


def _response(status: str, conditional_symbol: str = "SE") -> ModelResult:
    symbol = "P" if status == "permitted" else conditional_symbol
    return ModelResult(
        json.dumps(
            {
                "cells": [
                    {
                        "district_code": "I-1",
                        "use_class": "warehouse_distribution",
                        "status": status,
                        "source_id": "us-00000-zo",
                        "local_uses": ["Warehouse"],
                        "evidence": {
                            "kind": "table",
                            "quote": f"Warehouse | I-1 | {symbol}",
                            "section": "Sec. 4-2",
                            "row_label": "Warehouse",
                            "column_header": "I-1",
                            "symbol": symbol,
                        },
                    }
                ]
            }
        ),
        "fake",
        1,
        1,
        0,
        0,
        0.0,
        0.0,
        {},
    )


def _absence_response() -> ModelResult:
    return ModelResult(
        json.dumps(
            {
                "cells": [
                    {
                        "district_code": "I-1",
                        "use_class": "lp_gas",
                        "status": "unlisted",
                        "source_id": "us-00000-zo",
                        "local_uses": [],
                        "evidence": {
                            "kind": "absence",
                            "quote": "Any use not listed in Table 4-2 is prohibited.",
                            "section": "Sec. 4-3",
                        },
                    }
                ]
            }
        ),
        "fake",
        1,
        1,
        0,
        0,
        0.0,
        0.0,
        {},
    )


def test_run_mirrors_flips_into_both_text_layers(tiny_root: Path) -> None:
    _mutation_root(tiny_root)
    raw_page = "Sec. 4-2\nWarehouse | I-1 | P"
    table_page = "Warehouse | P"
    segment_path = tiny_root / "cache" / "segments" / "us-00000" / "use_table-us-00000-zo.txt"
    segment_path.write_text(
        "=== us-00000-zo page 1 ===\n" + raw_page + "\n\n[reconstructed table text]\n" + table_page,
        encoding="utf-8",
    )
    source_path = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    source_path.write_text(raw_page + TABLE_TEXT_MARKER + "[page 1]\n" + table_page, encoding="utf-8")

    target = tiny_root / "target"
    _copy_root(tiny_root, target, "us-00000")
    _replace_pages(tiny_root, target, "us-00000", random.Random(0), 2, targets={"Warehouse"})

    mutated_source = (target / "cache" / "text" / "us-00000-zo.txt").read_text(encoding="utf-8")
    raw_layer, table_layer = mutated_source.split(TABLE_TEXT_MARKER)
    assert raw_layer == "Sec. 4-2\nWarehouse | I-1 | SE"
    assert table_layer == "[page 1]\nWarehouse | SE"
    assert len(mutated_source.split(TABLE_TEXT_MARKER)) == 2

    missing_table_target = tiny_root / "missing-table-target"
    _copy_root(tiny_root, missing_table_target, "us-00000")
    missing_source = missing_table_target / "cache" / "text" / "us-00000-zo.txt"
    missing_source.write_text(raw_page, encoding="utf-8")
    with pytest.raises(ValueError, match="source us-00000-zo page 1"):
        _replace_pages(tiny_root, missing_table_target, "us-00000", random.Random(0), 2, targets={"Warehouse"})


def test_run_detects_an_extractor_that_reads_the_mutated_symbol(tiny_root: Path) -> None:
    _mutation_root(tiny_root)

    def reads_table(prompt, _images, _workdir):
        return _response("conditional" if "Warehouse | SE" in prompt else "permitted")

    result = run(tiny_root, "us-00000", reads_table, n=1, seed=0, today="2026-10-10")

    assert result["result"] == "changed"
    assert result["flips_detected"] > 0


def test_run_targets_the_cited_row_and_reports_a_noise_floor(tiny_root: Path) -> None:
    _mutation_root(tiny_root, filler_rows=30)

    def reads_table(prompt, _images, _workdir):
        return _response("conditional" if "Warehouse | SE" in prompt else "permitted")

    result = run(tiny_root, "us-00000", reads_table, n=1, seed=0, today="2026-10-10")

    assert result["targeted"] is True
    assert result["rows_flipped"] == 1
    assert result["flipped_cells"] == 1
    assert result["flipped_cells_changed"] == 1
    assert result["detection_rate"] == 1.0
    assert result["cells"] == [
        {
            "key": "us-00000/I-1/warehouse_distribution",
            "before": "permitted",
            "after": "conditional",
            "flipped": True,
            "outcome": "to_conditional",
        }
    ]


def test_run_reports_unchanged_for_an_extractor_that_ignores_text(tiny_root: Path) -> None:
    _mutation_root(tiny_root)

    def ignores_table(_prompt, _images, _workdir):
        return _absence_response()

    result = run(tiny_root, "us-00000", ignores_table, n=1, seed=0, today="2026-10-10")

    assert result["result"] == "unchanged"


def test_run_counts_only_expected_direction_moves(tiny_root: Path) -> None:
    _mutation_root(tiny_root, filler_rows=30, conditional_symbol="C")

    def reads_c_table(prompt, _images, _workdir):
        return _response("conditional" if "Warehouse | C" in prompt else "permitted", "C")

    result = run(tiny_root, "us-00000", reads_c_table, n=1, seed=0, today="2026-10-10")

    assert result["flips"][0]["to"] == "C"
    assert result["flipped_outcomes"]["to_conditional"] == 1
    assert result["expected_rate"] == 1.0

    def drops_mutated_cell(prompt, _images, _workdir):
        if "Warehouse | C" in prompt:
            return ModelResult(json.dumps({"cells": []}), "fake", 1, 1, 0, 0, 0.0, 0.0, {})
        return _response("permitted", "C")

    result = run(tiny_root, "us-00000", drops_mutated_cell, n=1, seed=0, today="2026-10-10")

    assert result["flipped_outcomes"]["dropped"] == 1
    assert result["expected_direction"] == 0
    assert result["expected_rate"] == 0.0
