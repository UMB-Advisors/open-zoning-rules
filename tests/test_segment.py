"""Offline tests for segmentation."""

from __future__ import annotations

import hashlib
import json

from ozr.gates import canonical, contains, text_layers
from ozr.segment import cell_text, segment_jurisdiction
from pdfgen import make_pdf, make_table_pdf


def test_segments_pdf_html_and_missing_bytes(tiny_root):
    pdf = make_pdf(
        [
            ["Zoning districts are hereby established: I-1 Light Industrial, I-2 Heavy Industrial"],
            [
                "Table 4-2 Table of Permitted Uses",
                "Warehouse P P",
                "I-1 I-2",
                "Any use not listed in Table 4-2 is prohibited.",
            ],
            ["Definitions", "Data center means a facility housing servers."],
        ]
    )
    digest = hashlib.sha256(pdf).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(pdf)
    sources_path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(sources_path.read_text())
    document["sources"][0]["sha256"] = digest
    document["sources"].append({**document["sources"][0], "source_id": "missing", "sha256": "f" * 64})
    sources_path.write_text(json.dumps(document))
    manifest = segment_jurisdiction(tiny_root, "us-00000")
    by_kind = {item["kind"]: item for item in manifest["segments"]}
    assert by_kind["district_list"]["pages"] == [1, 2]
    assert by_kind["use_table"]["pages"] == [2, 3]
    assert by_kind["not_listed"]["pages"] == [2]
    assert by_kind["definitions"]["pages"] == [3]
    assert "Warehouse P P" in (tiny_root / "cache" / "text" / "us-00000-zo.txt").read_text()
    assert "=== us-00000-zo page 2 ===" in (tiny_root / "cache" / by_kind["use_table"]["text"]).read_text()
    image = by_kind["use_table"]["images"][0]
    assert hashlib.sha256((tiny_root / "cache" / image["path"]).read_bytes()).hexdigest() == image["sha256"]
    before = (tiny_root / "jurisdictions" / "us-00000" / "segments.json").read_bytes()
    segment_jurisdiction(tiny_root, "us-00000")
    assert (tiny_root / "jurisdictions" / "us-00000" / "segments.json").read_bytes() == before
    assert "missing" in manifest["missing_bytes"]


def test_html_is_one_tag_stripped_page(tiny_root):
    source = json.loads((tiny_root / "jurisdictions" / "us-00000" / "sources.json").read_text())["sources"][0]
    data = b"<p>Hello <b>zoning</b></p><script>nope</script><div>world &amp; more</div>"
    digest = hashlib.sha256(data).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(data)
    source["sha256"] = digest
    (tiny_root / "jurisdictions" / "us-00000" / "sources.json").write_text(json.dumps({"sources": [source]}))
    segment_jurisdiction(tiny_root, "us-00000")
    assert (tiny_root / "cache" / "text" / "us-00000-zo.txt").read_text() == "Hello zoning\nworld & more"


def test_list_style_use_pages_keep_their_continuation_page(tiny_root):
    pdf = make_pdf(
        [
            ["Article 1: General provisions"],
            ["Permitted Uses (by-right)", "Warehouse", "Data center"],
            ["Distribution center", "Truck terminal"],
            ["Permissible Uses (by special use permit)", "Refinery"],
        ]
    )
    digest = hashlib.sha256(pdf).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(pdf)
    sources_path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(sources_path.read_text())
    document["sources"][0]["sha256"] = digest
    sources_path.write_text(json.dumps(document))

    manifest = segment_jurisdiction(tiny_root, "us-00000")
    use_table = next(item for item in manifest["segments"] if item["kind"] == "use_table")
    assert use_table["pages"] == [2, 3, 4]


def test_wrapped_row_labels_are_rebuilt_from_table_rulings(tiny_root):
    pdf = make_table_pdf(
        [
            [["Table of Permitted Uses"], ["SCN-", "16"], ["CC", "-", "NC"]],
            [["Floating Solar", "Facility"], ["P"], ["P"]],
            [["Wholesale Distribution,", "Warehousing and", "Storage"], [""], ["S"]],
        ],
        [230, 80, 80],
    )
    digest = hashlib.sha256(pdf).hexdigest()
    (tiny_root / "cache").mkdir()
    (tiny_root / "cache" / digest).write_bytes(pdf)
    sources_path = tiny_root / "jurisdictions" / "us-00000" / "sources.json"
    document = json.loads(sources_path.read_text())
    document["sources"][0]["sha256"] = digest
    sources_path.write_text(json.dumps(document))

    manifest = segment_jurisdiction(tiny_root, "us-00000")
    text_path = tiny_root / "cache" / "text" / "us-00000-zo.txt"
    full_text = text_path.read_text()
    raw, _table = text_layers(full_text)
    assert canonical("Floating Solar Facility") not in canonical(raw)
    assert "Floating Solar Facility | P | P" in full_text
    assert "Wholesale Distribution, Warehousing and Storage |  | S" in full_text
    assert "SCN-16" in full_text
    assert "CC-NC" in full_text
    use_table = next(item for item in manifest["segments"] if item["kind"] == "use_table")
    assert "[reconstructed table text]" in (tiny_root / "cache" / use_table["text"]).read_text()
    before = text_path.read_bytes()
    segment_jurisdiction(tiny_root, "us-00000")
    assert text_path.read_bytes() == before


def test_cell_text_joins_hyphenated_fragments():
    assert contains(cell_text("SCN-\n16"), "SCN-16")
    assert contains(cell_text("CC\n-\nNC"), "CC-NC")
    assert contains(cell_text("Post-\nProduction"), "Post-Production")
