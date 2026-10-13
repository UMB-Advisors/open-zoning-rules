"""Check committed triage inputs against their schemas and source policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from jsonschema import Draft202012Validator

from ozr.contamination import check_url, load_denylist

_STATE_FILE = re.compile(r"^[A-Z]{2}$")


def _read(path: Path, root: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{path.relative_to(root)}: invalid JSON: {error}")
        return None


def _validator(root: Path, name: str) -> Draft202012Validator:
    schema = json.loads((root / "schema" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _schema_errors(path: Path, root: Path, validator: Draft202012Validator, value: object) -> list[str]:
    return [f"{path.relative_to(root)}: schema invalid: {error.message}" for error in validator.iter_errors(value)]


def _url_errors(path: Path, root: Path, url: object, denylist: frozenset[str]) -> list[str]:
    if not isinstance(url, str):
        return []
    return [f"{path.relative_to(root)}: {error}" for error in check_url(url, denylist)]


def _host_allowed(url: object, policy: object, org_id: object = None) -> bool:
    if not isinstance(url, str) or not isinstance(policy, dict):
        return False
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    hosts = policy.get("hosts", [])
    if any(isinstance(item, str) and (host == item.lower() or host.endswith(f".{item.lower()}")) for item in hosts):
        return True
    orgs = policy.get("arcgis_org_ids", [])
    if not isinstance(org_id, str) or org_id not in orgs:
        return False
    return f"/{org_id}/" in parsed.path or host == "www.arcgis.com"


def _layer_org_id(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urllib.parse.urlsplit(url)
    if re.fullmatch(r"services\d*\.arcgis\.com", parsed.hostname or ""):
        parts = parsed.path.split("/")
        return parts[1] if len(parts) > 1 and parts[1] else None
    return None


def _known_answer_errors(
    root: Path, jurisdictions: dict[str, dict], taxonomy: set[str], denylist: frozenset[str]
) -> list[str]:
    path = root / "tests" / "known_answers.json"
    if not path.exists():
        return []
    errors: list[str] = []
    document = _read(path, root, errors)
    if document is None:
        return errors
    errors.extend(_schema_errors(path, root, _validator(root, "known_answers.schema.json"), document))
    if not isinstance(document, dict):
        return errors
    seen: set[str] = set()
    for kind in ("cells", "amendments"):
        for row in document.get(kind, []) if isinstance(document.get(kind), list) else []:
            if not isinstance(row, dict):
                continue
            identifier = row.get("id")
            if isinstance(identifier, str):
                if identifier in seen:
                    errors.append(f"{path.relative_to(root)}: duplicate known answer id: {identifier}")
                seen.add(identifier)
            jurisdiction_id = row.get("jurisdiction_id")
            jurisdiction = jurisdictions.get(jurisdiction_id) if isinstance(jurisdiction_id, str) else None
            if jurisdiction is None:
                errors.append(f"{path.relative_to(root)}: unknown jurisdiction: {jurisdiction_id}")
            districts = (
                {item.get("district_code") for item in jurisdiction.get("districts", []) if isinstance(item, dict)}
                if jurisdiction
                else set()
            )
            values = row.get("districts", []) if kind == "amendments" else [row.get("district_code")]
            for district in values if isinstance(values, list) else []:
                if district != "*" and district not in districts:
                    errors.append(f"{path.relative_to(root)}: unknown district: {district}")
            classes = row.get("use_classes", []) if kind == "amendments" else [row.get("use_class")]
            for use_class in classes if isinstance(classes, list) else []:
                if use_class not in taxonomy:
                    errors.append(f"{path.relative_to(root)}: use class not in taxonomy: {use_class}")
            citation = row.get("citation")
            if isinstance(citation, dict):
                errors.extend(_url_errors(path, root, citation.get("url"), denylist))
    return errors


def triage_errors(root: Path) -> list[str]:
    """Return deterministic validation and policy errors for committed triage data."""
    root = root.resolve()
    errors: list[str] = []
    denylist = load_denylist(root / "policy" / "denylist.txt")
    primary_hosts = _read(root / "policy" / "primary_hosts.json", root, errors)
    primary_hosts = primary_hosts if isinstance(primary_hosts, dict) else {}
    taxonomy_document = _read(root / "taxonomy" / "v1.json", root, errors)
    taxonomy = (
        {
            item.get("id")
            for item in taxonomy_document.get("classes", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if isinstance(taxonomy_document, dict)
        else set()
    )
    jurisdiction_validator = _validator(root, "jurisdiction.schema.json")
    sources_validator = _validator(root, "sources.schema.json")
    jurisdictions: dict[str, dict] = {}
    source_ids: set[str] = set()
    base = root / "jurisdictions"
    for directory in sorted(base.iterdir()) if base.exists() else []:
        if not directory.is_dir():
            continue
        jurisdiction_path = directory / "jurisdiction.json"
        sources_path = directory / "sources.json"
        jurisdiction = _read(jurisdiction_path, root, errors) if jurisdiction_path.exists() else None
        sources = _read(sources_path, root, errors) if sources_path.exists() else None
        if jurisdiction is None:
            errors.append(f"{jurisdiction_path.relative_to(root)}: missing jurisdiction.json")
            jurisdiction = {}
        if sources is None:
            errors.append(f"{sources_path.relative_to(root)}: missing sources.json")
            sources = {}
        errors.extend(_schema_errors(jurisdiction_path, root, jurisdiction_validator, jurisdiction))
        errors.extend(_schema_errors(sources_path, root, sources_validator, sources))
        if not isinstance(jurisdiction, dict) or not isinstance(sources, dict):
            continue
        jurisdiction_id = jurisdiction.get("jurisdiction_id")
        if jurisdiction_id != directory.name:
            errors.append(f"{jurisdiction_path.relative_to(root)}: directory name does not match jurisdiction_id")
        if isinstance(jurisdiction_id, str):
            jurisdictions[jurisdiction_id] = jurisdiction
        policy = primary_hosts.get(jurisdiction_id) if isinstance(jurisdiction_id, str) else None
        if policy is None:
            errors.append(f"{jurisdiction_path.relative_to(root)}: jurisdiction missing from primary_hosts")
        listed = set(jurisdiction.get("sources", [])) if isinstance(jurisdiction.get("sources"), list) else set()
        found: set[str] = set()
        for source in sources.get("sources", []) if isinstance(sources.get("sources"), list) else []:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id")
            if isinstance(source_id, str):
                if source_id in source_ids:
                    errors.append(f"{sources_path.relative_to(root)}: duplicate source id: {source_id}")
                source_ids.add(source_id)
                found.add(source_id)
                if source_id not in listed:
                    errors.append(f"{sources_path.relative_to(root)}: source not listed by jurisdiction: {source_id}")
            if source.get("jurisdiction_id") != directory.name:
                errors.append(f"{sources_path.relative_to(root)}: source jurisdiction_id does not match directory")
            errors.extend(_url_errors(sources_path, root, source.get("url"), denylist))
            errors.extend(_url_errors(sources_path, root, source.get("final_url"), denylist))
            if policy is not None and not _host_allowed(source.get("url"), policy, source.get("arcgis_org_id")):
                errors.append(
                    f"{sources_path.relative_to(root)}: source url is not a primary host: {source.get('url')}"
                )
        for source_id in listed - found:
            errors.append(f"{jurisdiction_path.relative_to(root)}: unlisted source id: {source_id}")
        for district in jurisdiction.get("districts", []) if isinstance(jurisdiction.get("districts"), list) else []:
            geometry = district.get("geometry_ref") if isinstance(district, dict) else None
            if isinstance(geometry, dict) and "layer_url" in geometry:
                url = geometry["layer_url"]
                errors.extend(_url_errors(jurisdiction_path, root, url, denylist))
                if policy is not None and not _host_allowed(url, policy, _layer_org_id(url)):
                    errors.append(
                        f"{jurisdiction_path.relative_to(root)}: geometry layer_url is not a primary host: {url}"
                    )
    state_validator = _validator(root, "state_rule.schema.json")
    state_base = root / "state_rules"
    for path in sorted(state_base.glob("*.json")) if state_base.exists() else []:
        state = path.stem
        document = _read(path, root, errors)
        if not _STATE_FILE.fullmatch(state):
            errors.append(f"{path.relative_to(root)}: state rule filename must be two upper-case letters")
        if not isinstance(document, list):
            errors.append(f"{path.relative_to(root)}: state rule file must be an array")
            continue
        found: set[str] = set()
        for row in document:
            errors.extend(_schema_errors(path, root, state_validator, row))
            if not isinstance(row, dict):
                continue
            use_class = row.get("use_class")
            if isinstance(use_class, str):
                if use_class in found:
                    errors.append(f"{path.relative_to(root)}: duplicate class: {use_class}")
                found.add(use_class)
                if row.get("id") != f"{state.lower()}-{use_class}":
                    errors.append(f"{path.relative_to(root)}: wrong id: {row.get('id')}")
            if row.get("state") != state:
                errors.append(f"{path.relative_to(root)}: wrong state: {row.get('state')}")
            errors.extend(_url_errors(path, root, row.get("url"), denylist))
        for use_class in sorted(taxonomy - found):
            errors.append(f"{path.relative_to(root)}: missing class: {use_class}")
        for use_class in sorted(found - taxonomy):
            errors.append(f"{path.relative_to(root)}: extra class: {use_class}")
    errors.extend(_known_answer_errors(root, jurisdictions, taxonomy, denylist))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = triage_errors(args.root)
    if errors:
        print("\n".join(errors))
        return 1
    root = args.root.resolve()
    jurisdiction_paths = root / "jurisdictions"
    state_paths = root / "state_rules"
    jurisdictions = (
        sum(1 for path in jurisdiction_paths.glob("*") if path.is_dir()) if jurisdiction_paths.exists() else 0
    )
    sources = (
        sum(
            len(json.loads(path.read_text(encoding="utf-8")).get("sources", []))
            for path in jurisdiction_paths.glob("*/sources.json")
        )
        if jurisdiction_paths.exists()
        else 0
    )
    state_rules = (
        sum(len(json.loads(path.read_text(encoding="utf-8"))) for path in state_paths.glob("*.json"))
        if state_paths.exists()
        else 0
    )
    known = root / "tests" / "known_answers.json"
    answers = len(json.loads(known.read_text(encoding="utf-8")).get("cells", [])) if known.exists() else 0
    print(
        f"triage check: ok ({jurisdictions} jurisdictions, {sources} sources, "
        f"{state_rules} state rules, {answers} known answers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
