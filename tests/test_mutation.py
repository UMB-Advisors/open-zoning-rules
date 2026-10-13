"""Offline mutation checks for table-symbol sensitivity."""

from __future__ import annotations

import json
import random
from pathlib import Path

from ozr.models import ModelResult
from ozr.mutation import mutate, run


def test_mutate_is_seeded_and_leaves_prose_symbols_alone() -> None:
    text = "Prose mentions a lone P but is not a table.\nWarehouse | I-1 | P\nOther P C SE\n"

    first, flips = mutate(text, random.Random(4), 2)
    second, again = mutate(text, random.Random(4), 2)

    assert first == second
    assert flips == again
    assert first.splitlines()[0] == "Prose mentions a lone P but is not a table."
    assert all(flip["line_before"] != flip["line_after"] for flip in flips)


def _mutation_root(tiny_root: Path) -> Path:
    base = tiny_root / "jurisdictions" / "us-00000"
    text = "Sec. 4-2\nWarehouse | I-1 | P\n"
    segment = "=== us-00000-zo page 1 ===\n" + text
    path = tiny_root / "cache" / "segments" / "us-00000" / "use_table-us-00000-zo.txt"
    path.parent.mkdir(parents=True)
    path.write_text(segment, encoding="utf-8")
    source = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    source.parent.mkdir(parents=True)
    source.write_text(text, encoding="utf-8")
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


def _response(status: str) -> ModelResult:
    symbol = "P" if status == "permitted" else "SE"
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


def test_run_detects_an_extractor_that_reads_the_mutated_symbol(tiny_root: Path) -> None:
    _mutation_root(tiny_root)

    def reads_table(prompt, _images, _workdir):
        return _response("conditional" if "Warehouse | I-1 | SE" in prompt else "permitted")

    result = run(tiny_root, "us-00000", reads_table, n=1, seed=0, today="2026-10-10")

    assert result["result"] == "changed"
    assert result["flips_detected"] > 0


def test_run_reports_unchanged_for_an_extractor_that_ignores_text(tiny_root: Path) -> None:
    _mutation_root(tiny_root)

    def ignores_table(_prompt, _images, _workdir):
        return _response("permitted")

    result = run(tiny_root, "us-00000", ignores_table, n=1, seed=0, today="2026-10-10")

    assert result["result"] == "unchanged"
