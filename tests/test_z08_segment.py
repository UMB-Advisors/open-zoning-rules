"""Targeted regression tests for Z08 segmentation fixes."""

from __future__ import annotations

import hashlib
import json

from ozr import segment
from ozr.gates import contains
from ozr.segment import segment_state_rules, table_rows


def test_table_rows_preserves_empty_spanned_cells():
    assert table_rows([["518210", None, "S"], [None, None, None]]) == ["518210 |  | S"]


def test_strip_line_numbers_makes_georgia_quote_contiguous():
    text = """58 (2) 'Policy' means an ordinance, resolution, regulation, code, or any other requirement
59 imposed by a governmental entity.
60 (b) No governmental entity of this state shall adopt any policy that restricts or prohibits,
61 or has the effect of restricting or prohibiting, based on the type or source of energy or fuel
62 to be delivered or the appliance to be used:"""
    quote = (
        "No governmental entity of this state shall adopt any policy that restricts or prohibits, "
        "or has the effect of restricting or prohibiting, based on the type or source of energy or fuel "
        "to be delivered or the appliance to be used:"
    )
    assert contains(segment.strip_line_numbers(text), quote)


def test_strip_line_numbers_ignores_non_runs_and_short_runs():
    virginia_text = "4.1-629. Local regulation.\n2 acres or more\n10 days notice\n"
    assert segment.strip_line_numbers(virginia_text) == virginia_text
    short_run = "1 a\n2 b\n"
    assert segment.strip_line_numbers(short_run) == short_run


def test_segment_state_rules_strips_only_georgia_enrolled_bills(tiny_root):
    text = b"60 Georgia text\n61 continues\n62 ends\n"
    digest = hashlib.sha256(text).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(text)
    sources = {
        "sources": [
            {
                "source_id": "ga-bill",
                "sha256": digest,
                "url": "https://www.legis.ga.gov/api/legislation/document/123",
            },
            {"source_id": "other-law", "sha256": digest, "url": "https://law.example.org/statute"},
        ]
    }
    (tiny_root / "state_rules" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")

    segment_state_rules(tiny_root)

    assert (tiny_root / "cache" / "text" / "ga-bill.txt").read_text() == "Georgia text\ncontinues\nends"
    assert (tiny_root / "cache" / "text" / "other-law.txt").read_text() == "60 Georgia text\n61 continues\n62 ends"
