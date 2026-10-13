"""Shared offline filesystem fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tiny_root(tmp_path: Path) -> Path:
    """Create a minimal repository root suitable for fetch and segment tests."""
    project = Path(__file__).resolve().parents[1]
    (tmp_path / "policy").mkdir()
    shutil.copy(project / "policy" / "denylist.txt", tmp_path / "policy" / "denylist.txt")
    shutil.copytree(project / "taxonomy", tmp_path / "taxonomy")
    shutil.copytree(project / "schema", tmp_path / "schema")
    jurisdiction = json.loads((project / "tests" / "fixtures" / "release" / "jurisdictions.json").read_text())[0]
    source = json.loads((project / "tests" / "fixtures" / "release" / "sources.json").read_text())["sources"][0]
    analyst = {**source, "source_id": "us-00000-analyst", "triage": "analyst_fetch"}
    jurisdiction["sources"] = [source["source_id"], analyst["source_id"]]
    for jid, state in (("us-00000", "ZZ"), ("us-00001", "YY")):
        directory = tmp_path / "jurisdictions" / jid
        directory.mkdir(parents=True)
        record = {**jurisdiction, "jurisdiction_id": jid, "state": state}
        entries = [{**source, "source_id": f"{jid}-zo", "jurisdiction_id": jid}]
        record["sources"] = [entries[0]["source_id"]]
        if jid == "us-00000":
            entries.append(analyst)
            record["sources"].append(analyst["source_id"])
        (directory / "jurisdiction.json").write_text(json.dumps(record), encoding="utf-8")
        (directory / "sources.json").write_text(json.dumps({"sources": entries}), encoding="utf-8")
    primary_hosts = {jid: {"hosts": ["planning.example.org"], "arcgis_org_ids": []} for jid in ("us-00000", "us-00001")}
    (tmp_path / "policy" / "primary_hosts.json").write_text(json.dumps(primary_hosts), encoding="utf-8")
    (tmp_path / "state_rules").mkdir()
    (tmp_path / "state_rules" / "ZZ.json").write_text(
        json.dumps(
            [
                {
                    "id": "zz-datacenter",
                    "state": "ZZ",
                    "use_class": "datacenter",
                    "effect": "state_siting_exclusive",
                    "url": "https://laws.example.org/a",
                    "effective_date": "2026-01-01",
                },
                {
                    "id": "zz-warehouse_distribution",
                    "state": "ZZ",
                    "use_class": "warehouse_distribution",
                    "effect": "none_found",
                    "url": "https://laws.example.org/no",
                },
            ]
        ),
        encoding="utf-8",
    )
    text_dir = tmp_path / "cache" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "us-00000-analyst.txt").write_text("", encoding="utf-8")
    return tmp_path
