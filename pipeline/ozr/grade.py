"""Combine blind labels into publishable, evidence-gated cells."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ozr.common import append_run, read_json, text_path, utc_now, write_json
from ozr.contamination import load_denylist
from ozr.gates import apply_grade_rules, cell_errors


def _key(cell: dict) -> tuple[object, object, object]:
    return cell.get("jurisdiction_id"), cell.get("district_code"), cell.get("use_class")


def _cells(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    document = read_json(path)
    return [cell for cell in document.get("cells", []) if isinstance(cell, dict)] if isinstance(document, dict) else []


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


def grade_jurisdiction(root: Path, jid: str, today: str) -> dict:
    """Publish extractor cells only when a blind reviewer label passed its gates."""
    base = root / "jurisdictions" / jid
    jurisdiction = read_json(base / "jurisdiction.json")
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    if not isinstance(jurisdiction, dict) or not isinstance(taxonomy, dict):
        raise ValueError(f"invalid jurisdiction inputs: {jid}")
    extractor = _cells(base / "cells.extracted.json")
    reviewers = [
        {_key(cell): cell for cell in _cells(base / f"cells.review.{name}.json")} for name in ("codex", "grok")
    ]
    rules_path = root / "state_rules" / f"{jurisdiction.get('state')}.json"
    rules = read_json(rules_path) if rules_path.is_file() else []
    rules = rules if isinstance(rules, list) else []
    denylist = load_denylist(root / "policy" / "denylist.txt")
    classes = [item.get("id") for item in taxonomy.get("classes", []) if isinstance(item, dict)]
    order = {value: index for index, value in enumerate(classes)}
    published: list[dict] = []
    withheld: list[dict] = []
    for extracted in extractor:
        key = _key(extracted)
        codex, grok = (reviewer.get(key) for reviewer in reviewers)
        labels = [label for label in (codex, grok) if label is not None]
        rendered = "/".join(str(value) for value in key)
        if not labels:
            withheld.append({"key": rendered, "reason": "no reviewer label passed the gates"})
            continue
        cell = dict(extracted)
        if len(labels) == 2:
            cell["review"] = (
                "agree" if extracted.get("status") == codex.get("status") == grok.get("status") else "disputed"
            )
            cell["confidence"] = "B" if cell["review"] == "agree" else "C"
        else:
            cell["review"], cell["confidence"] = "single", "C"
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
        errors = cell_errors(cell, text, taxonomy, jurisdiction, denylist)
        if errors:
            withheld.append({"key": rendered, "reason": errors})
        else:
            published.append(cell)
    published.sort(key=lambda cell: (str(cell.get("district_code")), order.get(cell.get("use_class"), len(order))))
    write_json(base / "cells.json", published)
    result = {"published": len(published), "withheld": withheld}
    append_run(root, jid, {"step": "grade", "at": utc_now(), "published": len(published), "withheld": len(withheld)})
    return result


def cli(args: argparse.Namespace) -> int:
    for jid in args.jurisdiction_ids:
        result = grade_jurisdiction(args.root, jid, args.today)
        print(f"{jid}: {result['published']} published, {len(result['withheld'])} withheld")
    return 0
