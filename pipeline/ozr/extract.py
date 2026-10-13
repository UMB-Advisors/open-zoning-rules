"""Extraction stage using the Claude adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ozr.common import append_run, utc_now, write_json
from ozr.labels import label_jurisdiction
from ozr.models import run_claude
from ozr.segment import load_segments


def run(root: Path, jid: str, call: Any = None, today: str | None = None, chunk_size: int = 5) -> dict | None:
    """Extract model labels and write the isolated extraction result."""
    if not load_segments(root, jid):
        append_run(root, jid, {"step": "extract", "at": utc_now(), "skipped": "no segments"})
        return None
    template = Path(__file__).resolve().parents[2] / "prompts" / "extract.v1.md"
    output = label_jurisdiction(
        root, jid, template, call or run_claude, "claude", "extract", today, chunk_size=chunk_size
    )
    write_json(root / "jurisdictions" / jid / "cells.extracted.json", output)
    return output


def cli(args: argparse.Namespace) -> int:
    """Run extraction sequentially for selected jurisdictions."""
    for jid in args.jurisdiction_ids:
        output = run(args.root, jid, today=args.today)
        if output is None:
            print(f"{jid}: skipped, no segments")
        else:
            print(f"{jid}: {len(output['cells'])} cells, {len(output['rejected'])} rejected")
    return 0
