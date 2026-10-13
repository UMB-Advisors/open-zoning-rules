"""Fetch approved primary-source bytes into the uncommitted content-addressed cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from functools import partial
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from ozr.common import append_run, cache_dir, jurisdiction_ids, read_json, utc_now, write_json
from ozr.contamination import USER_AGENT, check_url, follow_redirects, load_denylist
from ozr.triage import host_allowed

Opener = Callable[[str], tuple[str, bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def default_opener(url: str, check: Callable[[str], list[str]] | None = None) -> tuple[str, bytes]:
    """Download a URL, following redirects and requiring an HTTP 200 response."""
    opener = urllib.request.build_opener(_NoRedirect())
    current = url
    for _ in range(10):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            response = opener.open(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        try:
            status = response.status
            location = response.headers.get("Location")
            if 300 <= status < 400 and location:
                target = urllib.parse.urljoin(current, location)
                errors = check(target) if check is not None else []
                if errors:
                    raise RuntimeError(f"refused URL: {target}: {'; '.join(errors)}")
                current = target
                continue
            if status != 200:
                raise RuntimeError(f"HTTP {status}: {current}")
            return current, response.read()
        finally:
            response.close()
    raise RuntimeError(f"too many redirects: {url}")


def policy_errors(
    url: str,
    policy: object,
    org_id: object,
    denylist: frozenset[str],
    chain: Callable[[str], list[str]] | None = None,
) -> list[str]:
    """Return primary-host and contamination-policy errors for a source URL."""
    errors = [] if host_allowed(url, policy, org_id) else [f"not a primary host: {url}"]
    initial_errors = check_url(url, denylist)
    if errors or initial_errors or chain is None:
        return errors + initial_errors
    targets = chain(url)
    for target in targets[1:]:
        if not host_allowed(target, policy, org_id):
            errors.append(f"redirect target: not a primary host: {target}")
    return errors + check_url(url, denylist, lambda _: targets)


def _redirect_chain(policy: object, org_id: object, denylist: frozenset[str]) -> Callable[[str], list[str]]:
    """Return a redirect walker that refuses targets outside source policy."""
    return partial(
        follow_redirects,
        refuse=lambda target: not host_allowed(target, policy, org_id) or bool(check_url(target, denylist)),
    )


def _cache_bytes(root: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    path = cache_dir(root) / digest
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return digest


def _manual_fetch(root: Path, jid: str, source: dict, policy: object, denylist: frozenset[str]) -> dict:
    """Import a verified analyst-supplied file without opening its source URL."""
    source_id = str(source.get("source_id", ""))
    digest = source.get("sha256")
    if not isinstance(digest, str) or not digest:
        return {"source_id": source_id, "status": "skipped", "reason": "analyst_fetch"}
    manual = sorted((root / "cache" / "manual" / jid).glob(f"{digest}.*"))
    if not manual:
        return {"source_id": source_id, "status": "skipped", "reason": "analyst_fetch"}
    errors: list[str] = []
    for value in (source.get("url"), source.get("final_url")):
        if isinstance(value, str):
            errors.extend(policy_errors(value, policy, source.get("arcgis_org_id"), denylist))
    if errors:
        return {"source_id": source_id, "status": "refused", "errors": errors}
    data = manual[0].read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != digest:
        return {"source_id": source_id, "status": "error", "error": f"sha256 mismatch: {actual}"}
    _cache_bytes(root, data)
    return {"source_id": source_id, "status": "imported"}


def _fetch_source(
    root: Path,
    source: dict,
    opener: Opener,
    errors: list[str],
    final_check: Callable[[str], list[str]],
    now: Callable[[], str],
    delay: float,
    sleep: Callable[[float], None],
) -> dict:
    source_id = str(source.get("source_id", ""))
    url = source.get("url")
    if not isinstance(url, str):
        return {"source_id": source_id, "status": "refused", "errors": ["missing URL"]}
    if errors:
        return {"source_id": source_id, "status": "refused", "errors": errors}
    try:
        final_url, data = opener(url)
    except Exception as error:  # urllib exceptions intentionally become per-source results.
        return {"source_id": source_id, "status": "error", "error": str(error)}
    finally:
        sleep(delay)
    final_errors = final_check(final_url)
    if final_errors:
        return {"source_id": source_id, "status": "refused", "errors": final_errors}
    previous = source.get("sha256")
    digest = _cache_bytes(root, data)
    source["sha256"] = digest
    source["fetched_at"] = now()
    if final_url == url:
        source.pop("final_url", None)
    else:
        source["final_url"] = final_url
    if not isinstance(previous, str) or not previous:
        status = "new"
    elif previous == digest:
        status = "unchanged"
    else:
        status = "changed"
    result = {"source_id": source_id, "status": status}
    if status == "changed":
        result["previous_sha256"] = previous
    return result


def fetch_jurisdiction(
    root: Path,
    jid: str,
    opener: Opener = default_opener,
    online: bool = False,
    now: Callable[[], str] = utc_now,
    delay: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Fetch one jurisdiction's approved source records and return their results."""
    sources_path = root / "jurisdictions" / jid / "sources.json"
    document = read_json(sources_path)
    if not isinstance(document, dict):
        raise ValueError(f"invalid sources document: {sources_path}")
    primary_hosts = read_json(root / "policy" / "primary_hosts.json")
    policy = primary_hosts.get(jid) if isinstance(primary_hosts, dict) else None
    denylist = load_denylist(root / "policy" / "denylist.txt")
    results: list[dict] = []
    changed = False
    for source in document.get("sources", []):
        if not isinstance(source, dict):
            continue
        if source.get("triage") == "analyst_fetch":
            results.append(_manual_fetch(root, jid, source, policy, denylist))
            continue
        url = source.get("url")
        initial_errors = (
            policy_errors(
                url,
                policy,
                source.get("arcgis_org_id"),
                denylist,
                _redirect_chain(policy, source.get("arcgis_org_id"), denylist) if online else None,
            )
            if isinstance(url, str)
            else ["missing URL"]
        )
        before = dict(source)
        final_check = partial(policy_errors, policy=policy, org_id=source.get("arcgis_org_id"), denylist=denylist)
        request_opener = partial(default_opener, check=final_check) if opener is default_opener else opener
        results.append(_fetch_source(root, source, request_opener, initial_errors, final_check, now, delay, sleep))
        changed = changed or source != before
    if changed:
        write_json(sources_path, document)
    append_run(root, jid, {"step": "fetch", "at": now(), "results": results})
    return results


def _layer_url(url: str) -> str:
    """Return an ArcGIS layer endpoint without request-specific query parameters."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def fetch_geometry(
    root: Path,
    jid: str,
    opener: Opener = default_opener,
    online: bool = False,
    delay: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Fetch paged GeoJSON only for GIS layers licensed for redistribution."""
    base = root / "jurisdictions" / jid
    sources_doc = read_json(base / "sources.json")
    jurisdiction = read_json(base / "jurisdiction.json")
    if not isinstance(sources_doc, dict) or not isinstance(jurisdiction, dict):
        raise ValueError(f"invalid jurisdiction documents: {jid}")
    primary_hosts = read_json(root / "policy" / "primary_hosts.json")
    policy = primary_hosts.get(jid) if isinstance(primary_hosts, dict) else None
    denylist = load_denylist(root / "policy" / "denylist.txt")
    layer_fields = {
        ref.get("layer_url"): ref.get("field")
        for district in jurisdiction.get("districts", [])
        if isinstance(district, dict)
        for ref in [district.get("geometry_ref")]
        if isinstance(ref, dict) and isinstance(ref.get("layer_url"), str) and isinstance(ref.get("field"), str)
    }
    results: list[dict] = []
    for source in sources_doc.get("sources", []):
        if not isinstance(source, dict) or source.get("kind") != "gis_layer":
            continue
        if source.get("redistribute_geometry") != "yes":
            continue
        source_id, url = source.get("source_id"), source.get("url")
        if not isinstance(source_id, str) or not isinstance(url, str):
            results.append({"source_id": str(source_id or ""), "status": "refused", "errors": ["missing URL"]})
            continue
        layer = _layer_url(url)
        field = layer_fields.get(layer)
        if not isinstance(field, str):
            results.append({"source_id": source_id, "status": "refused", "errors": ["no district geometry field"]})
            continue
        initial_errors = policy_errors(
            layer,
            policy,
            source.get("arcgis_org_id"),
            denylist,
            _redirect_chain(policy, source.get("arcgis_org_id"), denylist) if online else None,
        )
        if initial_errors:
            results.append({"source_id": source_id, "status": "refused", "errors": initial_errors})
            continue
        final_check = partial(policy_errors, policy=policy, org_id=source.get("arcgis_org_id"), denylist=denylist)
        request_opener = partial(default_opener, check=final_check) if opener is default_opener else opener
        features: list[object] = []
        offset = 0
        try:
            while True:
                query = (
                    f"{layer}/query?where=1%3D1&outFields={quote(field, safe='')}&outSR=4326&f=geojson"
                    f"&resultOffset={offset}&resultRecordCount=1000"
                )
                request_errors = policy_errors(
                    query,
                    policy,
                    source.get("arcgis_org_id"),
                    denylist,
                    _redirect_chain(policy, source.get("arcgis_org_id"), denylist) if online else None,
                )
                if request_errors:
                    raise ValueError("; ".join(request_errors))
                final_url, data = request_opener(query)
                final_errors = final_check(final_url)
                if final_errors:
                    raise ValueError("; ".join(final_errors))
                page = json.loads(data.decode("utf-8"))
                if not isinstance(page, dict):
                    raise ValueError("invalid GeoJSON response")
                page_features = page.get("features", [])
                if not isinstance(page_features, list):
                    raise ValueError("invalid GeoJSON features")
                if not page_features:
                    break
                features.extend(page_features)
                properties = page.get("properties")
                more = page.get("exceededTransferLimit") is True or (
                    isinstance(properties, dict) and properties.get("exceededTransferLimit") is True
                )
                if not more:
                    break
                # Servers may cap a page below the requested count; advance by what was returned.
                offset += len(page_features)
        except Exception as error:  # Network and malformed-page errors are isolated per source.
            results.append({"source_id": source_id, "status": "error", "error": str(error)})
        else:
            write_json(
                root / "cache" / "geometry" / f"{source_id}.geojson",
                {"type": "FeatureCollection", "features": features},
            )
            results.append({"source_id": source_id, "status": "new"})
        finally:
            sleep(delay)
    return results


def _state_sources(root: Path) -> dict:
    """Build stable statute source records from non-empty state-rule evidence."""
    jurisdictions: dict[str, str] = {}
    for jid in jurisdiction_ids(root):
        document = read_json(root / "jurisdictions" / jid / "jurisdiction.json")
        if isinstance(document, dict) and isinstance(document.get("state"), str):
            jurisdictions[jid] = document["state"]
    rows: dict[str, list[tuple[str, dict]]] = {}
    for path in sorted((root / "state_rules").glob("[A-Z][A-Z].json")):
        document = read_json(path)
        if not isinstance(document, list):
            continue
        for row in document:
            if isinstance(row, dict) and row.get("effect") != "none_found" and isinstance(row.get("url"), str):
                rows.setdefault(row["url"], []).append((path.stem, row))
    existing_path = root / "state_rules" / "sources.json"
    existing_document = read_json(existing_path) if existing_path.exists() else {"sources": []}
    existing = {
        item.get("url"): item
        for item in existing_document.get("sources", [])
        if isinstance(existing_document, dict) and isinstance(item, dict) and isinstance(item.get("url"), str)
    }
    sources: list[dict] = []
    for number, url in enumerate(sorted(rows), 1):
        state, row = sorted(rows[url], key=lambda item: item[0])[0]
        matches = sorted(jid for jid, jurisdiction_state in jurisdictions.items() if jurisdiction_state == state)
        if not matches:
            continue
        source = dict(existing.get(url, {}))
        # The sources schema requires one jurisdiction even for statewide statutes.
        source.update(
            {
                "source_id": source.get("source_id", f"{state.lower()}-statute-{number}"),
                "jurisdiction_id": matches[0],
                "kind": "statute",
                "url": url,
                "source_date": row.get("effective_date", "unknown"),
                "licence_terms": {"text": "Enacted state law; public record."},
                "redistribute_geometry": "unknown",
                "triage": "ok",
            }
        )
        sources.append(source)
    return {"sources": sources}


def fetch_state_rules(
    root: Path,
    opener: Opener = default_opener,
    now: Callable[[], str] = utc_now,
    delay: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Fetch distinct primary statute sources referenced by state-rule rows."""
    document = _state_sources(root)
    denylist = load_denylist(root / "policy" / "denylist.txt")
    results: list[dict] = []
    for source in document["sources"]:
        url = source["url"]

        def final_check(final_url: str, requested: str = url) -> list[str]:
            # Statutes have no per-state host list, so a redirect must stay on the host triage approved.
            if urlsplit(final_url).hostname != urlsplit(requested).hostname:
                return [f"redirected off the statute host: {final_url}"]
            return check_url(final_url, denylist)

        request_opener = partial(default_opener, check=final_check) if opener is default_opener else opener
        results.append(
            _fetch_source(root, source, request_opener, check_url(url, denylist), final_check, now, delay, sleep)
        )
    # Only fetched statutes are recorded: the sources schema requires sha256 and fetched_at.
    document["sources"] = [source for source in document["sources"] if "sha256" in source and "fetched_at" in source]
    write_json(root / "state_rules" / "sources.json", document)
    return results


def cli(args: argparse.Namespace) -> int:
    """Run fetches selected by the shared command-line parser."""
    if len(args.jurisdiction_ids) == 1 and not args.single:
        raise SystemExit("fetching one jurisdiction requires --single")
    results = [
        result
        for jid in args.jurisdiction_ids
        for result in fetch_jurisdiction(args.root, jid, online=args.online, delay=args.delay)
    ]
    if args.state_rules:
        results.extend(fetch_state_rules(args.root, delay=args.delay))
    if args.geometry:
        results.extend(
            result
            for jid in args.jurisdiction_ids
            for result in fetch_geometry(args.root, jid, online=args.online, delay=args.delay)
        )
    for result in results:
        print(f"{result['source_id']}: {result['status']}")
    failed = sum(result["status"] in {"refused", "error"} for result in results)
    print(f"fetch: {len(results)} sources, {failed} failed")
    return 1 if failed else 0
