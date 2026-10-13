"""Regression gates for verbatim state-statute quotes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ozr import segment
from ozr.gates import _state_rule_quote_errors, contains

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "statutes"


def _rule(state: str, rule_id: str) -> dict:
    rules = json.loads((ROOT / "state_rules" / f"{state}.json").read_text(encoding="utf-8"))
    return next(rule for rule in rules if rule["id"] == rule_id)


def test_virginia_cannabis_quote_matches_verbatim_statute_excerpt() -> None:
    quote = _rule("VA", "va-cannabis_cultivation_processing")["quote"]
    excerpt = (FIXTURES / "va-statute-4.excerpt.txt").read_text(encoding="utf-8")

    assert contains(excerpt, quote)


def test_georgia_lp_gas_quote_requires_line_number_normalization() -> None:
    quote = _rule("GA", "ga-lp_gas")["quote"]
    excerpt = (FIXTURES / "ga-statute-7.raw-excerpt.txt").read_text(encoding="utf-8")

    assert contains(segment.strip_line_numbers(excerpt), quote)
    assert not contains(excerpt, quote)


def test_cached_state_rule_quotes_pass_the_preemption_gate() -> None:
    text_dir = ROOT / "cache" / "text"
    source_ids = ("va-statute-4", "ga-statute-7", "ga-statute-8")
    if not all((text_dir / f"{source_id}.txt").is_file() for source_id in source_ids):
        pytest.skip("state-statute text cache is absent")

    rules = [
        _rule("VA", "va-cannabis_cultivation_processing"),
        _rule("GA", "ga-lp_gas"),
        _rule("GA", "ga-utility_generation"),
    ]
    source_document = json.loads((ROOT / "state_rules" / "sources.json").read_text(encoding="utf-8"))
    by_url = {source["url"]: source for source in source_document["sources"]}
    sources = [by_url[rule["url"]] for rule in rules]

    assert _state_rule_quote_errors(rules, sources, text_dir) == []
