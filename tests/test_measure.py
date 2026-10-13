"""Hand-checked panel-agreement measurement tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ozr.measure import RELIANCE_NOTICE, measure


def _write_cells(path: Path, cells: list[dict], rejected: int | list[dict] = 0) -> None:
    entries = [{} for _ in range(rejected)] if isinstance(rejected, int) else rejected
    path.write_text(json.dumps({"cells": cells, "rejected": entries, "missing": []}), encoding="utf-8")


def _cell(use_class: str, status: str) -> dict:
    return {"jurisdiction_id": "us-00000", "district_code": "I-1", "use_class": use_class, "status": status}


def test_measure_reports_hand_computed_metrics_known_answers_and_cost(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    jurisdiction["districts"] = [jurisdiction["districts"][0]]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    statuses = ["permitted", "permitted", "conditional", "conditional", "prohibited", "unlisted", "unlisted"]
    classes = [item["id"] for item in json.loads((tiny_root / "taxonomy" / "v1.json").read_text())["classes"]]
    codex = [_cell(use_class, status) for use_class, status in zip(classes, statuses, strict=True)]
    grok = [*codex[:-1], _cell(classes[-1], "permitted")]
    extractor = [*codex]
    extractor[3] = _cell(classes[3], "permitted")
    _write_cells(base / "cells.extracted.json", extractor, rejected=1)
    _write_cells(base / "cells.review.codex.json", codex, rejected=2)
    _write_cells(base / "cells.review.grok.json", grok, rejected=3)
    known = tiny_root / "known.json"
    known.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "matched",
                        "jurisdiction_id": "us-00000",
                        "district_code": "I-1",
                        "use_class": classes[0],
                        "expected_status": "permitted",
                        "source_text_status": "permitted",
                    },
                    {
                        "id": "missed",
                        "jurisdiction_id": "us-00000",
                        "district_code": "I-1",
                        "use_class": classes[3],
                        "expected_status": "conditional",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    runs = tiny_root / "runs"
    runs.mkdir()
    (runs / "us-00000.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"model": "one", "input_tokens": 10, "output_tokens": 5, "cost_usd": 1.5, "wall_s": 60}),
                json.dumps({"model": "two", "input_tokens": 3, "cost_usd": None, "wall_s": 30}),
            ]
        ),
        encoding="utf-8",
    )

    report = measure(tiny_root, ["us-00000"], known)

    # Gold = 6, disputed = 1. Listed matches = 4/5; recall = 1/1;
    # lower bound = 5/(6 + 1) = 5/7. Kappa = (6/7 - 13/49)/(1 - 13/49) = 29/36.
    assert report["listed_agreement"] == pytest.approx(4 / 5)
    assert report["unlisted_recall"] == pytest.approx(1)
    assert report["unlisted_precision"] == pytest.approx(1)
    assert report["disputed_share"] == pytest.approx(1 / 7)
    assert report["lower_bound"] == pytest.approx(5 / 7)
    assert report["kappa"] == pytest.approx(29 / 36)
    assert report["gates"]["listed_agreement"]["result"] == "insufficient data"
    assert report["gate_rejection_rate"] == {"extractor": 1 / 8, "codex": 2 / 9, "grok": 3 / 10}
    assert report["known_answers"][0]["match_expected"] is True
    assert report["known_answer_misses"][0]["id"] == "missed"
    assert report["cost"]["per_jurisdiction"]["us-00000"]["models"]["one"]["tokens"] == 15
    assert report["cost"]["per_jurisdiction"]["us-00000"]["models"]["two"]["cost_usd"] is None
    assert report["cost"]["per_jurisdiction"]["us-00000"]["cost_usd"] is None
    assert report["measure"] == "model-panel agreement"
    assert report["reliance_notice"] == RELIANCE_NOTICE
    assert "accuracy" not in json.dumps(report).lower()


def test_disputed_share_failure_overrides_other_sufficient_gates(tiny_root: Path) -> None:
    classes = ["permitted", "conditional", "prohibited", "unlisted"]
    (tiny_root / "taxonomy" / "v1.json").write_text(
        json.dumps({"classes": [{"id": value} for value in classes]}), encoding="utf-8"
    )
    districts = [{"district_code": f"D-{number}", "family": "industrial"} for number in range(60)]
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text())
    jurisdiction["districts"] = districts
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    extractor: list[dict] = []
    codex: list[dict] = []
    grok: list[dict] = []
    for district in districts:
        for status in classes:
            cell = {"jurisdiction_id": "us-00000", "district_code": district["district_code"], "use_class": status}
            codex.append({**cell, "status": status})
            grok.append(
                {
                    **cell,
                    "status": (
                        status
                        if int(district["district_code"].split("-")[1]) < 50
                        else "conditional"
                        if status == "permitted"
                        else "permitted"
                    ),
                }
            )
            extractor.append({**cell, "status": status})
    _write_cells(base / "cells.extracted.json", extractor)
    _write_cells(base / "cells.review.codex.json", codex)
    _write_cells(base / "cells.review.grok.json", grok)

    report = measure(tiny_root, ["us-00000"])

    # 40 disputed cells out of 240; every status still has 50 gold cells.
    assert report["disputed_share"] == pytest.approx(40 / 240)
    assert report["gates"]["disputed_share"]["result"] == "fail"
    for name in ("listed_agreement", "unlisted_recall", "unlisted_precision"):
        assert report["gates"][name]["result"] == "fail"
        assert report["gates"][name]["reason"] == "disputed share exceeds 0.15"


def test_measure_reports_rejected_reviewer_dissent_variants(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    jurisdiction["districts"] = [jurisdiction["districts"][0]]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    classes = [item["id"] for item in json.loads((tiny_root / "taxonomy" / "v1.json").read_text())["classes"]]
    extractor = [_cell(use_class, "permitted") for use_class in classes]
    grok = [*extractor]
    codex = extractor[2:]
    _write_cells(base / "cells.extracted.json", extractor)
    _write_cells(
        base / "cells.review.codex.json",
        codex,
        rejected=[
            {"cell": _cell(classes[0], "conditional")},
            {"cell": _cell(classes[1], "permitted")},
        ],
    )
    _write_cells(base / "cells.review.grok.json", grok)

    report = measure(tiny_root, ["us-00000"])

    assert report["disputed_share"] == pytest.approx(0)
    assert report["disputed_share_counting_rejected"] == pytest.approx(2 / len(classes))
    assert report["disputed_share_counting_rejected_differing"] == pytest.approx(1 / len(classes))
