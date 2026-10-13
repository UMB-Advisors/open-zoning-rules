"""Combine blind labels into publishable, evidence-gated cells."""

from __future__ import annotations

import argparse
import hashlib
from datetime import date
from pathlib import Path

from ozr.common import append_run, read_json, text_path, utc_now, write_json
from ozr.contamination import load_denylist
from ozr.gates import OCR_TEXT_MARKER, apply_grade_rules, cell_errors, jurisdiction_text, ocr_only, superseded_errors


def _key(cell: dict) -> tuple[object, object, object]:
    return cell.get("jurisdiction_id"), cell.get("district_code"), cell.get("use_class")


def _cells(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    document = read_json(path)
    return [cell for cell in document.get("cells", []) if isinstance(cell, dict)] if isinstance(document, dict) else []


def _rejected(path: Path) -> dict[tuple[object, object, object], dict]:
    if not path.is_file():
        return {}
    document = read_json(path)
    if not isinstance(document, dict):
        return {}
    return {
        _key(entry["cell"]): entry
        for entry in document.get("rejected", [])
        if isinstance(entry, dict) and isinstance(entry.get("cell"), dict)
    }


def _pending(path: Path, cell: dict) -> bool:
    if not path.is_file():
        return False
    amendments = read_json(path)
    if not isinstance(amendments, list):
        return False
    for amendment in amendments:
        if not isinstance(amendment, dict) or amendment.get("kind") not in {"moratorium", "pending_text_amendment"}:
            continue
        if amendment.get("status") in {"expired", "withdrawn", "repealed"}:
            continue
        classes = amendment.get("use_classes", [])
        districts = amendment.get("districts", [])
        class_match = "*" in classes or cell.get("use_class") in classes
        if class_match and ("*" in districts or cell.get("district_code") in districts):
            return True
    return False


def _grade_run_id(root: Path, base: Path, jid: str, today: str, source_ids: list[str]) -> str:
    """Derive a grade run id from its deterministic inputs."""
    digest = hashlib.sha256()
    digest.update(b"today\0")
    digest.update(today.encode())
    paths = [
        base / "jurisdiction.json",
        base / "sources.json",
        base / "amendments.json",
        base / "cells.extracted.json",
        base / "cells.review.codex.json",
        base / "cells.review.grok.json",
        root / "taxonomy" / "v1.json",
    ]
    state = read_json(base / "jurisdiction.json").get("state")
    if isinstance(state, str):
        paths.append(root / "state_rules" / f"{state}.json")
    paths.extend(root / "cache" / "text" / f"{source_id}.txt" for source_id in source_ids)
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return f"grade-{jid}-{digest.hexdigest()[:16]}"


def grade_jurisdiction(root: Path, jid: str, today: str) -> dict:
    """Publish extractor cells only when a blind reviewer label passed its gates."""
    base = root / "jurisdictions" / jid
    jurisdiction = read_json(base / "jurisdiction.json")
    source_document = read_json(base / "sources.json")
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    if not isinstance(jurisdiction, dict) or not isinstance(taxonomy, dict) or not isinstance(source_document, dict):
        raise ValueError(f"invalid jurisdiction inputs: {jid}")
    extractor = _cells(base / "cells.extracted.json")
    extracted_path = base / "cells.extracted.json"
    extracted_document = read_json(extracted_path) if extracted_path.is_file() else {}
    rejected = _rejected(extracted_path)
    reviewers = [
        {_key(cell): cell for cell in _cells(base / f"cells.review.{name}.json")} for name in ("codex", "grok")
    ]
    rules_path = root / "state_rules" / f"{jurisdiction.get('state')}.json"
    rules = read_json(rules_path) if rules_path.is_file() else []
    rules = rules if isinstance(rules, list) else []
    amendments_path = base / "amendments.json"
    amendments = read_json(amendments_path) if amendments_path.is_file() else []
    amendments = amendments if isinstance(amendments, list) else []
    sources = {
        source.get("source_id"): source
        for source in source_document.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    denylist = load_denylist(root / "policy" / "denylist.txt")
    classes = [item.get("id") for item in taxonomy.get("classes", []) if isinstance(item, dict)]
    order = {value: index for index, value in enumerate(classes)}
    published: list[dict] = []
    withheld: list[dict] = []
    extractor_by_key = {_key(cell): cell for cell in extractor}
    source_ids = [source_id for source_id in jurisdiction.get("sources", []) if isinstance(source_id, str)]
    run_id = _grade_run_id(root, base, jid, today, source_ids)
    exempt = {source_id for source_id in source_ids if sources.get(source_id, {}).get("kind") == "gis_layer"}
    absence_text = jurisdiction_text(root / "cache" / "text", source_ids, exempt=exempt)
    districts = [item.get("district_code") for item in jurisdiction.get("districts", []) if isinstance(item, dict)]
    for district in districts:
        for use_class in classes:
            key = (jid, district, use_class)
            rendered = "/".join(str(value) for value in key)
            extracted = extractor_by_key.get(key)
            if extracted is None:
                rejected_entry = rejected.get(key, {})
                document_run_id = (
                    extracted_document.get("regate", {}).get("run_id") if isinstance(extracted_document, dict) else None
                )
                fallback_run_id = extracted_document.get("run_id") if isinstance(extracted_document, dict) else None
                withheld.append(
                    {
                        "key": rendered,
                        "gate": "extraction",
                        "reason": rejected_entry.get("errors", ["extractor returned no cell for this key"]),
                        "run_id": rejected_entry.get("run_id") or document_run_id or fallback_run_id,
                    }
                )
                continue
            codex, grok = (reviewer.get(key) for reviewer in reviewers)
            labels = [label for label in (codex, grok) if label is not None]
            if not labels:
                withheld.append(
                    {
                        "key": rendered,
                        "gate": "review",
                        "reason": ["no reviewer label passed the gates"],
                        "run_id": run_id,
                    }
                )
                continue
            cell = dict(extracted)
            if len(labels) == 2:
                cell["review"] = (
                    "agree" if extracted.get("status") == codex.get("status") == grok.get("status") else "disputed"
                )
                cell["confidence"] = "B" if cell["review"] == "agree" else "C"
            else:
                cell["review"] = "single" if extracted.get("status") == labels[0].get("status") else "disputed"
                cell["confidence"] = "C"
            if cell.get("parcel_specific"):
                cell["see_case"] = jurisdiction.get("case_lookup_url")
            for rule in rules:
                if (
                    isinstance(rule, dict)
                    and rule.get("use_class") == cell.get("use_class")
                    and rule.get("effect") != "none_found"
                ):
                    cell["preemption"] = {"state_rule_id": rule.get("id"), "effect": rule.get("effect")}
                    break
            cell = apply_grade_rules(
                cell, date.fromisoformat(today), pending_amendment=_pending(base / "amendments.json", cell)
            )
            source = cell.get("source", {})
            source_id = source.get("id") if isinstance(source, dict) else None
            text = (
                text_path(root, source_id).read_text(encoding="utf-8")
                if isinstance(source_id, str) and text_path(root, source_id).is_file()
                else ""
            )
            if ocr_only(cell, text):
                cell["confidence"] = "C"
            if cell.get("status") == "unlisted" and OCR_TEXT_MARKER in absence_text:
                cell["confidence"] = "C"
            errors = cell_errors(
                cell, text, taxonomy, jurisdiction, denylist, absence_text=absence_text, amendments=amendments
            )
            superseded = superseded_errors(cell, amendments, sources, jurisdiction, text)
            if errors or superseded:
                withheld.append(
                    {
                        "key": rendered,
                        "gate": "superseded" if superseded else "grade",
                        "reason": [*errors, *superseded],
                        "run_id": run_id,
                    }
                )
            else:
                published.append(cell)
    published.sort(key=lambda cell: (str(cell.get("district_code")), order.get(cell.get("use_class"), len(order))))
    write_json(base / "cells.json", published)
    withheld.sort(key=lambda item: item["key"])
    write_json(base / "cells.withheld.json", {"jurisdiction_id": jid, "run_id": run_id, "withheld": withheld})
    result = {"published": len(published), "withheld": withheld}
    append_run(
        root,
        jid,
        {"step": "grade", "run_id": run_id, "at": utc_now(), "published": len(published), "withheld": len(withheld)},
    )
    return result


def cli(args: argparse.Namespace) -> int:
    for jid in args.jurisdiction_ids:
        result = grade_jurisdiction(args.root, jid, args.today)
        print(f"{jid}: {result['published']} published, {len(result['withheld'])} withheld")
    return 0
