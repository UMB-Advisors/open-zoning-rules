"""Offline tests for the fetch stage."""

from __future__ import annotations

import hashlib
import json

import jsonschema
import pytest
from ozr import fetch
from ozr.__main__ import main
from ozr.contamination import USER_AGENT


def _source(root, source_id="us-00000-zo"):
    path = root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    return next(item for item in document["sources"] if item["source_id"] == source_id)


def test_skips_analyst_fetch_without_opening(tiny_root):
    calls = []
    results = fetch.fetch_jurisdiction(tiny_root, "us-00000", lambda url: calls.append(url) or (url, b"law"))
    assert calls == ["https://planning.example.org/zoning/ordinance.pdf"]
    assert results[1] == {"source_id": "us-00000-analyst", "status": "skipped", "reason": "analyst_fetch"}


@pytest.mark.parametrize("url", ["https://municode.com/code", "https://elsewhere.example.org/code"])
def test_refuses_disallowed_initial_urls_without_opening(tiny_root, url):
    source = _source(tiny_root)
    source["url"] = url
    (tiny_root / "jurisdictions" / "us-00000" / "sources.json").write_text(json.dumps({"sources": [source]}))
    results = fetch.fetch_jurisdiction(tiny_root, "us-00000", lambda value: pytest.fail(f"opened {value}"))
    assert results[0]["status"] == "refused"


def test_refuses_denylisted_redirect_without_cache(tiny_root):
    results = fetch.fetch_jurisdiction(tiny_root, "us-00000", lambda url: ("https://municode.com/code", b"bad"))
    assert results[0]["status"] == "refused"
    assert not (tiny_root / "cache").exists()


def test_fetch_records_new_changed_and_unchanged(tiny_root):
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    document["sources"][0].pop("sha256")
    path.write_text(json.dumps(document))
    first = fetch.fetch_jurisdiction(
        tiny_root, "us-00000", lambda url: (url + "?download=1", b"one"), now=lambda: "2026-01-01T00:00:00Z"
    )
    second = fetch.fetch_jurisdiction(
        tiny_root, "us-00000", lambda url: (url, b"two"), now=lambda: "2026-01-02T00:00:00Z"
    )
    third = fetch.fetch_jurisdiction(
        tiny_root, "us-00000", lambda url: (url, b"two"), now=lambda: "2026-01-03T00:00:00Z"
    )
    assert [first[0]["status"], second[0]["status"], third[0]["status"]] == ["new", "changed", "unchanged"]
    source = _source(tiny_root)
    assert source["sha256"] == hashlib.sha256(b"two").hexdigest()
    assert source["fetched_at"] == "2026-01-03T00:00:00Z"
    assert "final_url" not in source
    assert (tiny_root / "cache" / source["sha256"]).read_bytes() == b"two"


def test_user_agent_publishes_issue_contact():
    assert "https://github.com/UMB-Advisors/open-zoning-rules/issues" in USER_AGENT


def test_cli_refuses_a_single_jurisdiction_without_single(tiny_root):
    with pytest.raises(SystemExit, match="requires --single"):
        main(["fetch", "us-00000", "--root", str(tiny_root)])


def test_state_sources_are_schema_valid(tiny_root):
    fetch.fetch_state_rules(tiny_root, lambda url: (url, b"law"))
    document = json.loads((tiny_root / "state_rules" / "sources.json").read_text())
    schema = json.loads((tiny_root / "schema" / "sources.schema.json").read_text())
    jsonschema.validate(document, schema)
    assert [item["url"] for item in document["sources"]] == ["https://laws.example.org/a"]


def test_fetch_geometry_pages_allowed_layers_and_skips_unknown(tiny_root):
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    document["sources"][0].update(
        {
            "kind": "gis_layer",
            "url": "https://planning.example.org/arcgis/rest/services/Zoning/MapServer/0?token=x",
            "redistribute_geometry": "yes",
        }
    )
    document["sources"].append(
        {
            **document["sources"][0],
            "source_id": "us-00000-unknown",
            "redistribute_geometry": "unknown",
        }
    )
    path.write_text(json.dumps(document))
    jurisdiction_path = tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    jurisdiction = json.loads(jurisdiction_path.read_text())
    for district in jurisdiction["districts"]:
        district["geometry_ref"]["layer_url"] = "https://planning.example.org/arcgis/rest/services/Zoning/MapServer/0"
    jurisdiction_path.write_text(json.dumps(jurisdiction))
    calls = []

    def opener(url):
        calls.append(url)
        offset = 0 if "resultOffset=0" in url else 1000
        return url, json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"ZONE": f"I-{offset // 1000 + 1}"}, "geometry": None}],
                "exceededTransferLimit": offset == 0,
            }
        ).encode()

    results = fetch.fetch_geometry(tiny_root, "us-00000", opener)
    assert [result["status"] for result in results] == ["new"]
    assert len(calls) == 2
    output = json.loads((tiny_root / "cache" / "geometry" / "us-00000-zo.geojson").read_text())
    assert [feature["properties"]["ZONE"] for feature in output["features"]] == ["I-1", "I-2"]
