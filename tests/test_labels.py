"""Offline integration tests for extraction/review label isolation and gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ozr.extract import run as extract
from ozr.gates import TABLE_TEXT_MARKER
from ozr.labels import _images
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


def test_passing_cells_record_which_text_matched(tiny_root: Path) -> None:
    _prepare(tiny_root)
    source_text = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    source_text.write_text("Table 4-2 I-1" + TABLE_TEXT_MARKER + "Warehouse | I-1 | P")

    output = extract(tiny_root, "us-00000", lambda *_args: _result(_good()), "2026-10-10")

    assert output is not None
    assert output["cells"][0]["matched_text"] == {
        "row_label": "table",
        "column_header": "raw",
        "section": "raw",
    }
    assert output["matched_text_counts"] == {
        "column_header:raw": 1,
        "row_label:table": 1,
        "section:raw": 1,
    }


def test_marker_page_suffix_in_source_id_is_stripped(tiny_root: Path) -> None:
    _prepare(tiny_root)
    valid = json.loads(_good())
    valid["cells"][0]["source_id"] = "us-00000-zo page 2"
    output = extract(tiny_root, "us-00000", lambda *_args: _result(json.dumps(valid)), "2026-10-10")
    assert output["cells"][0]["source"]["id"] == "us-00000-zo"

    unknown = json.loads(_good())
    unknown["cells"][0]["source_id"] = "us-99999-zo page 2"
    output = extract(tiny_root, "us-00000", lambda *_args: _result(json.dumps(unknown)), "2026-10-10")
    assert any("source_id not in sources" in error for error in output["rejected"][0]["errors"])


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


def test_absence_gate_reads_every_source_of_the_jurisdiction(tiny_root: Path) -> None:
    source_a = make_pdf([["Sec. 4-3", "Any use not listed in Table 4-2 is prohibited."]])
    source_b = make_pdf([["Definitions", "Data center means a facility housing servers."]])
    (tiny_root / "cache").mkdir()
    digest_a, digest_b = hashlib.sha256(source_a).hexdigest(), hashlib.sha256(source_b).hexdigest()
    (tiny_root / "cache" / digest_a).write_bytes(source_a)
    (tiny_root / "cache" / digest_b).write_bytes(source_b)
    sources_path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(sources_path.read_text())
    document["sources"][0]["sha256"] = digest_a
    source_b_record = {**document["sources"][0], "source_id": "us-00000-definitions", "sha256": digest_b}
    document["sources"].append(source_b_record)
    sources_path.write_text(json.dumps(document))
    jurisdiction_path = tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    jurisdiction = json.loads(jurisdiction_path.read_text())
    jurisdiction["sources"].append("us-00000-definitions")
    jurisdiction_path.write_text(json.dumps(jurisdiction))
    segment_jurisdiction(tiny_root, "us-00000")
    answer = {
        "cells": [
            {
                "district_code": "I-1",
                "use_class": "datacenter",
                "status": "unlisted",
                "source_id": "us-00000-zo",
                "local_uses": [],
                "evidence": {
                    "kind": "absence",
                    "quote": "Any use not listed in Table 4-2 is prohibited.",
                    "section": "Sec. 4-3",
                },
                "absence_hits": [
                    {
                        "term": "data center",
                        "quote": "Data center means a facility housing servers.",
                        "section": "Definitions",
                        "reason": "The definition does not list the use.",
                    },
                    {
                        "term": "servers",
                        "quote": "Data center means a facility housing servers.",
                        "section": "Definitions",
                        "reason": "The definition does not list the use.",
                    },
                ],
            },
            {
                "district_code": "I-2",
                "use_class": "datacenter",
                "status": "unlisted",
                "source_id": "us-00000-zo",
                "local_uses": [],
                "evidence": {
                    "kind": "absence",
                    "quote": "Any use not listed in Table 4-2 is prohibited.",
                    "section": "Sec. 4-3",
                },
                "absence_hits": [
                    {
                        "term": "data center",
                        "quote": "Data center is never defined here.",
                        "section": "Definitions",
                        "reason": "The definition does not list the use.",
                    },
                    {
                        "term": "servers",
                        "quote": "Data center means a facility housing servers.",
                        "section": "Definitions",
                        "reason": "The definition does not list the use.",
                    },
                ],
            },
        ]
    }

    output = extract(tiny_root, "us-00000", lambda *_args: _result(json.dumps(answer)), "2026-10-10")
    assert [cell["district_code"] for cell in output["cells"]] == ["I-1"]
    assert any("absence gate" in error for error in output["rejected"][0]["errors"])


def test_labelling_is_chunked_by_district_and_usage_is_summed(tiny_root: Path) -> None:
    _prepare(tiny_root)
    jurisdiction_path = tiny_root / "jurisdictions" / "us-00000" / "jurisdiction.json"
    jurisdiction = json.loads(jurisdiction_path.read_text())
    jurisdiction["districts"] = jurisdiction["districts"][:3]
    jurisdiction_path.write_text(json.dumps(jurisdiction))
    prompts: list[str] = []

    def call(prompt, _images, _workdir):
        prompts.append(prompt)
        return ModelResult(json.dumps({"cells": []}), "fake", 10, 2, 3, 4, 0.01, 0.5, {})

    extract(tiny_root, "us-00000", call, "2026-10-10", chunk_size=2)
    assert len(prompts) == 2
    assert "I-1" in prompts[0] and "I-2" in prompts[0] and "PD-1" not in prompts[0]
    assert "- PD-1: Planned Development (PD)" in prompts[1]
    assert "- I-1: Light Industrial (industrial)" not in prompts[1]
    ledger = json.loads((tiny_root / "runs" / "us-00000.jsonl").read_text().splitlines()[-1])
    assert ledger["calls"] == 2
    assert ledger["input_tokens"] == 20
    assert ledger["output_tokens"] == 4
    assert ledger["cache_read_tokens"] == 6
    assert ledger["cache_write_tokens"] == 8
    assert ledger["cost_usd"] == 0.02


def test_image_cap_keeps_pages_naming_a_taxonomy_term(tiny_root: Path) -> None:
    taxonomy = json.loads((tiny_root / "taxonomy" / "v1.json").read_text())
    first = {
        "source_id": "source-a",
        "text": "".join(f"=== source-a page {page} ===\nordinary text\n" for page in range(1, 44)),
        "images": [{"page": page, "path": f"/tmp/page-{page}.png"} for page in range(1, 44)],
    }
    second = {
        "source_id": "source-b",
        "text": "=== source-b page 44 ===\ndata center\n=== source-b page 45 ===\ndata center\n",
        "images": [{"page": page, "path": f"/tmp/page-{page}.png"} for page in (44, 45)],
    }
    images = _images([first, second], taxonomy)
    assert len(images) == 40
    assert {image["page"] for image in images}.issuperset({44, 45})


def test_extract_skips_a_jurisdiction_with_no_segments(tiny_root: Path) -> None:
    (tiny_root / "jurisdictions" / "us-00000" / "segments.json").write_text(json.dumps({"segments": []}))

    def call(*_args):
        raise AssertionError("the model must not be called")

    assert extract(tiny_root, "us-00000", call, "2026-10-10") is None
    assert not (tiny_root / "jurisdictions" / "us-00000" / "cells.extracted.json").exists()
    ledger = json.loads((tiny_root / "runs" / "us-00000.jsonl").read_text().splitlines()[-1])
    assert ledger["skipped"] == "no segments"
