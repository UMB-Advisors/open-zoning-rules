"""Check repository evidence links against the source policy."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\"']+")
TEXT_SUFFIXES = {".json", ".md", ".csv", ".txt", ".yaml", ".yml"}
USER_AGENT = (
    "open-zoning-rules/0.1 (+https://github.com/UMB-Advisors/open-zoning-rules; "
    "contact: https://github.com/UMB-Advisors/open-zoning-rules/issues)"
)


def load_denylist(path: Path | None = None) -> frozenset[str]:
    """Load uncommented domain names from the policy file."""
    path = path or Path(__file__).resolve().parents[2] / "policy" / "denylist.txt"
    return frozenset(
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def normalize_host(host: str) -> str | None:
    """Return an IDNA-normalized hostname, or None when it cannot be normalized."""
    host = host.strip().lower()
    if "%" in host:
        return None
    if host.startswith("["):
        host = host.split("]", 1)[0][1:]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    try:
        return host.rstrip(".").encode("idna").decode("ascii") or None
    except UnicodeError:
        return None


def host_banned(host: str, denylist: frozenset[str]) -> bool:
    """Return whether host is a listed domain or one of its subdomains."""
    normalized = normalize_host(host)
    return normalized is not None and any(
        normalized == domain or normalized.endswith(f".{domain}") for domain in denylist
    )


def _url_errors(url: str, denylist: frozenset[str]) -> list[str]:
    parsed = urllib.parse.urlsplit(url)
    if "%" in parsed.netloc:
        return [f"percent-encoded host: {url}"]
    try:
        host = parsed.hostname
    except ValueError:
        host = None
    normalized_host = normalize_host(host) if host else None
    if not normalized_host:
        return [f"unparseable/no host: {url}"]
    if parsed.scheme.lower() != "https":
        return [f"not https: {url}"]
    if host_banned(normalized_host, denylist):
        return [f"banned host: {url}"]
    return []


def check_url(url: str, denylist: frozenset[str], chain: Callable[[str], list[str]] | None = None) -> list[str]:
    """Return policy errors for a URL and, optionally, its redirect chain."""
    errors = _url_errors(url, denylist)
    if errors or chain is None:
        return errors
    for index, target in enumerate(chain(url)):
        if index == 0 and target == url:
            continue
        errors.extend(f"redirect target: {error}" for error in _url_errors(target, denylist))
    return errors


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _response(url: str, method: str):
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        return opener.open(request, timeout=20)
    except urllib.error.HTTPError as error:
        return error


def follow_redirects(url: str, refuse: Callable[[str], bool] | None = None) -> list[str]:
    """Return a manually followed HTTP redirect chain, up to ten hops."""
    chain = [url]
    current = url
    for _ in range(10):
        response = _response(current, "HEAD")
        if response.code in {405, 501}:
            response.close()
            response = _response(current, "GET")
        try:
            location = response.headers.get("Location")
            code = response.code
        finally:
            response.close()
        if not (300 <= code < 400 and location):
            return chain
        current = urllib.parse.urljoin(current, location)
        chain.append(current)
        if (refuse or (lambda target: bool(_url_errors(target, load_denylist()))))(current):
            return chain
    raise RuntimeError(f"too many redirects: {url}")


def _tree_urls(root: Path) -> list[tuple[Path, str]]:
    urls: list[tuple[Path, str]] = []
    for directory in ("jurisdictions", "state_rules", "releases"):
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="ignore")
                urls.extend((path, match.rstrip(".,;:!?)]}")) for match in URL_RE.findall(text))
    return urls


def scan_tree(root: Path, denylist: frozenset[str], chain: Callable[[str], list[str]] | None = None) -> list[str]:
    """Scan evidence-bearing text files below root for disallowed URLs."""
    errors: list[str] = []
    for path, url in _tree_urls(root):
        errors.extend(f"{path.relative_to(root)}: {error}" for error in check_url(url, denylist, chain))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args(argv)
    denylist = load_denylist()
    chain = follow_redirects if args.online else None
    errors = scan_tree(args.root, denylist, chain)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"contamination check: ok ({len(_tree_urls(args.root))} urls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
