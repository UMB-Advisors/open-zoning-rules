"""Offline tests for release construction."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import jsonschema
import pyarrow.parquet as pq
from ozr import measure, release
from ozr.contract import check_release

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for directory in ("taxonomy", "policy", "schema"):
        shutil.copytree(ROOT / directory, root / directory)
    jurisdiction = root / "jurisdictions" / "us-00000"
    jurisdiction.mkdir(parents=True)
    release_fixture = FIXTURES / "release"
    for name in ("jurisdictions.json", "sources.json", "cells.json"):
        document = json.loads((release_fixture / name).read_text(encoding="utf-8"))
        if name == "jurisdictions.json":
            document = document[0]
            name = "jurisdiction.json"
        elif name == "sources.json":
            document = {"sources": [document["sources"][0]]}
        (jurisdiction / name).write_text(json.dumps(document), encoding="utf-8")
    (root / "state_rules").mkdir()
    rules = json.loads((release_fixture / "state_rules.json").read_text(encoding="utf-8"))
    (root / "state_rules" / "ZZ.json").write_text(json.dumps(rules), encoding="utf-8")
    statute = json.loads((release_fixture / "sources.json").read_text(encoding="utf-8"))["sources"][1]
    (root / "state_rules" / "sources.json").write_text(json.dumps({"sources": [statute]}), encoding="utf-8")
    shutil.copytree(FIXTURES / "texts", root / "cache" / "text")
    (root / "reports").mkdir()
    (root / "reports" / "accuracy.json").write_text(
        json.dumps({"reliance_notice": measure.RELIANCE_NOTICE}), encoding="utf-8"
    )
    return root


def test_build_writes_a_valid_hashed_release(tmp_path: Path) -> None:
    root = _root(tmp_path)
    errors = release.build(root, published="2026-10-09")
    assert errors == []
    out = root / "releases" / "v0.1.0"
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert check_release(manifest) == []
    schema = json.loads((root / "schema" / "manifest.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    for entry in manifest["files"]:
        assert entry["sha256"] == hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest()
    table = pq.read_table(out / "cells.parquet")
    cells = json.loads((out / "cells.json").read_text(encoding="utf-8"))
    assert table.num_rows == len(cells)
    assert table.column("status").to_pylist() == [cell["status"] for cell in cells]
    assert b"geo" in (table.schema.metadata or {})
    assert "denylist.txt" not in {entry["path"] for entry in manifest["files"]}
    assert manifest["other_files"][0]["path"] == "denylist.txt"


def test_build_writes_geometry_only_when_redistribution_is_allowed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    source_id = "us-00000-gis"
    geometry_dir = root / "cache" / "geometry"
    geometry_dir.mkdir(parents=True)
    geometry_dir.joinpath(f"{source_id}.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"ZONE": "I-1"},
                        "geometry": {"type": "Point", "coordinates": [-122, 46]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    release.build(root, published="2026-10-09")
    out = root / "releases" / "v0.1.0"
    assert not list(out.glob("districts.*.geoparquet"))

    sources_path = root / "jurisdictions" / "us-00000" / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    sources["sources"].append(
        {
            **sources["sources"][0],
            "source_id": source_id,
            "kind": "gis_layer",
            "url": "https://gis.example.org/arcgis/rest/services/Zoning/MapServer/0?token=x",
            "redistribute_geometry": "yes",
        }
    )
    sources_path.write_text(json.dumps(sources), encoding="utf-8")
    assert release.build(root, published="2026-10-09") == []
    path = out / f"districts.{source_id}.geoparquet"
    assert pq.read_table(path).column("district_code").to_pylist() == ["I-1"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == path.name)
    assert entry["source_terms"]["redistribute_geometry"] == "yes"


def test_build_reports_missing_accuracy_and_gate_errors(tmp_path: Path) -> None:
    root = _root(tmp_path / "second")
    (root / "reports" / "accuracy.json").unlink()
    assert "run ozr measure first" in release.build(root, published="2026-10-09")

    root = _root(tmp_path)
    cells_path = root / "jurisdictions" / "us-00000" / "cells.json"
    cells = json.loads(cells_path.read_text(encoding="utf-8"))
    cells[0]["evidence"]["quote"] = "not in the source"
    cells_path.write_text(json.dumps(cells), encoding="utf-8")
    assert any("quote not found in source" in error for error in release.build(root, published="2026-10-09"))
