"""Mutation check: verify that labels respond to changed use-table symbols."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import tempfile
from collections.abc import Collection
from pathlib import Path
from typing import Any

from ozr.common import append_run, read_json, write_json
from ozr.labels import label_jurisdiction
from ozr.models import run_claude

SYMBOLS = {"P": "SE", "SE": "P", "C": "P", "S": "P", "CU": "P", "SUP": "P", "X": "P", "PS": "SE"}
_TOKEN = re.compile(r"(?<!\w)(?:P|SE|C|S|CU|SUP|X|PS)(?!\w)")
_MARKER = re.compile(r"^=== (?P<source>.+) page (?P<page>\d+) ===\n", re.MULTILINE)


def _row(line: str) -> bool:
    return " | " in line or len(_TOKEN.findall(line)) >= 3


def mutate(text: str, rng: random.Random, n: int, targets: Collection[str] | None = None) -> tuple[str, list[dict]]:
    """Flip up to n symbols (or, with targets, n whole rows holding a target label), using the supplied RNG."""
    lines = text.splitlines(keepends=True)
    if targets is None:
        candidates = [(i, match) for i, line in enumerate(lines) if _row(line) for match in _TOKEN.finditer(line)]
        selected = rng.sample(candidates, min(n, len(candidates)))
    else:
        # Targeted: pick up to n whole rows that hold a target label and flip every symbol on them.
        rows = [
            i for i, line in enumerate(lines) if _row(line) and _TOKEN.search(line) and any(t in line for t in targets)
        ]
        chosen = rng.sample(rows, min(n, len(rows)))
        selected = [(i, match) for i in chosen for match in _TOKEN.finditer(lines[i])]
    selected_by_line: dict[int, list[re.Match[str]]] = {}
    for index, match in selected:
        selected_by_line.setdefault(index, []).append(match)
    flips: list[dict] = []
    for index, matches in selected_by_line.items():
        before = lines[index]
        replacements = {match.start(): match.group() for match in matches}
        rendered: list[str] = []
        cursor = 0
        for match in _TOKEN.finditer(before):
            rendered.append(before[cursor : match.start()])
            token = match.group()
            rendered.append(SYMBOLS[token] if match.start() in replacements else token)
            if match.start() in replacements:
                flips.append(
                    {
                        "line_no": index + 1,
                        "line_before": before.rstrip("\n"),
                        "line_after": "",
                        "from": token,
                        "to": SYMBOLS[token],
                    }
                )
            cursor = match.end()
        rendered.append(before[cursor:])
        lines[index] = "".join(rendered)
        for flip in flips:
            if flip["line_no"] == index + 1:
                flip["line_after"] = lines[index].rstrip("\n")
    return "".join(lines), flips


def _copy_root(root: Path, target: Path, jid: str) -> None:
    for name in ("taxonomy", "schema", "policy", "prompts"):
        source = root / name
        if source.exists():
            shutil.copytree(source, target / name)
    shutil.copytree(root / "jurisdictions" / jid, target / "jurisdictions" / jid)
    for name in ("segments", "text"):
        source = root / "cache" / name
        if source.exists():
            shutil.copytree(source, target / "cache" / name)


def _replace_pages(
    root: Path,
    target: Path,
    jid: str,
    rng: random.Random,
    n: int,
    targets: Collection[str] | None = None,
) -> list[dict]:
    manifest = read_json(root / "jurisdictions" / jid / "segments.json")
    flips: list[dict] = []
    remaining = n
    for segment in manifest.get("segments", []) if isinstance(manifest, dict) else []:
        if not isinstance(segment, dict) or segment.get("kind") != "use_table":
            continue
        relative = segment.get("text")
        if not isinstance(relative, str):
            continue
        original_path = root / "cache" / relative
        mutated_path = target / "cache" / relative
        original = original_path.read_text(encoding="utf-8")
        mutated, changes = mutate(original, rng, remaining, targets)
        if targets is None:
            remaining -= len(changes)
        else:
            remaining -= len({change["line_no"] for change in changes})
        mutated_path.parent.mkdir(parents=True, exist_ok=True)
        mutated_path.write_text(mutated, encoding="utf-8")
        flips.extend(changes)
        markers = list(_MARKER.finditer(original))
        for marker_index, marker in enumerate(markers):
            end = markers[marker_index + 1].start() if marker_index + 1 < len(markers) else len(original)
            old_page = original[marker.end() : end].strip()
            new_marker = list(_MARKER.finditer(mutated))[marker_index]
            new_end = (
                list(_MARKER.finditer(mutated))[marker_index + 1].start()
                if marker_index + 1 < len(markers)
                else len(mutated)
            )
            new_page = mutated[new_marker.end() : new_end].strip()
            source_path = target / "cache" / "text" / f"{marker.group('source')}.txt"
            if source_path.is_file():
                source_path.write_text(
                    source_path.read_text(encoding="utf-8").replace(old_page, new_page, 1), encoding="utf-8"
                )
    return flips


def _row_label(cell: dict | None) -> str:
    evidence = cell.get("evidence") if isinstance(cell, dict) else None
    label = evidence.get("row_label") if isinstance(evidence, dict) else None
    return label if isinstance(label, str) else ""


def _is_table_cell(cell: dict | None) -> bool:
    evidence = cell.get("evidence") if isinstance(cell, dict) else None
    if not isinstance(evidence, dict):
        return False
    return (
        evidence.get("kind") == "table"
        and isinstance(evidence.get("symbol"), str)
        and bool(evidence["symbol"])
        and isinstance(evidence.get("row_label"), str)
        and bool(evidence["row_label"])
    )


def _index(cells: list[dict]) -> dict[tuple[object, object, object], dict]:
    return {(cell.get("jurisdiction_id"), cell.get("district_code"), cell.get("use_class")): cell for cell in cells}


def run(root: Path, jid: str, call: Any = None, n: int = 10, seed: int = 0, today: str | None = None) -> dict:
    """Run text-only baseline and mutation labels, then record observed changes."""
    call = call or run_claude
    template = Path(__file__).resolve().parents[2] / "prompts" / "extract.v1.md"
    baseline = label_jurisdiction(root, jid, template, call, "claude", "mutation-baseline", today, with_images=False)
    targets = sorted({_row_label(cell) for cell in baseline["cells"] if _is_table_cell(cell)})
    targeted = bool(targets)
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary)
        _copy_root(root, target, jid)
        flips = _replace_pages(root, target, jid, random.Random(seed), n, targets if targeted else None)
        mutated = label_jurisdiction(target, jid, template, call, "claude", "mutation", today, with_images=False)
        run_path = target / "runs" / f"{jid}.jsonl"
        if run_path.is_file():
            for record in run_path.read_text(encoding="utf-8").splitlines():
                append_run(root, jid, json.loads(record))
    before, after = _index(baseline["cells"]), _index(mutated["cells"])
    keys = sorted(set(before) | set(after), key=str)
    changed = [
        key
        for key in keys
        if (before.get(key) or {}).get("status") != (after.get(key) or {}).get("status")
        or (
            (before.get(key) or {}).get("evidence", {}).get("quote")
            != (after.get(key) or {}).get("evidence", {}).get("quote")
        )
    ]
    status_changed = {
        key for key in keys if (before.get(key) or {}).get("status") != (after.get(key) or {}).get("status")
    }
    flipped_keys = {
        key
        for key in before
        if _is_table_cell(before[key]) and any(_row_label(before[key]) in flip["line_before"] for flip in flips)
    }
    compared_keys = set(before) & set(after)
    unflipped_keys = compared_keys - flipped_keys
    for flip in flips:
        # A flip is detected when a table cell whose row label is on the flipped line changed status.
        flip["flip_detected"] = any(
            key in status_changed and _row_label(before.get(key)) and _row_label(before.get(key)) in flip["line_before"]
            for key in keys
        )
    result = {
        "seed": seed,
        "n": n,
        "targeted": targeted,
        "flips": flips,
        "rows_flipped": len({flip["line_no"] for flip in flips}),
        "flipped_cells": len(flipped_keys),
        "flipped_cells_changed": len(flipped_keys & status_changed),
        "unflipped_cells": len(unflipped_keys),
        "unflipped_cells_changed": len(unflipped_keys & status_changed),
        "detection_rate": round(len(flipped_keys & status_changed) / len(flipped_keys), 3) if flipped_keys else None,
        "noise_rate": round(len(unflipped_keys & status_changed) / len(unflipped_keys), 3) if unflipped_keys else None,
        "cells": [
            {
                "key": "/".join(str(value) for value in key),
                "before": (before.get(key) or {}).get("status"),
                "after": (after.get(key) or {}).get("status"),
                "flipped": key in flipped_keys,
            }
            for key in keys
        ],
        "cells_compared": len(keys),
        "status_changed": len(status_changed),
        "quote_changed": sum(
            (
                (before.get(key) or {}).get("evidence", {}).get("quote")
                != (after.get(key) or {}).get("evidence", {}).get("quote")
            )
            for key in keys
        ),
        "flips_detected": sum(flip["flip_detected"] for flip in flips),
        "flips_total": len(flips),
        "changed_keys": ["/".join(str(value) for value in key) for key in changed],
        "result": "changed" if changed else "unchanged",
    }
    write_json(root / "jurisdictions" / jid / "mutation.json", result)
    return result


def cli(args: argparse.Namespace) -> int:
    for jid in args.jurisdiction_ids:
        result = run(args.root, jid, today=args.today)
        print(
            f"{jid}: {result['result']} rows_flipped={result['rows_flipped']} "
            f"detection={result['flipped_cells_changed']}/{result['flipped_cells']} "
            f"noise={result['unflipped_cells_changed']}/{result['unflipped_cells']}"
        )
    return 0
