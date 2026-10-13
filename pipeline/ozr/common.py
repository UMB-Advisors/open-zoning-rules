"""Shared filesystem and clock helpers for pipeline stages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> object:
    """Read a UTF-8 JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    """Write a stable, human-readable UTF-8 JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cache_dir(root: Path) -> Path:
    """Return the uncommitted cache directory."""
    return root / "cache"


def text_path(root: Path, source_id: str) -> Path:
    """Return the full-text cache path for a source."""
    return cache_dir(root) / "text" / f"{source_id}.txt"


def segment_dir(root: Path, jid: str) -> Path:
    """Return the segment cache directory for a jurisdiction."""
    return cache_dir(root) / "segments" / jid


def jurisdiction_ids(root: Path) -> list[str]:
    """Return sorted jurisdiction directories that contain jurisdiction.json."""
    base = root / "jurisdictions"
    if not base.exists():
        return []
    return sorted(path.name for path in base.iterdir() if path.is_dir() and (path / "jurisdiction.json").is_file())


def append_run(root: Path, jid: str, record: dict) -> None:
    """Append one JSON run record for a jurisdiction."""
    path = root / "runs" / f"{jid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def utc_now() -> str:
    """Return the current UTC time in the repository timestamp format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    """Return today's UTC date."""
    return datetime.now(UTC).strftime("%Y-%m-%d")
