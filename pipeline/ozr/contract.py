"""Consumer contract checks for zoning-atlas.release/0.1."""

from __future__ import annotations

import re
import urllib.parse

VALUES = ("permitted", "conditional", "prohibited", "unlisted")
CONFIDENCE = ("A", "B", "C", "unverified")
RELEASE_SCHEMA = "zoning-atlas.release/0.1"
FORMATS = ("geoparquet", "json")

_MISSING = object()
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HTTPS = re.compile(r"https://")
_PATH_ESCAPE = re.compile(r"(^/|\.\.)")
_BANNED_HOSTS = re.compile(
    r"(^|\.)(municode\.com|amlegal\.com|ecode360\.com|codelibrary\.amlegal\.com|zoningatlas\.org)$",
    re.IGNORECASE,
)


def _js_falsy(value: object) -> bool:
    if value is _MISSING or value is None or value is False:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    return False


def _js_str(value: object) -> str:
    """Return the JavaScript ToString form used after a truthiness check."""
    if value is True:
        return "true"
    if value is False or value is None or value is _MISSING:
        return ""
    if isinstance(value, bool):
        return "true" if value else ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


def _or_empty(value: object) -> str:
    if _js_falsy(value):
        return ""
    return _js_str(value)


def _path_label(path: object) -> str:
    if _js_falsy(path):
        return "?"
    return _js_str(path)


def _hostname(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return ""
    return host or ""


def _path_escapes(path: object) -> bool:
    if not isinstance(path, str):
        return True
    return _PATH_ESCAPE.search(path) is not None


def _named_source(source: object) -> bool:
    if _js_falsy(source) or not isinstance(source, dict):
        return False
    return isinstance(source.get("id", _MISSING), str)


def _evidence_gap(evidence: object) -> bool:
    if _js_falsy(evidence) or not isinstance(evidence, dict):
        return True
    quote = evidence.get("quote", _MISSING)
    section = evidence.get("section", _MISSING)
    if not isinstance(quote, str) or quote == "":
        return True
    return not isinstance(section, str) or section == ""


def _graded_errors(answer: dict, source: object) -> list[str]:
    errors: list[str] = []
    for key in ("jurisdiction", "district", "release"):
        field = answer.get(key, _MISSING)
        if not isinstance(field, str) or field == "":
            errors.append("a graded answer names its " + key)
    if _evidence_gap(answer.get("evidence", _MISSING)):
        errors.append("a graded answer quotes its evidence and section")
    source_url = source.get("url", _MISSING) if isinstance(source, dict) else _MISSING
    source_date = source.get("date", _MISSING) if isinstance(source, dict) else _MISSING
    if _HTTPS.match(_or_empty(source_url)) is None:
        errors.append("a graded answer links its primary source (https)")
    else:
        url_text = source_url if isinstance(source_url, str) else _js_str(source_url)
        if _BANNED_HOSTS.search(_hostname(url_text)):
            errors.append("source " + url_text + " is a third-party code host or the NZA: primary sources only")
    if _DATE.fullmatch(_or_empty(source_date)) is None:
        errors.append("a graded answer dates its source YYYY-MM-DD")
    return errors


def check_answer(answer: object) -> list[str]:
    """Return consumer-contract errors for one lookup record."""
    if not isinstance(answer, dict):
        return ["an answer is an object"]
    errors: list[str] = []
    value = answer.get("value", _MISSING)
    confidence = answer.get("confidence", _MISSING)
    if value is not None and value not in VALUES:
        errors.append("value is one of " + ", ".join(VALUES) + " or null")
    if confidence not in CONFIDENCE:
        errors.append("confidence is " + ", ".join(CONFIDENCE))
    if (value is None) != (confidence == "unverified"):
        errors.append("a value comes with a grade, and no value is unverified")
    source = answer.get("source", _MISSING)
    if not _named_source(source):
        errors.append("an answer names its source")
    if value is not None:
        errors.extend(_graded_errors(answer, source))
    return errors


def _one_file_errors(entry: object) -> list[str]:
    if not isinstance(entry, dict):
        label = "?"
        return [
            label + ": format is " + " or ".join(FORMATS),
            "a file path stays inside the release",
            label + ": carries its sha256",
        ]
    path = entry.get("path", _MISSING)
    label = _path_label(path)
    errors: list[str] = []
    if entry.get("format", _MISSING) not in FORMATS:
        errors.append(label + ": format is " + " or ".join(FORMATS))
    if _path_escapes(path):
        errors.append("a file path stays inside the release")
    if _SHA256.fullmatch(_or_empty(entry.get("sha256", _MISSING))) is None:
        errors.append(label + ": carries its sha256")
    return errors


def check_release(manifest: object) -> list[str]:
    """Return consumer-contract errors for a release manifest."""
    schema = manifest.get("schema", _MISSING) if isinstance(manifest, dict) else _MISSING
    if not isinstance(manifest, dict) or schema != RELEASE_SCHEMA:
        return ["schema is not " + RELEASE_SCHEMA]
    errors: list[str] = []
    if _SEMVER.fullmatch(_or_empty(manifest.get("version", _MISSING))) is None:
        errors.append("version is semver")
    if _DATE.fullmatch(_or_empty(manifest.get("published", _MISSING))) is None:
        errors.append("published is YYYY-MM-DD")
    licence = manifest.get("licence", _MISSING)
    if not isinstance(licence, str) or licence == "":
        errors.append("names its data licence")
    if _HTTPS.match(_or_empty(manifest.get("schema_url", _MISSING))) is None:
        errors.append("links its published record schema (schema_url)")
    files = manifest.get("files", _MISSING)
    if not isinstance(files, list) or len(files) == 0:
        errors.append("lists its files")
    if isinstance(files, list):
        for entry in files:
            errors.extend(_one_file_errors(entry))
    return errors


def to_record(cell: dict, version: str) -> dict:
    """Map a release cell row to a consumer lookup record."""
    evidence = cell.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    source = cell.get("source")
    if not isinstance(source, dict):
        source = {}
    return {
        "value": cell.get("status"),
        "confidence": cell.get("confidence"),
        "jurisdiction": cell.get("jurisdiction_id"),
        "district": cell.get("district_code"),
        "evidence": {"quote": evidence.get("quote"), "section": evidence.get("section")},
        "source": {"id": source.get("id"), "url": source.get("url"), "date": source.get("date")},
        "release": version,
    }
