"""Regression tests for the cross-model review findings on the Z0.3 pipeline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator
from ozr import fetch, release
from ozr.gates import release_errors
from ozr.grade import grade_jurisdiction
from test_release_build import _root as release_root

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures"


def test_statute_redirect_off_the_approved_host_is_refused(tiny_root: Path) -> None:
    results = fetch.fetch_state_rules(tiny_root, lambda url: ("https://archive.example.net/copy", b"law"))
    assert [result["status"] for result in results] == ["refused"]
    document = json.loads((tiny_root / "state_rules" / "sources.json").read_text())
    assert document["sources"] == []


def test_geometry_paging_follows_short_pages_and_stops_on_an_empty_page(tiny_root: Path) -> None:
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    layer = "https://planning.example.org/arcgis/rest/services/Zoning/MapServer/0"
    document["sources"][0].update({"kind": "gis_layer", "url": layer, "redistribute_geometry": "yes"})
    path.write_text(json.dumps(document))
    jurisdiction_path = tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    jurisdiction = json.loads(jurisdiction_path.read_text())
    for district in jurisdiction["districts"]:
        district["geometry_ref"]["layer_url"] = layer
    jurisdiction_path.write_text(json.dumps(jurisdiction))
    pages = {0: ["I-1", "I-2"], 2: ["PD-1"], 3: []}
    offsets = []

    def opener(url):
        offset = int(url.split("resultOffset=")[1].split("&")[0])
        offsets.append(offset)
        features = [{"type": "Feature", "properties": {"ZONE": code}, "geometry": None} for code in pages[offset]]
        # A server capped at two rows per page that always claims more.
        return url, json.dumps({"features": features, "exceededTransferLimit": True}).encode()

    results = fetch.fetch_geometry(tiny_root, "us-00000", opener)
    assert [result["status"] for result in results] == ["new"]
    assert offsets == [0, 2, 3]
    output = json.loads((tiny_root / "cache" / "geometry" / "us-00000-zo.geojson").read_text())
    assert [feature["properties"]["ZONE"] for feature in output["features"]] == ["I-1", "I-2", "PD-1"]


def test_a_moratorium_on_all_classes_marks_cells_stale(tiny_root: Path) -> None:
    base = tiny_root / "jurisdictions" / "us-00000"
    (tiny_root / "cache" / "text").mkdir(parents=True)
    shutil.copy(FIXTURE / "texts" / "us-00000-zo.txt", tiny_root / "cache" / "text" / "us-00000-zo.txt")
    cells = json.loads((FIXTURE / "release" / "cells.json").read_text())
    cell = next(
        item for item in cells if item["district_code"] == "I-1" and item["use_class"] == "warehouse_distribution"
    )
    for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json"):
        (base / name).write_text(json.dumps({"cells": [cell], "rejected": [], "missing": []}))
    moratorium = {"kind": "moratorium", "status": "active", "use_classes": ["*"], "districts": ["*"]}
    (base / "amendments.json").write_text(json.dumps([moratorium]))
    grade_jurisdiction(tiny_root, "us-00000", "2026-10-10")
    [published] = json.loads((base / "cells.json").read_text())
    assert published["stale"] is True
    assert published["confidence"] == "C"


def test_a_wrong_other_files_hash_fails_the_release_gate(tmp_path: Path) -> None:
    root = release_root(tmp_path)
    assert release.build(root, published="2026-10-09") == []
    out = root / "releases" / "v0.1.0"
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["other_files"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    errors = release_errors(out, root / "cache" / "text")
    assert any("hash: denylist.txt" in error for error in errors)


def test_jurisdiction_schema_accepts_the_case_lookup_that_grade_reads() -> None:
    schema = json.loads((ROOT / "schema" / "jurisdiction.schema.json").read_text())
    jurisdiction = json.loads((FIXTURE / "release" / "jurisdictions.json").read_text())[0]
    jurisdiction["case_lookup_url"] = "https://planning.example.org/cases"
    assert list(Draft202012Validator(schema).iter_errors(jurisdiction)) == []
    jurisdiction["case_lookup_url"] = "http://planning.example.org/cases"
    assert list(Draft202012Validator(schema).iter_errors(jurisdiction)) != []
