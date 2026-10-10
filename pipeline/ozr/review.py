"""Independent review stage using Codex or Grok."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ozr.common import write_json
from ozr.labels import label_jurisdiction
from ozr.models import run_codex, run_grok


def run(root: Path, jid: str, reviewer: str, call: Any = None, today: str | None = None, chunk_size: int = 5) -> dict:
    """Review labels without reading any previous model output."""
    if reviewer not in {"codex", "grok"}:
        raise ValueError(f"unknown reviewer: {reviewer}")
    if call is None:
        call = run_codex if reviewer == "codex" else _run_grok
    template = Path(__file__).resolve().parents[2] / "prompts" / "review.v1.md"
    # Grok reads text only (spec section 5), so it is never handed page images.
    output = label_jurisdiction(
        root,
        jid,
        template,
        call,
        reviewer,
        f"review-{reviewer}",
        today,
        with_images=reviewer == "codex",
        chunk_size=chunk_size,
    )
    write_json(root / "jurisdictions" / jid / f"cells.review.{reviewer}.json", output)
    return output


def _run_grok(prompt: str, _images: list[object], workdir: Path):
    return run_grok(prompt, workdir)


def cli(args: argparse.Namespace) -> int:
    """Run selected independent reviewers sequentially."""
    reviewers = ("codex", "grok") if args.reviewer == "both" else (args.reviewer,)
    for reviewer in reviewers:
        for jid in args.jurisdiction_ids:
            output = run(args.root, jid, reviewer, today=args.today)
            print(f"{jid}/{reviewer}: {len(output['cells'])} cells, {len(output['rejected'])} rejected")
    return 0
