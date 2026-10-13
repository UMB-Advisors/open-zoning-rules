"""Release-directory gates over the synthetic fixture."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from ozr.contract import check_answer, to_record
from ozr.gates import release_errors

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "tests/fixtures/release"
TEXTS = ROOT / "tests/fixtures/texts"
BAD = ROOT / "tests/fixtures/bad"
GATES = {
    "bad_quote.json": "quote not found in source",
    "missing_section.json": "section not found in source",
    "banned_host.json": "banned host",
    "absence_unexplained.json": "absence gate: 'heavy industry' occurs 6 times in the code and 6 are not explained",
    "denylist_only_host.json": "banned host",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_release(tmp_path: Path) -> Path:
    target = tmp_path / "release"
    shutil.copytree(RELEASE, target)
    return target


def drop_keys(release: Path, keys: set[tuple[str, str, str]]) -> None:
    """Rewrite cells.json without the named keys and refresh its manifest hash."""
    cells_path = release / "cells.json"
    cells = json.loads(cells_path.read_text(encoding="utf-8"))
    kept = [cell for cell in cells if (cell["jurisdiction_id"], cell["district_code"], cell["use_class"]) not in keys]
    payload = json.dumps(kept, indent=2) + "\n"
    cells_path.write_text(payload, encoding="utf-8")
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    for item in manifest["files"]:
        if item["path"] == "cells.json":
            item["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_fixture_release_passes() -> None:
    assert release_errors(RELEASE, TEXTS) == []


@pytest.mark.parametrize("name", list(GATES))
def test_bad_cell_override_fails_named_gate(name: str) -> None:
    errors = release_errors(RELEASE, TEXTS, cell_overrides=[_load(BAD / name)])
    assert any(GATES[name] in error for error in errors)


def test_denylist_only_host_passes_contract_and_fails_release() -> None:
    cell = _load(BAD / "denylist_only_host.json")
    version = _load(RELEASE / "manifest.json")["version"]
    assert check_answer(to_record(cell, version)) == []
    errors = release_errors(RELEASE, TEXTS, cell_overrides=[cell])
    assert any("banned host" in error for error in errors)


def test_dropped_cell_fails_coverage(tmp_path: Path) -> None:
    release = _copy_release(tmp_path)
    drop_keys(release, {("us-00000", "I-1", "datacenter")})
    errors = release_errors(release, TEXTS)
    assert any("coverage" in error for error in errors)


def test_parcel_specific_confidence_b_fails() -> None:
    cells = json.loads((RELEASE / "cells.json").read_text(encoding="utf-8"))
    cell = next(item for item in cells if item["district_code"] == "PD-1")
    cell = {**cell, "confidence": "B"}
    errors = release_errors(RELEASE, TEXTS, cell_overrides=[cell])
    assert any("parcel_specific confidence is C" in error for error in errors)


def test_stale_checked_at_fails() -> None:
    cells = json.loads((RELEASE / "cells.json").read_text(encoding="utf-8"))
    cell = {**cells[0], "checked_at": "2025-01-01", "stale": False}
    errors = release_errors(RELEASE, TEXTS, cell_overrides=[cell])
    assert any("staleness" in error for error in errors)


def test_corrupted_manifest_hash_fails(tmp_path: Path) -> None:
    release = _copy_release(tmp_path)
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = "b" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    errors = release_errors(release, TEXTS)
    assert any("hash" in error for error in errors)
