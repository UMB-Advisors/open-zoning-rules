import subprocess

from ozr.fingerprints import digest, find_hits, main


def init_repo(path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "policy").mkdir()
    (path / "policy" / "fingerprints.txt").write_text("# configured here\n")
    (path / "sample.txt").write_text("ordinary content\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)


def test_find_hits() -> None:
    value = digest("Acme Widgets", "k")
    assert find_hits("we met ACME   widgets today", {value}, "k") == {"acme widgets"}
    assert not find_hits("acme only", {value}, "k")


def test_find_hits_ignores_spacing_and_punctuation() -> None:
    value = digest("Acme Widgets", "k")
    for text in ("AcmeWidgets ships", "the acme-widgets site", "acme_widgets"):
        assert find_hits(text, {value}, "k"), text


def test_main_allows_empty_configuration(tmp_path, capsys) -> None:
    init_repo(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0
    assert "none configured" in capsys.readouterr().out


def test_main_requires_key_when_configured(tmp_path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    (tmp_path / "policy" / "fingerprints.txt").write_text(digest("Acme Widgets", "k") + "\n")
    monkeypatch.delenv("FINGERPRINT_KEY", raising=False)
    assert main(["--root", str(tmp_path)]) == 2
    assert "FINGERPRINT_KEY" in capsys.readouterr().err


def test_main_reports_hits_without_term(tmp_path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    (tmp_path / "policy" / "fingerprints.txt").write_text(digest("Acme Widgets", "k") + "\n")
    (tmp_path / "sample.txt").write_text("Acme Widgets is present\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    monkeypatch.setenv("FINGERPRINT_KEY", "k")
    assert main(["--root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "sample.txt:1:" in output
    assert "Acme Widgets" not in output
