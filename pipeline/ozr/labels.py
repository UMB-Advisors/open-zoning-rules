"""Shared prompt construction and deterministic gates for model labels."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from ozr.common import append_run, read_json, text_path, utc_now
from ozr.common import today as default_today
from ozr.contamination import check_url, load_denylist
from ozr.gates import absence_errors, absence_hits, enum_errors, quote_errors, section_errors, term_in
from ozr.models import ModelError, ModelResult, parse_json_object
from ozr.segment import load_segments

_MARKER = re.compile(r"^=== (?P<source>.+) page (?P<page>\d+) ===\n", re.MULTILINE)
_EVIDENCE_KEYS = ("kind", "quote", "section", "row_label", "column_header", "symbol")


def _taxonomy_text(taxonomy: dict) -> str:
    blocks = []
    for item in taxonomy.get("classes", []):
        if not isinstance(item, dict):
            continue
        lines = [f"- {item.get('id', '')}: {item.get('name', '')}"]
        for key in ("covers", "includes", "excludes"):
            value = item.get(key, [])
            rendered = ", ".join(value) if isinstance(value, list) else str(value)
            lines.append(f"  - {key}: {rendered}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _rules_text(taxonomy: dict) -> str:
    return "\n".join(f"- {item['text']}" for item in taxonomy.get("rules", []) if _has_text(item))


def _districts_text(jurisdiction: dict) -> str:
    return "\n".join(
        f"- {item.get('district_code', '')}: {item.get('district_name', '')} ({item.get('family', '')})"
        for item in jurisdiction.get("districts", [])
        if isinstance(item, dict)
    )


def _has_text(item: object) -> bool:
    return isinstance(item, dict) and isinstance(item.get("text"), str)


def _deduplicated_segments(segments: list[dict]) -> str:
    pages: dict[tuple[str, int], str] = {}
    for segment in segments:
        text = segment.get("text")
        if not isinstance(text, str):
            continue
        markers = list(_MARKER.finditer(text))
        for index, marker in enumerate(markers):
            key = (marker.group("source"), int(marker.group("page")))
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            pages.setdefault(key, text[marker.start() : end].strip())
    return "\n\n".join(pages[key] for key in sorted(pages))


def term_hits(text: str, taxonomy: dict, max_lines: int = 5) -> str:
    """Render deterministic full-code taxonomy-term occurrences for an absence review."""
    lines = text.splitlines()
    blocks: list[str] = []
    for item in taxonomy.get("classes", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        hits: list[str] = []
        for term in absence_hits(text, item["id"], taxonomy):
            matched = [line.strip() for line in lines if term_in(line, term)][:max_lines]
            if matched:
                hits.append(f"- {term}: " + " | ".join(matched))
        blocks.append(f"{item['id']}:\n" + ("\n".join(hits) if hits else "- none"))
    return "\n".join(blocks)


def build_prompt(template_path: Path, taxonomy: dict, jurisdiction: dict, segments: list[dict], term_hits: str) -> str:
    """Fill a prompt template without interpreting its JSON braces as formatting."""
    template = template_path.read_text(encoding="utf-8")
    values = {
        "taxonomy": _taxonomy_text(taxonomy),
        "rules": _rules_text(taxonomy),
        "districts": _districts_text(jurisdiction),
        "term_hits": term_hits,
        "segments": _deduplicated_segments(segments),
    }
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def normalise_label(
    raw: dict,
    jurisdiction: dict,
    sources_by_id: dict[str, dict],
    checked_at: str,
    by: str,
    ref: str,
) -> dict:
    """Turn one model response row into the record shape used by later stages."""
    source_id = raw.get("source_id")
    source = sources_by_id.get(source_id, {}) if isinstance(source_id, str) else {}
    district = next((item for item in jurisdiction.get("districts", []) if _is_district(item, raw)), {})
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    source_date = source.get("source_date")
    if source_date == "unknown":
        fetched_at = source.get("fetched_at", "")
        source_date = fetched_at.split("T", 1)[0] if isinstance(fetched_at, str) else ""
    record = {
        "jurisdiction_id": jurisdiction.get("jurisdiction_id"),
        "district_code": raw.get("district_code"),
        "use_class": raw.get("use_class"),
        "status": raw.get("status"),
        "local_uses": raw.get("local_uses") if isinstance(raw.get("local_uses"), list) else [],
        "evidence": {key: evidence[key] for key in _EVIDENCE_KEYS if key in evidence},
        "source": {"id": source_id, "url": source.get("url"), "date": source_date},
        "parcel_specific": district.get("parcel_specific", False) if isinstance(district, dict) else False,
        "checked_at": checked_at,
        "stale": False,
        "history": [{"date": checked_at, "from": None, "to": raw.get("status"), "by": by, "ref": ref}],
    }
    for key in ("definition_evidence", "absence_hits", "notes"):
        if key in raw:
            record[key] = raw[key]
    return record


def _is_district(item: object, raw: dict) -> bool:
    return isinstance(item, dict) and item.get("district_code") == raw.get("district_code")


def label_errors(
    cell: dict,
    text: str,
    taxonomy: dict,
    jurisdiction: dict,
    district_codes: list[str],
    denylist: frozenset[str],
) -> list[str]:
    """Return pre-grading label gate errors for one normalized cell."""
    key = f"{cell.get('jurisdiction_id', '')}/{cell.get('district_code', '')}/{cell.get('use_class', '')}"
    errors = [] if cell.get("district_code") in district_codes else [f"{key}: unknown district"]
    # enum_errors also checks confidence/review; inject grading placeholders so those checks cannot fire here.
    errors.extend(enum_errors({**cell, "confidence": "C", "review": "single"}, taxonomy))
    errors.extend(quote_errors(cell, text))
    errors.extend(section_errors(cell, text))
    errors.extend(absence_errors(cell, text, taxonomy, jurisdiction))
    source = cell.get("source") if isinstance(cell.get("source"), dict) else {}
    source_ids = {str(item) for item in jurisdiction.get("sources", [])}
    if not isinstance(source.get("id"), str) or source["id"] not in source_ids:
        errors.append(f"{key}: source_id not in sources")
    url = source.get("url")
    if not isinstance(url, str) or not url:
        errors.append(f"{key}: no source url")
    else:
        errors.extend(f"{key}: {error}" for error in check_url(url, denylist))
    return errors


def _images(segments: list[dict]) -> list[dict]:
    seen: set[str] = set()
    images: list[dict] = []
    for segment in segments:
        for image in segment.get("images", []):
            if isinstance(image, dict) and isinstance(image.get("path"), str) and image["path"] not in seen:
                seen.add(image["path"])
                images.append(image)
    return images


def _run_id(step: str, jid: str) -> str:
    return f"{step}-{jid}-{utc_now().replace('-', '').replace(':', '')}"


def label_jurisdiction(
    root: Path,
    jid: str,
    template: Path,
    call: Any,
    by: str,
    run_step: str,
    today: str | None = None,
    with_images: bool = True,
) -> dict:
    """Label a jurisdiction once, preserving only cells that pass deterministic gates."""
    jurisdiction = read_json(root / "jurisdictions" / jid / "jurisdiction.json")
    source_document = read_json(root / "jurisdictions" / jid / "sources.json")
    taxonomy = read_json(root / "taxonomy" / "v1.json")
    if not all(isinstance(value, dict) for value in (jurisdiction, source_document, taxonomy)):
        raise ValueError(f"invalid jurisdiction inputs: {jid}")
    sources_by_id = {
        source["source_id"]: source
        for source in source_document.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    segments = load_segments(root, jid)
    full_texts = {
        source_id: text_path(root, source_id).read_text(encoding="utf-8")
        for source_id in sources_by_id
        if text_path(root, source_id).is_file()
    }
    checked_at = today or default_today()
    run_id = _run_id(run_step, jid)
    hits = term_hits("\n\n".join(full_texts.values()), taxonomy)
    prompt = build_prompt(template, taxonomy, jurisdiction, segments, hits)
    try:
        with tempfile.TemporaryDirectory() as temporary:
            result: ModelResult = call(prompt, _images(segments) if with_images else [], Path(temporary))
        answer = parse_json_object(result.text)
    except ModelError as error:
        append_run(root, jid, {"step": run_step, "run_id": run_id, "at": utc_now(), "error": str(error)})
        raise
    raw_cells = answer.get("cells")
    if not isinstance(raw_cells, list):
        error = ModelError("model output cells is not a list")
        append_run(root, jid, {"step": run_step, "run_id": run_id, "at": utc_now(), "error": str(error)})
        raise error
    district_codes = [item.get("district_code") for item in jurisdiction.get("districts", []) if isinstance(item, dict)]
    district_codes = [code for code in district_codes if isinstance(code, str)]
    denylist = load_denylist(root / "policy" / "denylist.txt")
    cells: list[dict] = []
    rejected: list[dict] = []
    seen: set[tuple[object, object]] = set()
    for raw in raw_cells:
        if not isinstance(raw, dict):
            rejected.append({"cell": raw, "errors": ["cell is not an object"]})
            continue
        cell = normalise_label(raw, jurisdiction, sources_by_id, checked_at, by, run_id)
        source_id = cell["source"].get("id") if isinstance(cell.get("source"), dict) else None
        errors = label_errors(cell, full_texts.get(source_id, ""), taxonomy, jurisdiction, district_codes, denylist)
        pair = (cell.get("district_code"), cell.get("use_class"))
        if pair in seen:
            errors.append(f"{cell.get('jurisdiction_id')}/{pair[0]}/{pair[1]}: duplicate cell")
        else:
            seen.add(pair)
        if errors:
            rejected.append({"cell": cell, "errors": errors})
        else:
            cells.append(cell)
    class_ids = [
        item.get("id")
        for item in taxonomy.get("classes", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    covered = {(cell["district_code"], cell["use_class"]) for cell in cells}
    missing = [
        [district, use_class]
        for district in district_codes
        for use_class in class_ids
        if (district, use_class) not in covered
    ]
    output = {
        "jurisdiction_id": jid,
        "prompt": template.name,
        "model": result.model,
        "run_id": run_id,
        "checked_at": checked_at,
        "cells": cells,
        "rejected": rejected,
        "missing": missing,
    }
    append_run(
        root,
        jid,
        {
            "step": run_step,
            "run_id": run_id,
            "at": utc_now(),
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cost_usd": result.cost_usd,
            "wall_s": result.wall_s,
            "cells": len(cells),
            "rejected": len(rejected),
        },
    )
    return output
