"""Checks for committed-triage validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from ozr.triage import triage_errors

ROOT = Path(__file__).resolve().parents[1]
CLASSES = [item["id"] for item in json.loads((ROOT / "taxonomy" / "v1.json").read_text())["classes"]]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_tree(tmp_path: Path) -> Path:
    for name in ("schema", "taxonomy"):
        shutil.copytree(ROOT / name, tmp_path / name)
    (tmp_path / "policy").mkdir()
    shutil.copy(ROOT / "policy" / "denylist.txt", tmp_path / "policy" / "denylist.txt")
    write_json(
        tmp_path / "policy" / "primary_hosts.json", {"us-00000": {"hosts": ["example.gov"], "arcgis_org_ids": ["org"]}}
    )
    jurisdiction = {
        "jurisdiction_id": "us-00000",
        "name": "Example County",
        "type": "county",
        "state": "ZZ",
        "unlisted_rule": "none",
        "code_version": "2026-01-01",
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
    }
    source = {
        "source_id": "source-1",
        "jurisdiction_id": "us-00000",
        "kind": "ordinance",
        "url": "https://example.gov/code",
        "fetched_at": "2026-01-01T00:00:00Z",
        "source_date": "2026-01-01",
        "sha256": "a" * 64,
        "licence_terms": {"text": "Public record."},
        "redistribute_geometry": "unknown",
        "triage": "ok",
    }
    write_json(tmp_path / "jurisdictions" / "us-00000" / "jurisdiction.json", jurisdiction)
    write_json(tmp_path / "jurisdictions" / "us-00000" / "sources.json", {"sources": [source]})
    rules = [
        {
            "id": f"zz-{use_class}",
            "state": "ZZ",
            "use_class": use_class,
            "effect": "none_found",
            "checked_at": "2026-01-01",
        }
        for use_class in CLASSES
    ]
    write_json(tmp_path / "state_rules" / "ZZ.json", rules)
    known = {
        "frozen_at": "2026-01-01",
        "taxonomy": "v1",
        "cells": [
            {
                "id": "cell-1",
                "jurisdiction_id": "us-00000",
                "district_code": "I",
                "use_class": "datacenter",
                "expected_status": "permitted",
                "basis": "code_text",
                "citation": {"url": "https://example.gov/code", "quote": "Data center permitted."},
                "quote_verified": True,
            }
        ],
        "amendments": [],
    }
    write_json(tmp_path / "tests" / "known_answers.json", known)
    return tmp_path


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_tree_passes(tmp_path: Path) -> None:
    assert triage_errors(make_tree(tmp_path)) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("schema_invalid", "schema invalid"),
        ("dir_mismatch", "directory name does not match jurisdiction_id"),
        ("unlisted_source", "unlisted source id"),
        ("source_not_listed", "source not listed by jurisdiction"),
        ("duplicate_source", "duplicate source id"),
        ("banned_source", "banned host"),
        ("banned_final", "banned host"),
        ("non_primary", "source url is not a primary host"),
        ("arcgis_org", "source url is not a primary host"),
        ("missing_policy", "jurisdiction missing from primary_hosts"),
        ("missing_class", "missing class"),
        ("duplicate_class", "duplicate class"),
        ("wrong_id", "wrong id"),
        ("wrong_state", "wrong state"),
        ("unknown_district", "unknown district"),
        ("unknown_jurisdiction", "unknown jurisdiction"),
        ("bad_status", "schema invalid"),
        ("banned_citation", "banned host"),
    ],
)
def test_triage_failures(tmp_path: Path, change: str, message: str) -> None:
    root = make_tree(tmp_path)
    jurisdiction_path = root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    sources_path = root / "jurisdictions" / "us-00000" / "sources.json"
    rules_path = root / "state_rules" / "ZZ.json"
    known_path = root / "tests" / "known_answers.json"
    jurisdiction = read_json(jurisdiction_path)
    sources = read_json(sources_path)
    rules = read_json(rules_path)
    known = read_json(known_path)
    if change == "schema_invalid":
        jurisdiction["name"] = ""
    elif change == "dir_mismatch":
        jurisdiction["jurisdiction_id"] = "us-00001"
    elif change == "unlisted_source":
        jurisdiction["sources"].append("missing")
    elif change == "source_not_listed":
        jurisdiction["sources"] = []
    elif change == "duplicate_source":
        second = root / "jurisdictions" / "us-00001"
        shutil.copytree(root / "jurisdictions" / "us-00000", second)
        other = read_json(second / "jurisdiction.json")
        other["jurisdiction_id"] = "us-00001"
        write_json(second / "jurisdiction.json", other)
        other_sources = read_json(second / "sources.json")
        other_sources["sources"][0]["jurisdiction_id"] = "us-00001"
        write_json(second / "sources.json", other_sources)
        policy = read_json(root / "policy" / "primary_hosts.json")
        policy["us-00001"] = policy["us-00000"]
        write_json(root / "policy" / "primary_hosts.json", policy)
    elif change == "banned_source":
        sources["sources"][0]["url"] = "https://municode.com/code"
    elif change == "banned_final":
        sources["sources"][0]["final_url"] = "https://municode.com/code"
    elif change == "non_primary":
        sources["sources"][0]["url"] = "https://other.gov/code"
    elif change == "arcgis_org":
        sources["sources"][0].update(url="https://www.arcgis.com/sharing/rest/content/items/a", arcgis_org_id="wrong")
    elif change == "missing_policy":
        write_json(root / "policy" / "primary_hosts.json", {})
    elif change == "missing_class":
        rules.pop()
    elif change == "duplicate_class":
        rules.append(rules[0])
    elif change == "wrong_id":
        rules[0]["id"] = "zz-wrong"
    elif change == "wrong_state":
        rules[0]["state"] = "WA"
    elif change == "unknown_district":
        known["cells"][0]["district_code"] = "X"
    elif change == "unknown_jurisdiction":
        known["cells"][0]["jurisdiction_id"] = "us-99999"
    elif change == "bad_status":
        known["cells"][0]["expected_status"] = "maybe"
    elif change == "banned_citation":
        known["cells"][0]["citation"]["url"] = "https://municode.com/code"
    write_json(jurisdiction_path, jurisdiction)
    write_json(sources_path, sources)
    write_json(rules_path, rules)
    write_json(known_path, known)
    assert any(message in error for error in triage_errors(root))


def test_repository_triage_data_passes() -> None:
    assert triage_errors(ROOT) == []


@pytest.mark.parametrize(
    ("layer_url", "allowed"),
    [
        ("https://services.arcgis.com/org/arcgis/rest/services/Zoning/FeatureServer/0", True),
        ("https://services3.arcgis.com/org/arcgis/rest/services/Zoning/FeatureServer/0", True),
        ("https://services.arcgis.com/other/arcgis/rest/services/Zoning/FeatureServer/0", False),
    ],
)
def test_geometry_layer_org_id(tmp_path: Path, layer_url: str, allowed: bool) -> None:
    root = make_tree(tmp_path)
    path = root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    jurisdiction = json.loads(path.read_text())
    jurisdiction["districts"][0]["geometry_ref"] = {"layer_url": layer_url, "field": "ZONE", "value": "I"}
    write_json(path, jurisdiction)
    errors = [error for error in triage_errors(root) if "geometry layer_url is not a primary host" in error]
    assert (errors == []) is allowed
