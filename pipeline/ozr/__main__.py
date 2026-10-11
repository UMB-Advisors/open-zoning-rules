"""Run Z0.3 pipeline stages.

Each stage module exposes ``cli(args: argparse.Namespace) -> int``; modules for
later stages are imported only when selected so their dependencies stay optional.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from ozr.common import ROOT, jurisdiction_ids, today

COMMANDS = ("fetch", "segment", "extract", "review", "grade", "measure", "mutation", "regate", "release", "audit")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ozr")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("jurisdiction_ids", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--state-rules", action="store_true")
    parser.add_argument("--geometry", action="store_true")
    parser.add_argument("--reviewer", choices=("codex", "grok", "both"), default="both")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--published", default=today())
    parser.add_argument("--today", default=today())
    parser.add_argument("--audit-sheet", type=Path, default=Path("audit/z0_audit_sheet.v0.1.0.csv"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse shared stage options and dispatch to its lazily imported module."""
    parser = _parser()
    args = parser.parse_intermixed_args(argv)
    args.root = args.root.resolve()
    known = jurisdiction_ids(args.root)
    if args.command == "release" and not args.jurisdiction_ids:
        args.jurisdiction_ids = known
    elif args.all:
        args.jurisdiction_ids = known
    elif not args.jurisdiction_ids:
        parser.error("provide jurisdiction ids or --all")
    unknown = sorted(set(args.jurisdiction_ids) - set(known))
    if unknown:
        parser.error(f"unknown jurisdiction id: {', '.join(unknown)}")
    try:
        module = importlib.import_module(f"ozr.{args.command}")
    except ModuleNotFoundError as error:
        if error.name == f"ozr.{args.command}":
            raise SystemExit("not implemented") from error
        raise
    return module.cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
