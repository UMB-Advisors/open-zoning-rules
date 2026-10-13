"""Regression coverage for Z0.8 grade, release, measure, and regate changes."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ozr import release
from ozr.__main__ import main
from ozr.gates import release_errors
from ozr.grade import grade_jurisdiction
from ozr.measure import RELIANCE_NOTICE, measure

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures"


def _write(path: Path, cells: list[dict], rejected: list[dict] | None = None) -> None:
    path.write_text(json.dumps({"cells": cells, "rejected": rejected or [], "missing": []}), encoding="utf-8")


def _release_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for directory in ("taxonomy", "policy", "schema"):
        shutil.copytree(ROOT / directory, root / directory)
    base = root / "jurisdictions" / "us-00000"
    base.mkdir(parents=True)
    for name in ("jurisdictions.json", "sources.json", "cells.json"):
        value = json.loads((FIXTURE / "release" / name).read_text())
        if name == "jurisdictions.json":
            value, name = value[0], "jurisdiction.json"
        elif name == "sources.json":
            value = {"sources": [value["sources"][0]]}
        (base / name).write_text(json.dumps(value), encoding="utf-8")
    (root / "state_rules").mkdir()
    (root / "state_rules" / "ZZ.json").write_text((FIXTURE / "release" / "state_rules.json").read_text())
    statute = json.loads((FIXTURE / "release" / "sources.json").read_text())["sources"][1]
    (root / "state_rules" / "sources.json").write_text(json.dumps({"sources": [statute]}), encoding="utf-8")
    shutil.copytree(FIXTURE / "texts", root / "cache" / "text")
    (root / "reports").mkdir()
    (root / "reports" / "accuracy.json").write_text(json.dumps({"reliance_notice": RELIANCE_NOTICE}), encoding="utf-8")
    return root


def _refresh_hash(release_dir: Path, name: str) -> None:
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256((release_dir / name).read_bytes()).hexdigest()
    next(item for item in manifest["files"] if item["path"] == name)["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_grade_records_disputed_single_and_extraction_withholding(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / "texts" / "us-00000-zo.txt", text_dir / "us-00000-zo.txt")
    cells = json.loads((FIXTURE / "release" / "cells.json").read_text())
    extractor = next(
        cell for cell in cells if cell["use_class"] == "warehouse_distribution" and cell["district_code"] == "I-1"
    )
    rejected = {
        "cell": {**extractor, "use_class": "datacenter"},
        "errors": ["prior extraction error"],
        "run_id": "extract-old",
    }
    _write(base / "cells.extracted.json", [extractor], [rejected])
    _write(base / "cells.review.codex.json", [{**extractor, "status": "unlisted"}])
    _write(base / "cells.review.grok.json", [])

    grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")

    published = json.loads((base / "cells.json").read_text())
    assert published[0]["review"] == "disputed"
    withheld = json.loads((base / "cells.withheld.json").read_text())["withheld"]
    assert next(item for item in withheld if item["key"].endswith("/datacenter")) == {
        "key": "us-00000/I-1/datacenter",
        "gate": "extraction",
        "reason": ["prior extraction error"],
        "run_id": "extract-old",
    }


def test_release_coverage_accepts_only_matching_grade_withholding(tmp_path: Path) -> None:
    root = _release_root(tmp_path)
    assert release.build(root, published="2026-10-09") == []
    out = root / "releases" / "v0.1.0"
    key = "us-00000/I-1/datacenter"
    cells = json.loads((out / "cells.json").read_text())
    (out / "cells.json").write_text(
        json.dumps([cell for cell in cells if (cell["district_code"], cell["use_class"]) != ("I-1", "datacenter")])
    )
    _refresh_hash(out, "cells.json")
    assert any(
        "coverage: us-00000/I-1/datacenter: missing cell" in error
        for error in release_errors(out, root / "cache" / "text", root=root)
    )
    (out / "withheld.json").write_text(
        json.dumps([{"key": key, "gate": "grade", "reason": ["x"], "run_id": "grade-1"}])
    )
    _refresh_hash(out, "withheld.json")
    assert any(
        "withheld without a matching grade failure record" in error
        for error in release_errors(out, root / "cache" / "text", root=root)
    )
    (root / "jurisdictions" / "us-00000" / "cells.withheld.json").write_text(
        json.dumps({"withheld": [{"key": key, "gate": "grade", "reason": ["x"], "run_id": "grade-1"}]}),
        encoding="utf-8",
    )
    assert release_errors(out, root / "cache" / "text", root=root) == []
    (out / "cells.json").write_text(json.dumps(cells))
    _refresh_hash(out, "cells.json")
    assert any(
        "listed as withheld but published" in error for error in release_errors(out, root / "cache" / "text", root=root)
    )


def test_release_withheld_must_be_listed_in_manifest_files(tmp_path: Path) -> None:
    root = _release_root(tmp_path)
    assert release.build(root, published="2026-10-09") == []
    out = root / "releases" / "v0.1.0"
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = [entry for entry in manifest["files"] if entry["path"] != "withheld.json"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert "withheld: withheld.json is not listed in the manifest files" in release_errors(
        out, root / "cache" / "text", root=root
    )


def test_measure_source_text_difference_is_not_a_miss_and_precision_needs_predictions(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    taxonomy = {"classes": [{"id": "unlisted"}]}
    (tiny_root / "taxonomy" / "v1.json").write_text(json.dumps(taxonomy), encoding="utf-8")
    jurisdiction = json.loads((base / "jurisdiction.json").read_text())
    jurisdiction["districts"] = [{"district_code": f"D-{i}", "family": "industrial"} for i in range(50)]
    (base / "jurisdiction.json").write_text(json.dumps(jurisdiction), encoding="utf-8")
    cells = [
        {"jurisdiction_id": "us-00000", "district_code": f"D-{i}", "use_class": "unlisted", "status": "unlisted"}
        for i in range(50)
    ]
    _write(
        base / "cells.extracted.json", [{**cell, "status": "permitted"} if i else cell for i, cell in enumerate(cells)]
    )
    _write(base / "cells.review.codex.json", cells)
    _write(base / "cells.review.grok.json", cells)
    known = tiny_root / "known.json"
    known.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "source-diff",
                        "jurisdiction_id": "us-00000",
                        "district_code": "D-0",
                        "use_class": "unlisted",
                        "expected_status": "unlisted",
                        "source_text_status": "permitted",
                    }
                ]
            }
        )
    )

    report = measure(tiny_root, ["us-00000"], known)

    assert report["known_answer_misses"] == []
    assert report["known_answer_source_text_differences"][0]["id"] == "source-diff"
    assert report["known_answers"][0]["published_status"] is None
    assert report["gates"]["unlisted_precision"]["result"] == "insufficient data"


def test_regate_moves_bad_quote_without_model_calls(tiny_root: Path) -> None:
    from ozr.regate import regate_jurisdiction

    base = tiny_root / "jurisdictions" / "us-00000"
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / "texts" / "us-00000-zo.txt", text_dir / "us-00000-zo.txt")
    cells = json.loads((FIXTURE / "release" / "cells.json").read_text())
    good = next(
        cell for cell in cells if cell["use_class"] == "warehouse_distribution" and cell["district_code"] == "I-1"
    )
    bad = {
        **good,
        "use_class": "datacenter",
        "evidence": {"kind": "prose", "quote": "not in source", "section": good["evidence"]["section"]},
    }
    _write(base / "cells.extracted.json", [good, bad])

    result = regate_jurisdiction(tiny_root, "us-00000")

    document = json.loads((base / "cells.extracted.json").read_text())
    assert len(document["cells"]) == 1
    assert document["rejected"][0]["run_id"] == result["run_id"]
    assert any("quote not found in source" in error for error in document["rejected"][0]["errors"])


def test_main_dispatches_regate_and_audit_sheet(tiny_root: Path) -> None:
    assert main(["regate", "--root", str(tiny_root), "us-00000"]) == 0
    assert main(["audit", "--root", str(tiny_root), "us-00000", "--audit-sheet", "audit/new.v0.2.0.csv"]) == 0
    assert (tiny_root / "audit" / "new.v0.2.0.csv").is_file()
