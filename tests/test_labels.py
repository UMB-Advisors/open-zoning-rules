"""Offline integration tests for extraction/review label isolation and gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ozr.extract import run as extract
from ozr.models import ModelResult
from ozr.review import run as review
from ozr.segment import segment_jurisdiction
from pdfgen import make_pdf


def _prepare(tiny_root: Path) -> None:
    pdf = make_pdf(
        [
            ["Zoning districts are hereby established: I-1 Light Industrial, I-2 Heavy Industrial"],
            ["Table 4-2 Table of Permitted Uses", "Warehouse P P", "I-1 I-2"],
            ["Definitions", "Data center means a facility housing servers."],
        ]
    )
    digest = hashlib.sha256(pdf).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(pdf)
    path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(path.read_text())
    document["sources"][0]["sha256"] = digest
    path.write_text(json.dumps(document))
    segment_jurisdiction(tiny_root, "us-00000")


def _result(text: str, model: str = "fake") -> ModelResult:
    return ModelResult(text, model, 10, 2, 3, 4, 0.01, 0.5, {})


def _good(notes: str = "") -> str:
    return json.dumps(
        {
            "cells": [
                {
                    "district_code": "I-1",
                    "use_class": "warehouse_distribution",
                    "status": "permitted",
                    "source_id": "us-00000-zo",
                    "local_uses": ["Warehouse"],
                    "evidence": {
                        "kind": "table",
                        "quote": "Warehouse | I-1 | P",
                        "section": "Table 4-2",
                        "row_label": "Warehouse",
                        "column_header": "I-1",
                        "symbol": "P",
                    },
                    "notes": notes,
                }
            ]
        }
    )


def test_extract_and_review_are_blind_to_each_other(tiny_root: Path) -> None:
    _prepare(tiny_root)
    observed: list[tuple[str, list[str]]] = []

    def extractor(prompt, _images, workdir):
        observed.append((prompt, [path.name for path in workdir.iterdir()]))
        return _result(_good("EXTRACTOR-ONLY-MARKER"), "claude")

    def reviewer(prompt, _images, workdir):
        observed.append((prompt, [path.name for path in workdir.iterdir()]))
        return _result(_good(), "codex:balanced")

    extract(tiny_root, "us-00000", extractor, "2026-10-10")
    output = review(tiny_root, "us-00000", "codex", reviewer, "2026-10-10")
    assert "EXTRACTOR-ONLY-MARKER" not in observed[1][0]
    assert observed[0][1] == observed[1][1] == []
    assert output["cells"][0]["status"] == "permitted"


def test_label_gates_reject_bad_cells_and_write_ledger(tiny_root: Path) -> None:
    _prepare(tiny_root)
    answer = json.loads(_good())
    good = answer["cells"][0]
    bad_row = {**good, "district_code": "I-2", "evidence": {**good["evidence"], "row_label": "No such row"}}
    unexplained = {
        **good,
        "district_code": "I-2",
        "use_class": "datacenter",
        "status": "unlisted",
        "local_uses": [],
        "evidence": {"kind": "absence", "quote": "Table 4-2 Table of Permitted Uses", "section": "Table 4-2"},
    }
    duplicate = dict(good)
    unknown = {**good, "district_code": "NOPE"}
    answer["cells"] = [good, bad_row, unexplained, duplicate, unknown]

    def call(_prompt, _images, _workdir):
        return _result(json.dumps(answer))

    output = extract(tiny_root, "us-00000", call, "2026-10-10")
    assert len(output["cells"]) == 1
    messages = [message for rejected in output["rejected"] for message in rejected["errors"]]
    assert any("row label not found" in message for message in messages)
    assert any("absence gate" in message for message in messages)
    assert any("duplicate cell" in message for message in messages)
    assert any("unknown district" in message for message in messages)
    assert ["I-1", "datacenter"] in output["missing"]
    ledger = json.loads((tiny_root / "runs" / "us-00000.jsonl").read_text().splitlines()[-1])
    assert ledger["input_tokens"] == 10
    assert ledger["cache_write_tokens"] == 4


def test_grok_review_is_never_given_images(tiny_root: Path) -> None:
    _prepare(tiny_root)
    seen: dict[str, list] = {}

    def codex(prompt, images, workdir):
        seen["codex"] = list(images)
        return _result(_good(), "codex:balanced")

    def grok(prompt, images, workdir):
        seen["grok"] = list(images)
        return _result(_good(), "grok")

    review(tiny_root, "us-00000", "codex", codex, "2026-10-10")
    review(tiny_root, "us-00000", "grok", grok, "2026-10-10")
    assert seen["codex"], "the codex reviewer reads the use-table page images"
    assert seen["grok"] == []
