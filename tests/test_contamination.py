from ozr.contamination import check_url, host_banned, load_denylist, scan_tree


def test_url_policy_and_redirects() -> None:
    denylist = load_denylist()
    assert check_url("https://library.municode.com/fl/x/codes/code_of_ordinances", denylist)
    assert check_url("https://ecode360.com/12345", denylist)
    assert check_url("https://www.zoningatlas.org/", denylist)
    assert not check_url("https://notmunicode.com/x", denylist)
    assert check_url("http://www.example.gov/zoning.pdf", denylist)
    assert not check_url("https://www.example.gov/zoning.pdf", denylist)
    errors = check_url(
        "https://www.example.gov/code",
        denylist,
        lambda url: [url, "https://library.municode.com/x"],
    )
    assert any("redirect target" in error for error in errors)
    assert host_banned("library.municode.com.:443", denylist)


def test_consumer_contract_hosts_are_banned() -> None:
    denylist = load_denylist()
    expected = {"municode.com", "amlegal.com", "ecode360.com", "zoningatlas.org"}
    assert expected <= denylist
    expected.add("codelibrary.amlegal.com")
    assert all(host_banned(host, denylist) for host in expected)


def test_scan_tree(tmp_path) -> None:
    source = tmp_path / "jurisdictions" / "us-00000" / "sources.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"url": "https://library.municode.com/x"}')
    errors = scan_tree(tmp_path, load_denylist())
    assert errors and errors[0].startswith("jurisdictions/us-00000/sources.json:")
    source.write_text('{"url": "https://www.example.gov/x"}')
    assert scan_tree(tmp_path, load_denylist()) == []


def test_real_tree_is_clean() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert scan_tree(root, load_denylist()) == []
