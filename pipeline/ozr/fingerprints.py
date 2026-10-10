"""Detect configured private-term fingerprints without exposing their terms."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import subprocess
import sys
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9]+")
MAX_FILE_SIZE = 2 * 1024 * 1024


def normalise(text: str) -> list[str]:
    """Return lowercase alphanumeric words."""
    return WORD_RE.findall(text.lower())


def digest(term: str, key: str) -> str:
    """Return the keyed digest of the normalized words joined with no separator, so that
    "Acme Widgets", "AcmeWidgets" and "acme-widgets" share one digest."""
    value = "".join(normalise(term)).encode()
    return hmac.new(key.encode(), value, hashlib.sha256).hexdigest()


def find_hits(text: str, digests: set[str], key: str, max_n: int = 4) -> set[str]:
    """Return normalized n-grams whose keyed digest is configured."""
    words = normalise(text)
    hits: set[str] = set()
    for start in range(len(words)):
        for size in range(1, min(max_n, len(words) - start) + 1):
            candidate = " ".join(words[start : start + size])
            if digest(candidate, key) in digests:
                hits.add(candidate)
    return hits


def _fingerprint_path(root: Path) -> Path:
    return root / "policy" / "fingerprints.txt"


def _load_digests(root: Path) -> set[str]:
    path = _fingerprint_path(root)
    if not path.exists():
        return set()
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _tracked_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    return [root / name for name in output.decode().split("\0") if name]


def _message_text(root: Path, rev_range: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), "log", "--format=%B", rev_range], text=True)


def _line_hits(text: str, digests: set[str], key: str) -> list[int]:
    return [number for number, line in enumerate(text.splitlines(), 1) if find_hits(line, digests, key)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--rev-range")
    parser.add_argument("--digest")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    key = os.environ.get("FINGERPRINT_KEY")

    if args.digest is not None:
        if not key:
            print("fingerprints: FINGERPRINT_KEY is required", file=sys.stderr)
            return 2
        print(digest(args.digest, key))
        return 0

    digests = _load_digests(root)
    if not digests:
        print("fingerprints: none configured")
        return 0
    if not key:
        print("fingerprints: FINGERPRINT_KEY is required", file=sys.stderr)
        return 2

    failures: list[str] = []
    for path in _tracked_files(root):
        if path.stat().st_size > MAX_FILE_SIZE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        failures.extend(f"{path.relative_to(root)}:{line}: fingerprint hit" for line in _line_hits(text, digests, key))
    if args.rev_range:
        failures.extend(
            f"commit message:{line}: fingerprint hit"
            for line in _line_hits(_message_text(root, args.rev_range), digests, key)
        )
    if failures:
        print("\n".join(failures))
        return 1
    print("fingerprints: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
