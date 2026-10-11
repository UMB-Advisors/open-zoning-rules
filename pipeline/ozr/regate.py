"""Reapply deterministic label gates without calling a model."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from ozr.common import append_run, read_json, utc_now, write_json
from ozr.labels import gate_cells


def _run_id(jid: str) -> str:
    return f"regate-{jid}-{utc_now().replace('-', '').replace(':', '')}"


def regate_jurisdiction(root: Path, jid: str) -> dict:
    """Re-gate extractor and reviewer ledgers, preserving their original metadata."""
    base = root / "jurisdictions" / jid
    jurisdiction = read_json(base / "jurisdiction.json")
    sources_document = read_json(base / "sources.json")
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    if not all(isinstance(value, dict) for value in (jurisdiction, sources_document, taxonomy)):
        raise ValueError(f"invalid jurisdiction inputs: {jid}")
    sources_by_id = {
        source["source_id"]: source
        for source in sources_document.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    run_id = _run_id(jid)
    at = utc_now()
    class_ids = [item.get("id") for item in taxonomy.get("classes", []) if isinstance(item, dict)]
    district_codes = [item.get("district_code") for item in jurisdiction.get("districts", []) if isinstance(item, dict)]
    files: dict[str, dict] = {}
    for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json"):
        path = base / name
        if not path.is_file():
            continue
        document = read_json(path)
        if not isinstance(document, dict):
            continue
        candidates = [dict(cell) for cell in document.get("cells", []) if isinstance(cell, dict)]
        retained = []
        for rejected in document.get("rejected", []) if isinstance(document.get("rejected"), list) else []:
            if isinstance(rejected, dict) and isinstance(rejected.get("cell"), dict):
                candidates.append(dict(rejected["cell"]))
            else:
                retained.append(rejected)
        for cell in candidates:
            cell.pop("matched_text", None)
        cells, rejected = gate_cells(root, jid, jurisdiction, sources_by_id, taxonomy, candidates)
        rejected = [*retained, *[{**entry, "run_id": run_id} for entry in rejected]]
        covered = {(cell.get("district_code"), cell.get("use_class")) for cell in cells}
        missing = [
            [district, use_class]
            for district in district_codes
            for use_class in class_ids
            if (district, use_class) not in covered
        ]
        counts = Counter(f"{field}:{layer}" for cell in cells for field, layer in cell["matched_text"].items())
        output = {
            **document,
            "cells": cells,
            "rejected": rejected,
            "matched_text_counts": dict(sorted(counts.items())),
            "missing": missing,
            "regate": {"run_id": run_id, "at": at},
        }
        write_json(path, output)
        files[name] = {"cells": len(cells), "rejected": len(rejected)}
    append_run(root, jid, {"step": "regate", "run_id": run_id, "at": at, "files": files})
    return {"run_id": run_id, "files": files}


def cli(args: argparse.Namespace) -> int:
    for jid in args.jurisdiction_ids:
        result = regate_jurisdiction(args.root, jid)
        print(f"{jid}: regated {len(result['files'])} files")
    return 0
