"""Draw a frozen, blind human-audit sample from published cells."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

SEED = 20261011
HEADER = tuple("cell_key jurisdiction_id district_code use_class source_url section human_status human_notes".split())
STATUSES = ("permitted", "conditional", "prohibited", "unlisted")


def draw(root: Path, jids: list[str], n: int = 60, seed: int = SEED) -> list[dict]:
    """Return n published cells stratified by status, then jurisdiction, with no model output."""
    cells = {status: [] for status in STATUSES}
    for jid in jids:
        path = root / "jurisdictions" / jid / "cells.json"
        if path.is_file():
            for cell in json.loads(path.read_text(encoding="utf-8")):
                if isinstance(cell, dict) and cell.get("status") in cells:
                    cells[cell["status"]].append(cell)
    n = max(n, 0)
    base, remainder = divmod(n, len(STATUSES))
    quotas = {status: min(base + (index < remainder), len(cells[status])) for index, status in enumerate(STATUSES)}
    remaining = min(n, sum(map(len, cells.values()))) - sum(quotas.values())
    while remaining:
        eligible = [status for status in STATUSES if quotas[status] < len(cells[status])]
        if not eligible:
            break
        share, extra = divmod(remaining, len(eligible))
        added = 0
        for index, status in enumerate(eligible):
            amount = min(share + (index < extra), len(cells[status]) - quotas[status])
            quotas[status] += amount
            added += amount
        remaining -= added
    selected: list[dict] = []
    for status in STATUSES:
        groups: dict[str, list[dict]] = {}
        for cell in cells[status]:
            groups.setdefault(cell["jurisdiction_id"], []).append(cell)
        for jid, group in groups.items():
            group.sort(key=lambda cell: (cell["district_code"], cell["use_class"]))
            random.Random(f"{seed}:{status}:{jid}").shuffle(group)
        positions = {jid: 0 for jid in sorted(groups)}
        taken = 0
        while taken < quotas[status]:
            for jid in sorted(groups):
                if taken < quotas[status] and positions[jid] < len(groups[jid]):
                    selected.append(groups[jid][positions[jid]])
                    positions[jid] += 1
                    taken += 1
    rows = [
        {
            "cell_key": f"{cell['jurisdiction_id']}/{cell['district_code']}/{cell['use_class']}",
            "jurisdiction_id": cell["jurisdiction_id"],
            "district_code": cell["district_code"],
            "use_class": cell["use_class"],
            "source_url": cell["source"]["url"],
            "section": cell["evidence"]["section"],
            "human_status": "",
            "human_notes": "",
        }
        for cell in selected
    ]
    return sorted(rows, key=lambda row: row["cell_key"])


def write_sheet(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def cli(args: argparse.Namespace) -> int:
    rows = draw(args.root, args.jurisdiction_ids)
    path = args.audit_sheet if args.audit_sheet.is_absolute() else args.root / args.audit_sheet
    write_sheet(rows, path)
    print(f"wrote {len(rows)} audit rows")
    return 0
