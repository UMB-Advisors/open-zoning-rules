"""Tests for opt-in two-column PDF text extraction."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pdfplumber
from jsonschema import Draft202012Validator
from ozr.segment import pdf_pages, segment_jurisdiction
from pdfgen import make_positioned_pdf


def _two_column_pdf() -> bytes:
    return make_positioned_pdf(
        [
            (72, 720, "Left sentence begins"),
            (320, 720, "Right column starts"),
            (72, 704, "and ends here."),
            (320, 704, "with its second line."),
            (160, 48, "Ordinance footer across the whole page"),
        ]
    )


def test_two_column_pages_are_read_by_column_when_enabled():
    pdf = _two_column_pdf()
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        extracted = document.pages[0].extract_text()

    assert pdf_pages(pdf)[0][0] == extracted
    two_columns = pdf_pages(pdf, columns=2)[0][0]
    assert "Left sentence begins and ends here." in two_columns.replace("\n", " ")
    assert two_columns.index("Left sentence begins") < two_columns.index("Right column starts")


def test_pages_with_many_midline_words_are_unchanged_when_enabled():
    pdf = make_positioned_pdf([(280, 720 - index * 16, "CrossMidlineTerm") for index in range(4)])
    assert pdf_pages(pdf, columns=2) == pdf_pages(pdf)


def test_segment_jurisdiction_uses_two_columns_only_when_source_requests_it(tiny_root):
    pdf = _two_column_pdf()
    digest = hashlib.sha256(pdf).hexdigest()
    (tiny_root / "cache").mkdir(exist_ok=True)
    (tiny_root / "cache" / digest).write_bytes(pdf)
    source_path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(source_path.read_text())
    document["sources"] = [{**document["sources"][0], "sha256": digest, "text_columns": 2}]
    source_path.write_text(json.dumps(document))

    segment_jurisdiction(tiny_root, "us-00000")
    text_path = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    assert text_path.read_text() == pdf_pages(pdf, columns=2)[0][0]

    document["sources"][0].pop("text_columns")
    source_path.write_text(json.dumps(document))
    segment_jurisdiction(tiny_root, "us-00000")
    assert text_path.read_text() == pdf_pages(pdf)[0][0]


def test_sources_schema_allows_only_one_or_two_text_columns():
    root = Path(__file__).parents[1]
    schema = json.loads((root / "schema" / "sources.schema.json").read_text())
    source = json.loads((root / "tests" / "fixtures" / "release" / "sources.json").read_text())["sources"][0]
    validator = Draft202012Validator(schema)

    assert not list(validator.iter_errors({"sources": [{**source, "text_columns": 2}]}))
    assert list(validator.iter_errors({"sources": [{**source, "text_columns": 3}]}))
