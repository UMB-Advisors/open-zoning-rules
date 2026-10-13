"""Build a deterministic, inspectable Z0.3 release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pyarrow as pa
import pyarrow.parquet as pq
from shapely import from_geojson, to_wkb

from ozr.common import jurisdiction_ids, read_json, today, write_json
from ozr.contamination import load_denylist
from ozr.contract import check_release
from ozr.gates import release_errors
from ozr.measure import RELIANCE_NOTICE


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_layer_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _taxonomy_order(root: Path) -> dict[str, int]:
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    classes = taxonomy.get("classes", []) if isinstance(taxonomy, dict) else []
    return {item["id"]: index for index, item in enumerate(classes) if isinstance(item, dict) and "id" in item}


def _included(root: Path) -> list[tuple[str, dict, dict, list[dict]]]:
    included: list[tuple[str, dict, dict, list[dict]]] = []
    for jid in jurisdiction_ids(root):
        base = root / "jurisdictions" / jid
        cells_path = base / "cells.json"
        if not cells_path.is_file():
            continue
        jurisdiction = read_json(base / "jurisdiction.json")
        sources = read_json(base / "sources.json")
        cells = read_json(cells_path)
        if not isinstance(jurisdiction, dict) or not isinstance(sources, dict) or not isinstance(cells, list):
            continue
        included.append((jid, jurisdiction, sources, [cell for cell in cells if isinstance(cell, dict)]))
    return included


def _cell_rows(cells: Iterable[dict], taxonomy_order: dict[str, int]) -> list[dict]:
    return sorted(
        cells,
        key=lambda cell: (
            str(cell.get("jurisdiction_id", "")),
            str(cell.get("district_code", "")),
            taxonomy_order.get(str(cell.get("use_class", "")), len(taxonomy_order)),
            str(cell.get("use_class", "")),
        ),
    )


def _cell_table(cells: list[dict]) -> pa.Table:
    """Build GeoParquet columns while retaining each complete source record as JSON."""
    rows = []
    for cell in cells:
        evidence = cell.get("evidence") if isinstance(cell.get("evidence"), dict) else {}
        source = cell.get("source") if isinstance(cell.get("source"), dict) else {}
        preemption = cell.get("preemption") if isinstance(cell.get("preemption"), dict) else {}
        local_uses = cell.get("local_uses")
        rows.append(
            {
                "jurisdiction_id": cell.get("jurisdiction_id"),
                "district_code": cell.get("district_code"),
                "use_class": cell.get("use_class"),
                "status": cell.get("status"),
                "confidence": cell.get("confidence"),
                "review": cell.get("review"),
                "parcel_specific": cell.get("parcel_specific"),
                "stale": cell.get("stale"),
                "checked_at": cell.get("checked_at"),
                "local_uses": local_uses if isinstance(local_uses, list) else None,
                "evidence_kind": evidence.get("kind"),
                "evidence_quote": evidence.get("quote"),
                "evidence_section": evidence.get("section"),
                "source_id": source.get("id"),
                "source_url": source.get("url"),
                "source_date": source.get("date"),
                "preemption_state_rule_id": preemption.get("state_rule_id"),
                "preemption_effect": preemption.get("effect"),
                "record_json": json.dumps(cell, ensure_ascii=False, sort_keys=True),
                "geometry": None,
            }
        )
    schema = pa.schema(
        [
            pa.field("jurisdiction_id", pa.string()),
            pa.field("district_code", pa.string()),
            pa.field("use_class", pa.string()),
            pa.field("status", pa.string()),
            pa.field("confidence", pa.string()),
            pa.field("review", pa.string()),
            pa.field("parcel_specific", pa.bool_()),
            pa.field("stale", pa.bool_()),
            pa.field("checked_at", pa.string()),
            pa.field("local_uses", pa.list_(pa.string())),
            pa.field("evidence_kind", pa.string()),
            pa.field("evidence_quote", pa.string()),
            pa.field("evidence_section", pa.string()),
            pa.field("source_id", pa.string()),
            pa.field("source_url", pa.string()),
            pa.field("source_date", pa.string()),
            pa.field("preemption_state_rule_id", pa.string()),
            pa.field("preemption_effect", pa.string()),
            pa.field("record_json", pa.string()),
            pa.field("geometry", pa.binary()),
        ],
        metadata={
            # A geometry-free GeoParquet is how this non-spatial table fits the contract format enum.
            b"geo": json.dumps(
                {
                    "version": "1.1.0",
                    "primary_column": "geometry",
                    "columns": {"geometry": {"encoding": "WKB", "geometry_types": []}},
                }
            ).encode(),
        },
    )
    return pa.Table.from_pylist(rows, schema=schema)


def _district_table(rows: list[dict]) -> pa.Table:
    geometry_types = sorted({row["geometry_type"] for row in rows})
    schema = pa.schema(
        [
            pa.field("jurisdiction_id", pa.string()),
            pa.field("district_code", pa.string()),
            pa.field("source_id", pa.string()),
            pa.field("geometry", pa.binary()),
        ],
        metadata={
            b"geo": json.dumps(
                {
                    "version": "1.1.0",
                    "primary_column": "geometry",
                    "columns": {"geometry": {"encoding": "WKB", "geometry_types": geometry_types}},
                }
            ).encode(),
        },
    )
    return pa.Table.from_pylist(
        [{key: value for key, value in row.items() if key != "geometry_type"} for row in rows], schema=schema
    )


def _district_files(root: Path, out: Path, included: list[tuple[str, dict, dict, list[dict]]]) -> list[dict]:
    entries: list[dict] = []
    for jid, jurisdiction, sources_doc, _ in included:
        districts = jurisdiction.get("districts", [])
        sources = sources_doc.get("sources", [])
        for source in sources if isinstance(sources, list) else []:
            if not isinstance(source, dict) or source.get("kind") != "gis_layer":
                continue
            if source.get("redistribute_geometry") != "yes" or not isinstance(source.get("url"), str):
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str):
                continue
            cache_path = root / "cache" / "geometry" / f"{source_id}.geojson"
            if not cache_path.is_file():
                continue
            document = read_json(cache_path)
            features = document.get("features", []) if isinstance(document, dict) else []
            layer_url = _source_layer_url(source["url"])
            fields = {
                ref.get("field")
                for district in districts
                if isinstance(district, dict)
                for ref in [district.get("geometry_ref")]
                if isinstance(ref, dict) and ref.get("layer_url") == layer_url and isinstance(ref.get("field"), str)
            }
            rows: list[dict] = []
            for feature in features if isinstance(features, list) else []:
                if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
                    continue
                geometry = feature.get("geometry")
                if geometry is None:
                    continue
                for field in sorted(fields):
                    code = feature["properties"].get(field)
                    if code is None:
                        continue
                    shape = from_geojson(json.dumps(geometry))
                    rows.append(
                        {
                            "jurisdiction_id": jid,
                            "district_code": str(code),
                            "source_id": source_id,
                            "geometry": to_wkb(shape),
                            "geometry_type": shape.geom_type,
                        }
                    )
            if not rows:
                continue
            filename = f"districts.{source_id}.geoparquet"
            pq.write_table(_district_table(rows), out / filename)
            terms = source.get("licence_terms") if isinstance(source.get("licence_terms"), dict) else {}
            source_terms = {key: terms[key] for key in ("text", "url") if isinstance(terms.get(key), str)}
            source_terms["redistribute_geometry"] = "yes"
            entries.append(
                {
                    "format": "geoparquet",
                    "path": filename,
                    "sha256": _sha256(out / filename),
                    "source_terms": source_terms,
                }
            )
    return entries


def build(
    root: Path,
    version: str = "0.1.0",
    published: str | None = None,
    out: Path | None = None,
    text_dir: Path | None = None,
) -> list[str]:
    """Write a release, then return contract and release-gate errors for it."""
    published = published or today()
    out = out or root / "releases" / f"v{version}"
    text_dir = text_dir or root / "cache" / "text"
    out.mkdir(parents=True, exist_ok=True)
    included = _included(root)
    cells = _cell_rows((cell for _, _, _, rows in included for cell in rows), _taxonomy_order(root))
    jurisdictions = [jurisdiction for _, jurisdiction, _, _ in included]
    local_sources = [
        source for _, _, document, _ in included for source in document.get("sources", []) if isinstance(source, dict)
    ]
    states = {jurisdiction.get("state") for jurisdiction in jurisdictions if isinstance(jurisdiction.get("state"), str)}
    statute_document = (
        read_json(root / "state_rules" / "sources.json") if (root / "state_rules" / "sources.json").is_file() else {}
    )
    state_source_rows = statute_document.get("sources", []) if isinstance(statute_document, dict) else []
    state_rules = [
        rule
        for state in sorted(states)
        for rule in (
            read_json(root / "state_rules" / f"{state}.json")
            if (root / "state_rules" / f"{state}.json").is_file()
            else []
        )
        if isinstance(rule, dict)
    ]
    statute_urls = {rule.get("url") for rule in state_rules if isinstance(rule.get("url"), str)}
    statute_sources = [
        source for source in state_source_rows if isinstance(source, dict) and source.get("url") in statute_urls
    ]
    amendments = [
        amendment
        for jid, _, _, _ in included
        for amendment in (
            read_json(root / "jurisdictions" / jid / "amendments.json")
            if (root / "jurisdictions" / jid / "amendments.json").is_file()
            else []
        )
        if isinstance(amendment, dict)
    ]
    write_json(out / "cells.json", cells)
    pq.write_table(_cell_table(cells), out / "cells.parquet")
    write_json(out / "jurisdictions.json", jurisdictions)
    write_json(
        out / "sources.json",
        {"sources": sorted(local_sources + statute_sources, key=lambda source: source.get("source_id", ""))},
    )
    write_json(out / "amendments.json", amendments)
    write_json(out / "state_rules.json", state_rules)
    withheld: list[dict] = []
    for jid, _, _, _ in included:
        path = root / "jurisdictions" / jid / "cells.withheld.json"
        document = read_json(path) if path.is_file() else {}
        if isinstance(document, dict):
            withheld.extend(
                {field: item.get(field) for field in ("key", "gate", "reason", "run_id")}
                for item in document.get("withheld", [])
                if isinstance(item, dict)
            )
    withheld.sort(key=lambda item: str(item.get("key", "")))
    write_json(out / "withheld.json", withheld)
    shutil_files = {"taxonomy.json": root / "taxonomy" / "v1.json", "denylist.txt": root / "policy" / "denylist.txt"}
    for name, source_path in shutil_files.items():
        (out / name).write_bytes(source_path.read_bytes())
    accuracy_path = root / "reports" / "accuracy.json"
    accuracy_error = None
    if not accuracy_path.is_file():
        accuracy_error = "run ozr measure first"
    else:
        accuracy = read_json(accuracy_path)
        if not isinstance(accuracy, dict) or accuracy.get("reliance_notice") != RELIANCE_NOTICE:
            accuracy_error = "accuracy.json reliance_notice does not match measure.RELIANCE_NOTICE"
        (out / "accuracy.json").write_bytes(accuracy_path.read_bytes())
    entries = [
        {"format": "json", "path": "cells.json", "sha256": _sha256(out / "cells.json")},
        {"format": "geoparquet", "path": "cells.parquet", "sha256": _sha256(out / "cells.parquet")},
        {"format": "json", "path": "jurisdictions.json", "sha256": _sha256(out / "jurisdictions.json")},
        {"format": "json", "path": "sources.json", "sha256": _sha256(out / "sources.json")},
        {"format": "json", "path": "amendments.json", "sha256": _sha256(out / "amendments.json")},
        {"format": "json", "path": "state_rules.json", "sha256": _sha256(out / "state_rules.json")},
        {"format": "json", "path": "withheld.json", "sha256": _sha256(out / "withheld.json")},
        {"format": "json", "path": "taxonomy.json", "sha256": _sha256(out / "taxonomy.json")},
        *_district_files(root, out, included),
    ]
    if accuracy_path.is_file():
        entries.append({"format": "json", "path": "accuracy.json", "sha256": _sha256(out / "accuracy.json")})
    manifest = {
        "schema": "zoning-atlas.release/0.1",
        "version": version,
        "published": published,
        "licence": "CC-BY-4.0",
        "schema_url": f"https://github.com/UMB-Advisors/open-zoning-rules/blob/v{version}/schema/record.schema.json",
        "files": entries,
        "other_files": [{"path": "denylist.txt", "sha256": _sha256(out / "denylist.txt")}],
        "stale_after_months": 12,
        "denylist": sorted(load_denylist(root / "policy" / "denylist.txt")),
        "reliance_notice": RELIANCE_NOTICE,
    }
    write_json(out / "manifest.json", manifest)
    errors = [
        *check_release(manifest),
        *release_errors(out, text_dir, load_denylist(root / "policy" / "denylist.txt"), root=root),
    ]
    return ([accuracy_error] if accuracy_error else []) + errors


def cli(args: argparse.Namespace) -> int:
    """Build a release and print its verified file hashes."""
    errors = build(args.root, args.version, args.published)
    if errors:
        print("\n".join(errors))
        return 1
    manifest = read_json(args.root / "releases" / f"v{args.version}" / "manifest.json")
    for entry in [*manifest["files"], *manifest.get("other_files", [])]:
        print(f"{entry['path']}: {entry['sha256']}")
    return 0
