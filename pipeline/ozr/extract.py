"""Extraction stage using the Claude adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ozr.common import write_json
from ozr.labels import label_jurisdiction
from ozr.models import run_claude


def run(root: Path, jid: str, call: Any = None, today: str | None = None) -> dict:
    """Extract model labels and write the isolated extraction result."""
    template = Path(__file__).resolve().parents[2] / "prompts" / "extract.v1.md"
    output = label_jurisdiction(root, jid, template, call or run_claude, "claude", "extract", today)
    write_json(root / "jurisdictions" / jid / "cells.extracted.json", output)
    return output


def cli(args: argparse.Namespace) -> int:
    """Run extraction sequentially for selected jurisdictions."""
    for jid in args.jurisdiction_ids:
        output = run(args.root, jid, today=args.today)
        print(f"{jid}: {len(output['cells'])} cells, {len(output['rejected'])} rejected")
    return 0
