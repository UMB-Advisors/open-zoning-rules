"""Regression coverage for Z08 source-policy hardening."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from ozr.contamination import check_url, load_denylist
from ozr.fetch import default_opener, policy_errors
from ozr.triage import host_allowed


def test_arcgis_org_exception_requires_service_host_and_first_path_segment() -> None:
    policy = {"hosts": ["hcfl.gov"], "arcgis_org_ids": ["apTfC6SUmnNfnxuF"]}
    org_id = "apTfC6SUmnNfnxuF"
    unapproved = "https://unapproved.example/apTfC6SUmnNfnxuF/code.pdf"

    assert not host_allowed(unapproved, policy, org_id)
    assert not host_allowed("https://www.arcgis.com/sharing/rest/content/items/abc?f=json", policy, org_id)
    assert host_allowed(
        "https://services3.arcgis.com/apTfC6SUmnNfnxuF/arcgis/rest/services/Zoning/FeatureServer/0", policy, org_id
    )
    assert not host_allowed(
        "https://services3.arcgis.com/other/arcgis/rest/services/apTfC6SUmnNfnxuF/FeatureServer/0", policy, org_id
    )
    assert policy_errors(unapproved, policy, org_id, load_denylist())


def test_default_opener_refuses_redirect_before_contacting_banned_server() -> None:
    class ServerA(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.server.hits.append(self.path)  # type: ignore[attr-defined]
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{server_b.server_port}/bounced")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: object) -> None:
            pass

    class ServerB(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.server.hits.append(self.path)  # type: ignore[attr-defined]
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{server_a.server_port}/finish")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server_a = ThreadingHTTPServer(("127.0.0.1", 0), ServerA)
    server_b = ThreadingHTTPServer(("127.0.0.1", 0), ServerB)
    server_a.hits = []  # type: ignore[attr-defined]
    server_b.hits = []  # type: ignore[attr-defined]
    threads = [threading.Thread(target=server.serve_forever) for server in (server_a, server_b)]
    for thread in threads:
        thread.start()
    try:
        url = f"http://127.0.0.1:{server_a.server_port}/start"
        with pytest.raises(RuntimeError, match="refused URL"):
            default_opener(url, check=lambda value: ["banned"] if f":{server_b.server_port}" in value else [])
        assert server_b.hits == []  # type: ignore[attr-defined]
    finally:
        for server in (server_a, server_b):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


def test_check_url_does_not_follow_an_already_banned_url() -> None:
    calls: list[str] = []
    errors = check_url("https://library.municode.com/x", load_denylist(), chain=lambda url: calls.append(url) or [])

    assert errors
    assert calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://library.municode\u3002com/code",
        "https://LIBRARY.MUNICODE.COM/x",
        "https://library\uff0emunicode\uff0ecom/",
    ],
)
def test_check_url_normalizes_unicode_and_case_for_denylist(url: str) -> None:
    assert any("banned host" in error for error in check_url(url, load_denylist()))


def test_check_url_allows_ordinary_host_after_normalization() -> None:
    assert check_url("https://www.example.gov/x", load_denylist()) == []
