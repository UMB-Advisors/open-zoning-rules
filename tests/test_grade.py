"""Offline tests for publication grading."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator
from ozr.grade import grade_jurisdiction

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures"


def _cell(use_class: str, district: str = "I-1") -> dict:
    cells = json.loads((FIXTURE / "release" / "cells.json").read_text(encoding="utf-8"))
    return next(cell for cell in cells if cell["district_code"] == district and cell["use_class"] == use_class)


def _write(path: Path, cells: list[dict]) -> None:
    path.write_text(json.dumps({"cells": cells, "rejected": [], "missing": []}), encoding="utf-8")


def test_grade_applies_review_staleness_and_publication_gates(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    jurisdiction["case_lookup_url"] = "https://planning.example.org/cases"
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / "texts" / "us-00000-zo.txt", text_dir / "us-00000-zo.txt")

    agree = _cell("warehouse_distribution")
    disputed = _cell("cannabis_cultivation_processing")
    single = _cell("lp_gas")
    withheld = _cell("utility_generation")
    parcel = _cell("warehouse_distribution", "PD-1")
    stale = {**_cell("battery_storage"), "checked_at": "2025-09-09"}
    pending = _cell("heavy_industrial_hazmat", "I-2")
    preempted = _cell("datacenter")
    invalid = {
        **_cell("heavy_industrial_hazmat"),
        "evidence": {**_cell("heavy_industrial_hazmat")["evidence"], "quote": "not in the ordinance"},
    }
    extracted = [agree, disputed, single, withheld, parcel, stale, pending, preempted, invalid]
    _write(base / "cells.extracted.json", extracted)
    _write(
        base / "cells.review.codex.json",
        [agree, disputed, single, parcel, stale, pending, preempted, invalid],
    )
    _write(
        base / "cells.review.grok.json",
        [
            agree,
            {**disputed, "status": "prohibited"},
            parcel,
            stale,
            pending,
            preempted,
            invalid,
        ],
    )
    (base / "amendments.json").write_text(
        json.dumps(
            [
                {
                    "kind": "moratorium",
                    "status": "active",
                    "use_classes": ["heavy_industrial_hazmat"],
                    "districts": ["I-2"],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")
    published = json.loads((base / "cells.json").read_text(encoding="utf-8"))
    by_class = {(cell["district_code"], cell["use_class"]): cell for cell in published}

    assert by_class[("I-1", "warehouse_distribution")]["confidence"] == "B"
    assert by_class[("I-1", "warehouse_distribution")]["review"] == "agree"
    assert by_class[("I-1", "cannabis_cultivation_processing")]["review"] == "disputed"
    assert by_class[("I-1", "cannabis_cultivation_processing")]["confidence"] == "C"
    assert by_class[("I-1", "lp_gas")]["review"] == "single"
    assert by_class[("I-1", "lp_gas")]["confidence"] == "C"
    assert by_class[("PD-1", "warehouse_distribution")]["confidence"] == "C"
    assert by_class[("PD-1", "warehouse_distribution")]["see_case"] == jurisdiction["case_lookup_url"]
    assert by_class[("I-1", "battery_storage")]["stale"] is True
    assert by_class[("I-1", "battery_storage")]["confidence"] == "C"
    assert by_class[("I-2", "heavy_industrial_hazmat")]["stale"] is True
    assert by_class[("I-2", "heavy_industrial_hazmat")]["confidence"] == "C"
    assert by_class[("I-1", "datacenter")]["preemption"] == {
        "state_rule_id": "zz-datacenter",
        "effect": "state_siting_exclusive",
    }
    assert result["published"] == len(published)
    assert any(item["key"].endswith("/utility_generation") for item in result["withheld"])
    assert any("row label not in quote" in str(item["reason"]) for item in result["withheld"])

    validator = Draft202012Validator(
        json.loads((tiny_root / "schema" / "record.schema.json").read_text(encoding="utf-8"))
    )
    assert [error.message for cell in published for error in validator.iter_errors(cell)] == []
