"""Parity with the consumer contract zoning-atlas.release/0.1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ozr.contract import check_answer, check_release, to_record

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/contract_parity/cases.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((ROOT / "tests/fixtures/contract_parity/expected.json").read_text(encoding="utf-8"))


def _by_name(items: list[dict]) -> dict[str, dict]:
    return {item["name"]: item for item in items}


ANSWERS = _by_name(CASES["answers"])
ANSWER_EXPECTED = _by_name(EXPECTED["answers"])
MANIFESTS = _by_name(CASES["manifests"])
MANIFEST_EXPECTED = _by_name(EXPECTED["manifests"])


@pytest.mark.parametrize("name", [item["name"] for item in EXPECTED["answers"]])
def test_check_answer_matches_consumer_contract(name: str) -> None:
    assert check_answer(ANSWERS[name]["input"]) == ANSWER_EXPECTED[name]["errors"]


@pytest.mark.parametrize("name", [item["name"] for item in EXPECTED["manifests"]])
def test_check_release_matches_consumer_contract(name: str) -> None:
    assert check_release(MANIFESTS[name]["input"]) == MANIFEST_EXPECTED[name]["errors"]


def test_fixture_cell_passes_check_answer() -> None:
    cells = json.loads((ROOT / "tests/fixtures/release/cells.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "tests/fixtures/release/manifest.json").read_text(encoding="utf-8"))
    for cell in cells:
        assert check_answer(to_record(cell, manifest["version"])) == []
