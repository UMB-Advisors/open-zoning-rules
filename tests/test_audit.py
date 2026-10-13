"""Tests for the blind published-cell audit sampler."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ozr.audit import HEADER, draw, write_sheet


def _cell(jid: str, district: str, use: str, status: str) -> dict:
    return {
        "jurisdiction_id": jid,
        "district_code": district,
        "use_class": use,
        "status": status,
        "source": {"url": f"https://example.test/{jid}"},
        "evidence": {"section": f"Section {district}", "quote": f"{jid} {district} {use} quote"},
        "confidence": "B",
        "review": "agree",
    }


def _root(tmp_path: Path, counts: dict[str, int]) -> tuple[Path, list[dict]]:
    cells: list[dict] = []
    for index, jid in enumerate(("aa", "bb", "cc")):
        rows = []
        for status, count in counts.items():
            for number in range(count):
                cell = _cell(jid, f"D{index}{number}", f"{status}_{number}", status)
                rows.append(cell)
                cells.append(cell)
        path = tmp_path / "jurisdictions" / jid / "cells.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    return tmp_path, cells


def test_seed_controls_selection(tmp_path: Path) -> None:
    root, _ = _root(tmp_path, {status: 4 for status in ("permitted", "conditional", "prohibited", "unlisted")})
    first = draw(root, ["aa", "bb", "cc"], n=8, seed=1)
    assert first == draw(root, ["aa", "bb", "cc"], n=8, seed=1)
    assert first != draw(root, ["aa", "bb", "cc"], n=8, seed=2)


def test_rows_and_csv_are_blind_and_have_only_header(tmp_path: Path) -> None:
    root, cells = _root(tmp_path, {"permitted": 2, "conditional": 2, "prohibited": 2, "unlisted": 2})
    rows = draw(root, ["aa", "bb", "cc"], n=8)
    path = tmp_path / "audit.csv"
    write_sheet(rows, path)
    with path.open(newline="", encoding="utf-8") as input_file:
        csv_rows = list(csv.DictReader(input_file))
    assert tuple(csv_rows[0]) == HEADER
    assert all(set(row) == set(HEADER) for row in rows)
    values = {value for row in csv_rows for value in row.values()}
    assert not values & {"permitted", "conditional", "prohibited", "unlisted"}
    assert not values & {cell["evidence"]["quote"] for cell in cells}
    assert all(row["human_status"] == "" for row in csv_rows)


def test_stratifies_and_round_robins_jurisdictions(tmp_path: Path) -> None:
    root, cells = _root(tmp_path, {status: 2 for status in ("permitted", "conditional", "prohibited", "unlisted")})
    status_for_key = {
        f"{cell['jurisdiction_id']}/{cell['district_code']}/{cell['use_class']}": cell["status"] for cell in cells
    }
    rows = draw(root, ["aa", "bb", "cc"], n=8)
    for status in ("permitted", "conditional", "prohibited", "unlisted"):
        sample = [row for row in rows if status_for_key[row["cell_key"]] == status]
        assert len(sample) == 2
        assert {row["jurisdiction_id"] for row in sample} == {"aa", "bb"}


def test_shortfall_redistributes_and_rows_are_sorted_unique(tmp_path: Path) -> None:
    root, cells = _root(tmp_path, {"permitted": 1, "conditional": 4, "prohibited": 4, "unlisted": 4})
    for jid in ("bb", "cc"):
        path = root / "jurisdictions" / jid / "cells.json"
        published = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps([cell for cell in published if cell["status"] != "permitted"]), encoding="utf-8")
    cells = [cell for cell in cells if cell["status"] != "permitted" or cell["jurisdiction_id"] == "aa"]
    rows = draw(root, ["aa", "bb", "cc"], n=8)
    keys = [row["cell_key"] for row in rows]
    statuses = {
        f"{cell['jurisdiction_id']}/{cell['district_code']}/{cell['use_class']}": cell["status"] for cell in cells
    }
    assert len(rows) == 8
    assert any(statuses[key] == "permitted" for key in keys)
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def test_quota_larger_than_jurisdiction_count_is_filled(tmp_path: Path) -> None:
    root, cells = _root(tmp_path, {status: 5 for status in ("permitted", "conditional", "prohibited", "unlisted")})
    status_for_key = {
        f"{cell['jurisdiction_id']}/{cell['district_code']}/{cell['use_class']}": cell["status"] for cell in cells
    }
    rows = draw(root, ["aa", "bb", "cc"], n=40)
    assert len(rows) == 40
    for status in ("permitted", "conditional", "prohibited", "unlisted"):
        assert sum(status_for_key[row["cell_key"]] == status for row in rows) == 10
