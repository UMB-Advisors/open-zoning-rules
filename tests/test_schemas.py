"""Checks for the v1 taxonomy and the release JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "record.schema.json",
    "manifest.schema.json",
    "state_rule.schema.json",
    "sources.schema.json",
    "jurisdiction.schema.json",
)
CLASS_IDS = [
    "datacenter",
    "warehouse_distribution",
    "heavy_industrial_hazmat",
    "lp_gas",
    "cannabis_cultivation_processing",
    "utility_generation",
    "battery_storage",
]
DATE = "2026-10-09"
SHA256 = "a" * 64


def load_json(relative: str) -> dict:
    """Load a JSON document from the repository root."""
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_schema(name: str) -> dict:
    """Load one JSON Schema document from schema/."""
    return load_json(f"schema/{name}")


def errors(name: str, instance: dict) -> list:
    """Return validation errors for an instance against a schema file."""
    return list(Draft202012Validator(load_schema(name)).iter_errors(instance))


def minimal_record() -> dict:
    return {
        "jurisdiction_id": "us-00000",
        "district_code": "IH",
        "use_class": "datacenter",
        "status": "permitted",
        "local_uses": ["data center"],
        "evidence": {
            "kind": "table",
            "quote": "data center is P in IH.",
            "section": "4.2",
            "row_label": "data center",
            "column_header": "IH",
            "symbol": "P",
        },
        "definition_evidence": {
            "quote": "Data center means a building primarily housing servers.",
            "section": "2.1",
        },
        "source": {"id": "src-ordinance", "url": "https://example.gov/code", "date": DATE},
        "confidence": "B",
        "review": "agree",
        "preemption": {"state_rule_id": "wa-datacenter", "effect": "none_found"},
        "parcel_specific": False,
        "see_case": None,
        "checked_at": DATE,
        "stale": False,
        "history": [{"date": DATE, "from": None, "to": "permitted", "by": "extractor", "ref": "run-1"}],
        "notes": "Mapped from the use table.",
    }


def unlisted_record() -> dict:
    record = minimal_record()
    record["status"] = "unlisted"
    record["local_uses"] = []
    record["evidence"] = {"kind": "absence", "quote": "Table 4.2 permitted uses.", "section": "4.2"}
    record.pop("definition_evidence")
    record["absence_hits"] = [
        {
            "term": "data center",
            "quote": "An office may contain a data center as an accessory room.",
            "section": "2.1",
            "reason": "Accessory server room, which the class excludes.",
        }
    ]
    return record


def minimal_manifest() -> dict:
    return {
        "schema": "zoning-atlas.release/0.1",
        "version": "0.1.0",
        "published": DATE,
        "licence": "CC-BY-4.0",
        "schema_url": "https://github.com/UMB-Advisors/open-zoning-rules/schema/manifest.schema.json",
        "files": [
            {
                "format": "geoparquet",
                "path": "districts.geoparquet",
                "sha256": SHA256,
                "source_terms": {
                    "text": "Redistribute with attribution.",
                    "url": "https://example.gov/terms",
                    "redistribute_geometry": "yes",
                },
            }
        ],
        "stale_after_months": 12,
        "denylist": ["example.gov"],
        "reliance_notice": "Parcel-specific answers are grade C at best. The case file governs.",
    }


def none_found_rule() -> dict:
    return {
        "id": "wa-datacenter",
        "state": "WA",
        "use_class": "datacenter",
        "effect": "none_found",
        "checked_at": DATE,
    }


def preempting_rule() -> dict:
    return {
        "id": "wa-battery_storage",
        "state": "WA",
        "use_class": "battery_storage",
        "effect": "local_ban_preempted",
        "citation": "Rev. Code 80.01",
        "quote": "A local government may not ban this use.",
        "url": "https://example.gov/statutes/80.01",
        "effective_date": "2024-01-01",
        "setbacks": [{"value": 500, "unit": "ft", "from": "school"}],
        "conditions": ["Applies above a stated capacity threshold."],
        "checked_at": DATE,
    }


def minimal_sources() -> dict:
    return {
        "sources": [
            {
                "source_id": "src-ordinance",
                "jurisdiction_id": "us-00000",
                "kind": "ordinance",
                "url": "https://example.gov/code",
                "fetched_at": f"{DATE}T00:00:00Z",
                "source_date": "2026-01-15",
                "sha256": SHA256,
                "licence_terms": {"text": "Public record."},
                "redistribute_geometry": "unknown",
                "triage": "ok",
            },
            {
                "source_id": "src-gis",
                "jurisdiction_id": "us-0000000",
                "kind": "gis_layer",
                "url": "https://gis.example.gov/zoning",
                "final_url": "https://gis.example.gov/zoning/0",
                "fetched_at": f"{DATE}T12:30:00Z",
                "source_date": "2026-01-15",
                "sha256": SHA256,
                "licence_terms": {"url": "https://example.gov/terms"},
                "redistribute_geometry": "no",
                "triage": "geometry_restricted",
                "arcgis_org_id": "exampleOrg",
            },
        ]
    }


def jurisdiction(rule: str) -> dict:
    document = {
        "jurisdiction_id": "us-00000",
        "name": "Example County",
        "type": "county",
        "state": "WA",
        "unlisted_rule": rule,
        "code_version": "2026-01-15",
        "conditional_zoning_unmapped": True,
        "sources": ["src-ordinance"],
        "districts": [
            {
                "district_code": "IH",
                "district_name": "Heavy Industrial",
                "family": "industrial",
                "parcel_specific": False,
                "geometry_ref": {"path": "districts/us-00000.json"},
            },
            {
                "district_code": "PD",
                "district_name": "Planned Development",
                "family": "PD",
                "parcel_specific": True,
                "geometry_ref": {
                    "layer_url": "https://gis.example.gov/zoning/0",
                    "field": "ZONE",
                    "value": "PD",
                },
            },
        ],
    }
    if rule == "prohibited_by_default":
        document["unlisted_rule_quote"] = {"quote": "Uses not listed are prohibited.", "section": "1.4"}
    return document


def test_schemas_are_draft_2020_12() -> None:
    for name in SCHEMA_NAMES:
        document = load_schema(name)
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert document["$id"] == f"https://github.com/UMB-Advisors/open-zoning-rules/schema/{name}"
        assert document["title"]
        assert document["description"]
        Draft202012Validator.check_schema(document)


def test_taxonomy_v1() -> None:
    document = load_json("taxonomy/v1.json")
    assert list(document) == ["taxonomy", "classes", "statuses", "rules", "evidence"]
    assert document["taxonomy"] == "v1"
    classes = document["classes"]
    assert [item["id"] for item in classes] == CLASS_IDS
    for item in classes:
        assert list(item) == [
            "id",
            "name",
            "covers",
            "includes",
            "excludes",
            "synonyms",
            "definition_terms",
        ]
        assert item["name"] and item["covers"]
        for key in ("includes", "excludes", "synonyms", "definition_terms"):
            values = item[key]
            assert values, (item["id"], key)
            assert all(isinstance(value, str) and value and value.strip() == value for value in values)
            folded = [value.casefold() for value in values]
            assert len(folded) == len(set(folded)), (item["id"], key)
        assert all("/" not in value and "(" not in value for value in item["synonyms"])
    assert [item["value"] for item in document["statuses"]] == [
        "permitted",
        "conditional",
        "prohibited",
        "unlisted",
    ]
    for status in document["statuses"]:
        assert list(status) == ["value", "meaning", "local_forms"]
        assert status["meaning"] and status["local_forms"]
    assert [item["id"] for item in document["rules"]] == [
        "blank_follows_key",
        "unlisted_not_prohibited",
        "rezoning_only_prohibited",
        "accessory_only_prohibited",
        "amendments_separate",
    ]
    assert all(item["text"].strip() for item in document["rules"])
    assert [item["status_source"] for item in document["evidence"]] == ["table", "prose", "absence"]
    assert all(item["must_contain"].strip() and item["gated_by"].strip() for item in document["evidence"])


def test_minimal_instances_validate() -> None:
    assert errors("record.schema.json", minimal_record()) == []
    assert errors("record.schema.json", unlisted_record()) == []
    assert errors("manifest.schema.json", minimal_manifest()) == []
    assert errors("state_rule.schema.json", none_found_rule()) == []
    assert errors("state_rule.schema.json", preempting_rule()) == []
    assert errors("sources.schema.json", minimal_sources()) == []
    assert errors("jurisdiction.schema.json", jurisdiction("none")) == []
    assert errors("jurisdiction.schema.json", jurisdiction("prohibited_by_default")) == []
    answer = load_schema("record.schema.json")["$defs"]["answer"]
    validator = Draft202012Validator(answer)
    lookup = {
        "value": "permitted",
        "confidence": "B",
        "jurisdiction": "us-00000",
        "district": "IH",
        "evidence": {"quote": "data center is P in IH.", "section": "4.2"},
        "source": {"id": "src-ordinance", "url": "https://example.gov/code", "date": DATE},
        "release": "0.1.0",
    }
    assert list(validator.iter_errors(lookup)) == []
    lookup["value"] = None
    lookup["confidence"] = "unverified"
    lookup["evidence"] = None
    assert list(validator.iter_errors(lookup)) == []


def test_table_evidence_without_row_label_fails() -> None:
    record = minimal_record()
    del record["evidence"]["row_label"]
    assert errors("record.schema.json", record)


def test_bad_date_fails() -> None:
    record = minimal_record()
    record["checked_at"] = "2026-1-9"
    assert errors("record.schema.json", record)
    record["checked_at"] = "2026-10-09\n"
    assert errors("record.schema.json", record)


def test_http_url_fails() -> None:
    record = minimal_record()
    record["source"]["url"] = "http://example.gov/code"
    assert errors("record.schema.json", record)


def test_preempting_rule_without_quote_fails() -> None:
    rule = preempting_rule()
    del rule["quote"]
    assert errors("state_rule.schema.json", rule)


def test_manifest_parent_path_fails() -> None:
    manifest = minimal_manifest()
    manifest["files"][0]["path"] = "../x.json"
    assert errors("manifest.schema.json", manifest)
