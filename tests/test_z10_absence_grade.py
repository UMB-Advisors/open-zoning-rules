"""Regression coverage for Z10 absence and grading gates."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from ozr.contamination import load_denylist
from ozr.gates import OCR_TEXT_MARKER, absence_errors, jurisdiction_text

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads((ROOT / "taxonomy" / "v1.json").read_text(encoding="utf-8"))
DENYLIST = load_denylist()
NONE = {"unlisted_rule": "none"}


def _unlisted(use_class: str) -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": "I-1",
        "use_class": use_class,
        "status": "unlisted",
        "evidence": {"kind": "absence", "quote": "Uses", "section": "Sec. 1"},
        "source": {"url": "https://planning.example.org/code"},
    }


def test_jurisdiction_text_requires_declared_source_text(tmp_path: Path) -> None:
    from ozr.gates import MissingSourceText

    (tmp_path / "a.txt").write_text("a")
    with pytest.raises(MissingSourceText):
        jurisdiction_text(tmp_path, ["a", "b"])
    assert jurisdiction_text(tmp_path, ["a", "b"], exempt={"b"}) == "a"


def test_jurisdiction_text_boundary_prevents_cross_source_term(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Sec. 1 Uses permitted: offices and big data")
    (tmp_path / "b.txt").write_text("center of town is a place.")
    assert absence_errors(_unlisted("datacenter"), jurisdiction_text(tmp_path, ["a", "b"]), TAXONOMY, NONE) == []


def test_absence_hit_requires_its_section() -> None:
    cell = _unlisted("datacenter")
    cell["absence_hits"] = [
        {"term": "data center", "quote": "no data center use is listed", "section": "Sec. 99-999", "reason": "x"}
    ]
    text = "Sec. 1 Uses. Note: no data center use is listed."
    assert absence_errors(cell, text, TAXONOMY, NONE)
    cell["absence_hits"][0]["section"] = "Sec. 1"
    assert absence_errors(cell, text, TAXONOMY, NONE) == []


def test_coverage_errors_keeps_id_with_no_cells() -> None:
    from ozr.gates import coverage_errors

    assert coverage_errors(["R-1"], [], ["datacenter"], "us-00000") == ["us-00000/R-1/datacenter: missing cell"]


def test_gate_cells_allows_valid_candidate_after_rejected_duplicate(tiny_root: Path) -> None:
    from ozr.labels import gate_cells

    source = ROOT / "tests" / "fixtures" / "texts" / "us-00000-zo.txt"
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, text_dir / "us-00000-zo.txt")
    (text_dir / "us-00000-analyst.txt").write_text("")
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text())
    sources = json.loads((base / "sources.json").read_text())["sources"]
    sources_by_id = {source["source_id"]: source for source in sources}
    cells = json.loads((ROOT / "tests" / "fixtures" / "release" / "cells.json").read_text())
    good = next(
        cell for cell in cells if cell["district_code"] == "I-1" and cell["use_class"] == "warehouse_distribution"
    )
    accepted, _ = gate_cells(tiny_root, "us-00000", jurisdiction, sources_by_id, TAXONOMY, [dict(good)])
    assert len(accepted) == 1
    bad = {**good, "evidence": {**good["evidence"], "quote": "not in source"}}
    accepted, _ = gate_cells(tiny_root, "us-00000", jurisdiction, sources_by_id, TAXONOMY, [dict(bad), dict(good)])
    assert len(accepted) == 1


def test_release_absence_over_ocr_requires_grade_c(tiny_root: Path) -> None:
    from ozr.gates import _one_cell_errors

    cell = {
        **_unlisted("datacenter"),
        "confidence": "B",
        "review": "single",
        "source": {"id": "us-00000-zo", "url": "https://planning.example.org/zoning/ordinance.pdf"},
    }
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    (text_dir / "us-00000-zo.txt").write_text("Sec. 1 Uses")
    jurisdiction = json.loads((tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json").read_text())
    source = json.loads((tiny_root / "jurisdictions" / "us-00000" / "sources.json").read_text())["sources"][0]
    errors = _one_cell_errors(
        cell,
        text_dir,
        TAXONOMY,
        jurisdiction,
        DENYLIST,
        None,
        None,
        [],
        {source["source_id"]: source},
        {},
        OCR_TEXT_MARKER,
    )
    assert any("absence evidence over a code with an OCR layer" in error for error in errors)
    cell["confidence"] = "C"
    errors = _one_cell_errors(
        cell,
        text_dir,
        TAXONOMY,
        jurisdiction,
        DENYLIST,
        None,
        None,
        [],
        {source["source_id"]: source},
        {},
        OCR_TEXT_MARKER,
    )
    assert not any("absence evidence over a code with an OCR layer" in error for error in errors)


def test_grade_run_id_is_independent_of_clock(tiny_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ozr.grade import grade_jurisdiction

    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text())
    jurisdiction["districts"] = [jurisdiction["districts"][0]]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction))
    (tiny_root / "taxonomy" / "v1.json").write_text(json.dumps({"classes": [{"id": "warehouse_distribution"}]}))
    cell = next(
        cell
        for cell in json.loads((ROOT / "tests" / "fixtures" / "release" / "cells.json").read_text())
        if cell["district_code"] == "I-1" and cell["use_class"] == "warehouse_distribution"
    )
    for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json"):
        (base / name).write_text(json.dumps({"cells": [cell], "rejected": []}))
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "tests" / "fixtures" / "texts" / "us-00000-zo.txt", text_dir / "us-00000-zo.txt")
    (text_dir / "us-00000-analyst.txt").write_text("")
    monkeypatch.setattr("ozr.grade.utc_now", lambda: "2026-01-01T00:00:00Z")
    grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")
    first = json.loads((base / "cells.withheld.json").read_text())["run_id"]
    monkeypatch.setattr("ozr.grade.utc_now", lambda: "2027-01-01T00:00:00Z")
    grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")
    assert json.loads((base / "cells.withheld.json").read_text())["run_id"] == first


def _amendment() -> dict:
    return {
        "id": "us-51107-zoam-2024-0001",
        "reference": "ZOAM-2024-0001",
        "jurisdiction_id": "us-51107",
        "kind": "adopted_text_amendment",
        "status": "adopted",
        "dates": {"adopted": "2025-03-18"},
        "use_classes": ["datacenter"],
        "districts": ["IP", "GI", "MRHI"],
        "quote": (
            "requiring Special Exception (SPEX) approval for data center uses in the Industrial Park (IP), "
            "General Industry (GI), and Mineral Resources-Heavy Industry (MR-HI) zoning districts"
        ),
        "section": "ZOAM-2024-0001",
        "source": {
            "id": "us-51107-dc-phase1",
            "url": "https://www.loudoun.gov/6221/Phase-1-Project-Plan-for-Data-Center-Sta",
        },
    }


def _loudoun_cell() -> dict:
    cell = next(
        cell
        for cell in json.loads((ROOT / "jurisdictions" / "us-51107" / "cells.extracted.json").read_text())["cells"]
        if cell["district_code"] == "MRHI" and cell["use_class"] == "datacenter"
    )
    return {**cell, "confidence": "C", "review": "single"}


def test_release_detects_superseded_loudoun_cell(tmp_path: Path) -> None:
    from ozr.gates import release_errors

    release = tmp_path / "release"
    shutil.copytree(ROOT / "releases" / "v0.1.0", release)
    (release / "amendments.json").write_text(json.dumps([_amendment()]))
    text_dir = ROOT / "cache" / "text" if (ROOT / "cache" / "text").is_dir() else tmp_path / "text"
    errors = release_errors(release, text_dir, cell_overrides=[_loudoun_cell()])
    assert any(
        "superseded" in error and "ZOAM-2024-0001" in error and "us-51107/MRHI/datacenter" in error for error in errors
    )


def test_superseded_errors_dates_and_incorporation() -> None:
    from ozr.gates import superseded_errors

    cell, amendment = _loudoun_cell(), _amendment()
    jurisdiction = json.loads((ROOT / "jurisdictions" / "us-51107" / "jurisdiction.json").read_text())
    sources = {
        source["source_id"]: source
        for source in json.loads((ROOT / "jurisdictions" / "us-51107" / "sources.json").read_text())["sources"]
    }
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "")
    cell["source"] = {**cell["source"], "id": "us-51107-dc-phase1"}
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "") == []
    cell = _loudoun_cell()
    cell["district_code"] = "OP"
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "") == []
    cell = _loudoun_cell()
    sources[cell["source"]["id"]] = {**sources[cell["source"]["id"]], "source_date": "2025-03-19"}
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "") == []
    sources[cell["source"]["id"]] = {**sources[cell["source"]["id"]], "source_date": "unknown"}
    jurisdiction = {**jurisdiction, "code_version": "unknown"}
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "")
    amendment["incorporated_in"] = [{"source_id": cell["source"]["id"], "quote": "amendment text"}]
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "amendment text") == []
    assert superseded_errors(cell, [amendment], sources, jurisdiction, "other text")
