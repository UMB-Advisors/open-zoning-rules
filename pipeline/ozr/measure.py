"""Measure extractor agreement with a blind two-model reference panel."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from ozr.common import read_json, write_json

RELIANCE_NOTICE = (
    "This is a research dataset, not a legal determination. Before relying on any answer, at every grade, get a zoning "
    "verification letter or use determination from the planning department, or a land-use attorney or planner."
)
CAVEAT = (
    "What is measured is agreement between the extractor and a reference built from two other models that labelled "
    "the same text blind. It does not measure agreement with the law as a planner would read it: three models reading "
    "the same ambiguous table the same wrong way is invisible to this method."
)
STATUSES = ("permitted", "conditional", "prohibited", "unlisted")
LISTED = STATUSES[:3]


def _key(cell: dict) -> tuple[object, object, object]:
    return cell.get("jurisdiction_id"), cell.get("district_code"), cell.get("use_class")


def _cells(path: Path) -> tuple[list[dict], int, int]:
    if not path.is_file():
        return [], 0, 0
    doc = read_json(path)
    if not isinstance(doc, dict):
        return [], 0, 0
    cells = [cell for cell in doc.get("cells", []) if isinstance(cell, dict)]
    rejected = doc.get("rejected", [])
    return cells, len(cells), len(rejected) if isinstance(rejected, list) else 0


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _kappa(pairs: list[tuple[str, str]]) -> float | None:
    if len(pairs) < 2:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    expected = sum(
        (sum(left == status for left, _ in pairs) / len(pairs))
        * (sum(right == status for _, right in pairs) / len(pairs))
        for status in STATUSES
    )
    return None if expected == 1 else (observed - expected) / (1 - expected)


def _subset(rows: list[dict]) -> dict:
    gold = [row for row in rows if row["gold"] is not None]
    listed = [row for row in gold if row["gold"] in LISTED]
    unlisted = [row for row in gold if row["gold"] == "unlisted"]
    return {
        "counts": {
            "universe": len(rows),
            "gold": len(gold),
            "disputed": sum(row["disputed"] for row in rows),
            "reviewer_missing": sum(row["missing"] for row in rows),
        },
        "listed_agreement": _rate(sum(row["extractor"] == row["gold"] for row in listed), len(listed)),
        "unlisted_recall": _rate(sum(row["extractor"] == "unlisted" for row in unlisted), len(unlisted)),
        "unlisted_precision": _rate(
            sum(row["gold"] == "unlisted" for row in gold if row["extractor"] == "unlisted"),
            sum(row["extractor"] == "unlisted" for row in gold),
        ),
        "disputed_share": _rate(sum(row["disputed"] for row in rows), len(rows)),
    }


def _gate(value: float | None, threshold: float, enough: bool, reason: str | None = None) -> dict:
    result = "insufficient data" if not enough else "pass" if value is not None and value >= threshold else "fail"
    output = {"value": value, "threshold": threshold, "result": result}
    if reason:
        output["reason"] = reason
    return output


def _cost(root: Path, jids: list[str]) -> dict:
    per_jurisdiction: dict[str, dict] = {}
    dollars: list[float] = []
    hours: list[float] = []
    for jid in jids:
        models: dict[str, dict] = {}
        path = root / "runs" / f"{jid}.jsonl"
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = record.get("model")
                if not isinstance(model, str):
                    continue
                entry = models.setdefault(model, {"tokens": 0, "cost_usd": 0.0, "wall_s": 0.0, "unpriced_calls": 0})
                entry["tokens"] += sum(
                    record.get(field, 0)
                    for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
                    if isinstance(record.get(field), int)
                )
                entry["wall_s"] += record.get("wall_s", 0) if isinstance(record.get("wall_s"), (int, float)) else 0
                if isinstance(record.get("cost_usd"), (int, float)):
                    entry["cost_usd"] += record["cost_usd"]
                else:
                    entry["unpriced_calls"] += 1
        total_cost = (
            None
            if any(item["unpriced_calls"] for item in models.values())
            else sum(item["cost_usd"] for item in models.values())
        )
        total_hours = sum(item["wall_s"] for item in models.values()) / 3600
        for item in models.values():
            if item["unpriced_calls"]:
                item["cost_usd"] = None
        per_jurisdiction[jid] = {"models": models, "cost_usd": total_cost, "wall_s": total_hours * 3600}
        if total_cost is not None:
            dollars.append(total_cost)
            hours.append(total_hours)
    return {"per_jurisdiction": per_jurisdiction, "dollars": _summary(dollars), "hours": _summary(hours)}


def _summary(values: list[float]) -> dict:
    return (
        {"median": statistics.median(values), "min": min(values), "max": max(values)}
        if values
        else {"median": None, "min": None, "max": None}
    )


def measure(root: Path, jids: list[str], known_answers_path: Path | None = None) -> dict:
    """Return panel-agreement metrics for the complete district/class universe."""
    known_answers_path = known_answers_path or root / "tests" / "known_answers.json"
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    classes = [
        item["id"] for item in taxonomy.get("classes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    rows: list[dict] = []
    extractor_index: dict[tuple[object, object, object], dict] = {}
    published_index: dict[tuple[object, object, object], dict] = {}
    stages = {"extractor": [0, 0], "codex": [0, 0], "grok": [0, 0]}
    mutations: dict[str, object] = {}
    for jid in jids:
        base = root / "jurisdictions" / jid
        jurisdiction = read_json(base / "jurisdiction.json")
        documents = [
            _cells(base / name)
            for name in ("cells.extracted.json", "cells.review.codex.json", "cells.review.grok.json")
        ]
        indexes = [{_key(cell): cell for cell in document[0]} for document in documents]
        for stage, document in zip(stages, documents, strict=True):
            stages[stage][0] += document[1]
            stages[stage][1] += document[2]
        extractor_index.update(indexes[0])
        published = read_json(base / "cells.json") if (base / "cells.json").is_file() else []
        if isinstance(published, list):
            published_index.update({_key(cell): cell for cell in published if isinstance(cell, dict)})
        for district in jurisdiction.get("districts", []):
            if not isinstance(district, dict):
                continue
            for use_class in classes:
                key = (jid, district.get("district_code"), use_class)
                c, g = indexes[1].get(key), indexes[2].get(key)
                c_status, g_status = (c or {}).get("status"), (g or {}).get("status")
                both = c_status in STATUSES and g_status in STATUSES
                rows.append(
                    {
                        "jid": jid,
                        "family": district.get("family"),
                        "extractor": (indexes[0].get(key) or {}).get("status"),
                        "gold": c_status if both and c_status == g_status else None,
                        "disputed": both and c_status != g_status,
                        "missing": not both,
                        "pair": (c_status, g_status) if both else None,
                    }
                )
        mutation = base / "mutation.json"
        if mutation.is_file():
            mutations[jid] = read_json(mutation)
    summary = _subset(rows)
    gold_counts = {status: sum(row["gold"] == status for row in rows) for status in STATUSES}
    pairs = [row["pair"] for row in rows if row["pair"]]
    disputed_failed = (summary["disputed_share"] or 0) > 0.15
    listed_enough = all(gold_counts[status] >= 50 for status in LISTED)
    unlisted_recall_enough = gold_counts["unlisted"] >= 50
    unlisted_precision_enough = sum(row["extractor"] == "unlisted" and row["gold"] is not None for row in rows) >= 50
    gates = {
        "listed_agreement": _gate(
            summary["listed_agreement"], 0.90, listed_enough, "disputed share exceeds 0.15" if disputed_failed else None
        ),
        "unlisted_recall": _gate(
            summary["unlisted_recall"],
            0.85,
            unlisted_recall_enough,
            "disputed share exceeds 0.15" if disputed_failed else None,
        ),
        "unlisted_precision": _gate(
            summary["unlisted_precision"],
            0.85,
            unlisted_precision_enough,
            "disputed share exceeds 0.15" if disputed_failed else None,
        ),
        "disputed_share": {
            "value": summary["disputed_share"],
            "threshold": 0.15,
            "result": "pass" if not disputed_failed else "fail",
        },
    }
    if disputed_failed:
        for name in ("listed_agreement", "unlisted_recall", "unlisted_precision"):
            gates[name]["result"] = "fail"
    known = read_json(known_answers_path) if known_answers_path.is_file() else {}
    answers, misses, source_text_differences = [], [], []
    for answer in known.get("cells", []) if isinstance(known, dict) else []:
        if not isinstance(answer, dict) or answer.get("jurisdiction_id") not in jids:
            continue
        cell = extractor_index.get(
            (answer.get("jurisdiction_id"), answer.get("district_code"), answer.get("use_class"))
        )
        status = cell.get("status") if cell else None
        published = published_index.get(
            (answer.get("jurisdiction_id"), answer.get("district_code"), answer.get("use_class"))
        )
        result = {
            "id": answer.get("id"),
            "expected_status": answer.get("expected_status"),
            "source_text_status": answer.get("source_text_status"),
            "extractor_status": status,
            "published_status": published.get("status") if published else None,
            "match_expected": status == answer.get("expected_status") if cell else None,
            "match_source_text": status == answer.get("source_text_status")
            if cell and "source_text_status" in answer
            else None,
        }
        answers.append(result)
        if result["match_expected"] is False:
            misses.append(result)
        if result["match_source_text"] is False:
            source_text_differences.append(result)
    return {
        "measure": "model-panel agreement",
        "caveat": CAVEAT,
        "reliance_notice": RELIANCE_NOTICE,
        **summary,
        "gold_counts": gold_counts,
        "lower_bound": _rate(
            sum(row["extractor"] == row["gold"] for row in rows if row["gold"] is not None),
            sum(row["gold"] is not None for row in rows) + sum(row["disputed"] for row in rows),
        ),
        "kappa": _kappa(pairs),
        "gates": gates,
        "by_jurisdiction": {jid: _subset([row for row in rows if row["jid"] == jid]) for jid in jids},
        "by_family": {
            family: _subset([row for row in rows if row["family"] == family])
            for family in sorted({row["family"] for row in rows}, key=str)
        },
        "gate_rejection_rate": {stage: _rate(values[1], sum(values)) for stage, values in stages.items()},
        "known_answers": answers,
        "known_answer_misses": misses,
        "known_answer_source_text_differences": source_text_differences,
        "mutation": mutations,
        "cost": _cost(root, jids),
    }


def cli(args: argparse.Namespace) -> int:
    result = measure(args.root, args.jurisdiction_ids)
    write_json(args.root / "reports" / "accuracy.json", result)
    print(f"measured {len(args.jurisdiction_ids)} jurisdictions")
    return 0
