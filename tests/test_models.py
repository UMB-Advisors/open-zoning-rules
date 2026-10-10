"""Offline contract tests for the blind model CLI adapters."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from ozr.models import ModelError, parse_json_object, run_claude, run_codex, run_grok


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


def test_claude_adapter_strips_environment_and_encodes_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = (Path(__file__).parent / "fixtures" / "cli" / "claude_stream.jsonl").read_text()
    image = tmp_path / "table.png"
    image.write_bytes(b"image bytes")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_TOKEN", "secret")

    def runner(argv, **kwargs):
        assert argv[:4] == ["claude", "-p", "--model", "claude-sonnet-5-5"]
        assert kwargs["cwd"] == tmp_path
        assert "CLAUDECODE" not in kwargs["env"]
        assert not any(key.startswith("CLAUDE_CODE_") for key in kwargs["env"])
        content = __import__("json").loads(kwargs["input"])["message"]["content"]
        assert base64.b64decode(content[0]["source"]["data"]) == b"image bytes"
        return _completed(fixture)

    result = run_claude("prompt", [image], tmp_path, runner=runner, clock=iter((1.0, 1.5)).__next__)
    assert (result.text, result.input_tokens, result.output_tokens, result.cache_write_tokens) == ("Red", 2, 4, 634)
    assert result.cost_usd == pytest.approx(0.00258)


def test_codex_adapter_copies_images_and_parses_usage(tmp_path: Path) -> None:
    fixture = (Path(__file__).parent / "fixtures" / "cli" / "codex_events.jsonl").read_text()
    image = tmp_path.parent / "input.png"
    image.write_bytes(b"image")

    def runner(argv, **kwargs):
        assert argv == [
            "codex",
            "exec",
            "-p",
            "balanced",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-c",
            "web_search=disabled",
            "-C",
            str(tmp_path),
            "-i",
            "input.png",
            "--",
            "-",
        ]
        assert kwargs["cwd"] == tmp_path
        assert (tmp_path / "input.png").read_bytes() == b"image"
        return _completed(fixture)

    result = run_codex("prompt", [image], tmp_path, runner=runner, clock=iter((1.0, 1.25)).__next__)
    assert (result.text, result.input_tokens, result.cache_read_tokens, result.output_tokens) == ("Red", 18928, 9600, 5)
    assert result.cost_usd is None


def test_grok_adapter_is_text_only(tmp_path: Path) -> None:
    fixture = (Path(__file__).parent / "fixtures" / "cli" / "grok.json").read_text()

    def runner(argv, **kwargs):
        assert argv == [
            "grok",
            "--prompt-file",
            "prompt.txt",
            "--output-format",
            "json",
            "--disable-web-search",
            "--tools",
            "",
            "--no-subagents",
            "--cwd",
            str(tmp_path),
        ]
        assert kwargs["input"] == ""
        assert (tmp_path / "prompt.txt").read_text() == "prompt"
        return _completed(fixture)

    result = run_grok("prompt", tmp_path, runner=runner, clock=iter((1.0, 1.5)).__next__)
    assert (result.model, result.input_tokens, result.cache_read_tokens, result.output_tokens) == (
        "grok-4.7-build",
        32459,
        2304,
        56,
    )


def test_model_error_never_contains_prompt(tmp_path: Path) -> None:
    def runner(_argv, **_kwargs):
        return _completed("", returncode=1, stderr="bad CLI")

    with pytest.raises(ModelError, match="bad CLI") as error:
        run_grok("private prompt", tmp_path, runner=runner)
    assert "private prompt" not in str(error.value)


def test_parse_json_object_handles_fences_and_rejects_arrays() -> None:
    assert parse_json_object('```json\n{"ok": true}\n```') == {"ok": True}
    with pytest.raises(ModelError):
        parse_json_object("[1, 2]")
