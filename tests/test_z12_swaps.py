"""Regression coverage for Z0.12 policy swaps."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from ozr.__main__ import main
from ozr.common import jurisdiction_ids
from ozr.contamination import check_url, host_banned, load_denylist
from ozr.gates import release_errors
from ozr.grade import grade_jurisdiction

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures"
RELEASE = FIXTURE / "release"
TEXTS = FIXTURE / "texts"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _jurisdiction(jid: str, **extra: object) -> dict:
    return {
        "jurisdiction_id": jid,
        "name": "Example County",
        "type": "county",
        "state": "ZZ",
        "unlisted_rule": "none",
        "code_version": "2026-10-11",
        "conditional_zoning_unmapped": False,
        "sources": ["source-1"],
        "districts": [
            {
                "district_code": "I",
                "district_name": "Industrial",
                "family": "industrial",
                "parcel_specific": False,
                "geometry_ref": {"path": "districts/i.json"},
            }
        ],
        **extra,
    }


def test_more_code_publishers_are_banned() -> None:
    denylist = load_denylist()
    hosts = {"encodeplus.com", "municipal.codes", "municipalcodeonline.com", "qcode.us"}
    assert hosts <= denylist
    assert all(host_banned(host, denylist) for host in hosts)
    assert check_url("https://library.qcode.us/lib/x", denylist)
    assert check_url("https://www.encodeplus.com/regs/x", denylist)
    assert check_url("https://x.municipal.codes/Code/1", denylist)
    assert check_url("https://www.municipalcodeonline.com/book", denylist)
    assert check_url("https://www.example.gov/code", denylist, lambda url: [url, "https://library.qcode.us/lib/x"])
    assert not check_url("https://www.notqcode.us.example.gov/x", denylist)


def test_retired_jurisdictions_are_not_selected_by_default(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    jurisdictions = (
        ("us-00000", {}),
        ("us-00001", {"retired": {"date": "2026-10-11", "reason": "x"}}),
        ("us-00002", {}),
    )
    for jid, extra in jurisdictions:
        _write_json(root / "jurisdictions" / jid / "jurisdiction.json", _jurisdiction(jid, **extra))

    assert jurisdiction_ids(root) == ["us-00000", "us-00002"]
    assert jurisdiction_ids(root, include_retired=True) == ["us-00000", "us-00001", "us-00002"]
    received: list[list[str]] = []
    monkeypatch.setattr(
        "ozr.__main__.importlib.import_module",
        lambda _: SimpleNamespace(cli=lambda args: received.append(args.jurisdiction_ids) or 0),
    )
    assert main(["grade", "--root", str(root), "--all"]) == 0
    assert received == [["us-00000", "us-00002"]]


def test_retired_schema_validation() -> None:
    schema = json.loads((ROOT / "schema" / "jurisdiction.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    valid = _jurisdiction("us-00000", retired={"date": "2026-10-11", "reason": "x"})
    assert list(validator.iter_errors(valid)) == []
    invalid = _jurisdiction("us-00000", retired={"date": "soon", "reason": "x"})
    assert list(validator.iter_errors(invalid))


def _fixture_cell(use_class: str) -> dict:
    cells = json.loads((RELEASE / "cells.json").read_text(encoding="utf-8"))
    return next(cell for cell in cells if cell["district_code"] == "I-1" and cell["use_class"] == use_class)


def _grade_draft(tiny_root: Path, *, draft: bool) -> dict:
    base = tiny_root / "jurisdictions" / "us-00000"
    jurisdiction = json.loads((base / "jurisdiction.json").read_text(encoding="utf-8"))
    if draft:
        jurisdiction["code_status"] = "unadopted_draft"
    _write_json(base / "jurisdiction.json", jurisdiction)
    text_dir = tiny_root / "cache" / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / "texts" / "us-00000-zo.txt", text_dir / "us-00000-zo.txt")
    cell = _fixture_cell("warehouse_distribution")
    for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json"):
        _write_json(base / name, {"cells": [cell], "rejected": [], "missing": []})
    grade_jurisdiction(tiny_root, "us-00000", "2026-10-11")
    cells = json.loads((base / "cells.json").read_text(encoding="utf-8"))
    return next(cell for cell in cells if cell["use_class"] == "warehouse_distribution")


def test_unadopted_draft_grade_cap(tiny_root: Path) -> None:
    normal_root = tiny_root.parent / "normal"
    shutil.copytree(tiny_root, normal_root)
    draft = _grade_draft(tiny_root, draft=True)
    assert draft["confidence"] == "C"
    assert draft["code_status"] == "unadopted_draft"

    normal = _grade_draft(normal_root, draft=False)
    assert normal["confidence"] == "B"
    assert "code_status" not in normal


def _draft_release(tmp_path: Path, *, draft: bool) -> tuple[Path, dict]:
    release = tmp_path / "release"
    shutil.copytree(RELEASE, release)
    jurisdictions = json.loads((release / "jurisdictions.json").read_text(encoding="utf-8"))
    if draft:
        jurisdictions[0]["code_status"] = "unadopted_draft"
    _write_json(release / "jurisdictions.json", jurisdictions)
    cell = json.loads((release / "cells.json").read_text(encoding="utf-8"))[0]
    return release, cell


def test_unadopted_draft_release_gate(tmp_path: Path) -> None:
    release, cell = _draft_release(tmp_path, draft=True)
    errors = release_errors(release, TEXTS, cell_overrides=[{**cell, "confidence": "B"}])
    assert any("unadopted draft: us-00000/I-1/datacenter: confidence is C" in error for error in errors)

    errors = release_errors(release, TEXTS, cell_overrides=[{**cell, "confidence": "C"}])
    assert any("unadopted draft: us-00000/I-1/datacenter: cell must carry" in error for error in errors)

    errors = release_errors(
        release, TEXTS, cell_overrides=[{**cell, "confidence": "C", "code_status": "unadopted_draft"}]
    )
    assert not any("unadopted draft: us-00000/I-1/datacenter:" in error for error in errors)

    ordinary_release, ordinary_cell = _draft_release(tmp_path / "ordinary", draft=False)
    errors = release_errors(
        ordinary_release,
        TEXTS,
        cell_overrides=[{**ordinary_cell, "code_status": "unadopted_draft"}],
    )
    assert any("cell carries code_status unadopted_draft without jurisdiction" in error for error in errors)
