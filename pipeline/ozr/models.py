"""Blind, injectable adapters for the supported model CLIs."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ozr.common import read_json

SYSTEM = (
    "You extract structured data from legal text. Follow the user's instructions exactly and answer with JSON only."
)


CODEX_DISABLED = (
    "shell_tool",
    "unified_exec",
    "code_mode_host",
    "browser_use",
    "computer_use",
    "in_app_browser",
    "apps",
    "view_image",
)


# grok ignores an empty --tools allowlist and will read files; each built-in tool is removed by name instead.
GROK_DISALLOWED = (
    "read_file,search_replace,grep,list_dir,run_terminal_cmd,task,get_task_output,kill_task,web_fetch,"
    "enter_plan_mode,exit_plan_mode,ask_user_question,todo_write,monitor,search_tool,use_tool,workflow,"
    "send_feedback,image_gen,image_edit,image_to_video,reference_to_video,write"
)


class ModelError(RuntimeError):
    """Raised when a model CLI fails or does not emit its documented output."""


@dataclass
class ModelResult:
    """A model response and its normalized accounting fields."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float | None
    wall_s: float
    usage: dict


def _environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key != "CLAUDECODE" and not key.startswith("CLAUDE_CODE_")
    }


def _error(message: str, completed: Any | None = None) -> ModelError:
    stderr = "" if completed is None else str(getattr(completed, "stderr", ""))[-2000:]
    return ModelError(f"{message}: {stderr}".rstrip())


def _run(argv: list[str], prompt: str, workdir: Path, runner: Any, timeout: float, clock: Any) -> tuple[Any, float]:
    started = clock()
    try:
        completed = runner(
            argv,
            input=prompt,
            cwd=workdir,
            env=_environment(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ModelError(f"model CLI timed out after {timeout:g}s") from error
    wall_s = clock() - started
    if completed.returncode != 0:
        raise _error(f"model CLI exited {completed.returncode}", completed)
    return completed, wall_s


def _image_path(image: object) -> Path:
    if isinstance(image, Path):
        return image
    if isinstance(image, str):
        return Path(image)
    if isinstance(image, dict) and isinstance(image.get("path"), str):
        return Path(image["path"])
    raise TypeError("image must be a path or image record")


def _copy_images(images: list[object], workdir: Path) -> list[str]:
    names: list[str] = []
    for index, image in enumerate(images):
        source = _image_path(image)
        name = source.name
        if name in names:
            name = f"{index}-{name}"
        shutil.copyfile(source, workdir / name)
        names.append(name)
    return names


def _json_lines(stdout: str, completed: Any) -> list[dict]:
    try:
        records = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise _error(f"unparseable model output ({error.msg})", completed) from error
    if not all(isinstance(record, dict) for record in records):
        raise _error("unparseable model output", completed)
    return records


def run_claude(
    prompt: str,
    images: list[object],
    workdir: Path,
    model: str = "claude-sonnet-5-5",
    *,
    runner: Any = subprocess.run,
    clock: Any = time.monotonic,
    timeout: float = 1800,
) -> ModelResult:
    """Run Claude with no tools, inherited sessions, or Claude Code environment."""
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(_image_path(image).read_bytes()).decode(),
            },
        }
        for image in images
    ]
    content.append({"type": "text", "text": prompt})
    stdin = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
    argv = [
        "claude",
        "-p",
        "--model",
        model,
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        "",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt",
        SYSTEM,
    ]
    completed, wall_s = _run(argv, stdin, workdir, runner, timeout, clock)
    records = _json_lines(completed.stdout, completed)
    result = next((record for record in reversed(records) if record.get("type") == "result"), None)
    if not isinstance(result, dict) or result.get("is_error") or not isinstance(result.get("result"), str):
        raise _error("unparseable model output", completed)
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    model_usage = result.get("modelUsage") if isinstance(result.get("modelUsage"), dict) else {}
    returned_model = next(iter(model_usage), model)
    return ModelResult(
        text=result["result"],
        model=returned_model,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
        cost_usd=float(result["total_cost_usd"]) if result.get("total_cost_usd") is not None else None,
        wall_s=wall_s,
        usage=usage,
    )


def price(model: str, result: ModelResult) -> float | None:
    """Price a result from the optional local model-price policy."""
    path = Path(__file__).resolve().parents[2] / "policy" / "model_prices.json"
    document = read_json(path) if path.is_file() else {}
    prices = document.get("models", {}) if isinstance(document, dict) else {}
    entry = prices.get(model) if isinstance(prices, dict) else None
    fields = ("input", "cached_input", "output")
    if not isinstance(entry, dict) or not all(isinstance(entry.get(key), (int, float)) for key in fields):
        return None
    uncached = max(0, result.input_tokens - result.cache_read_tokens)
    total = uncached * entry["input"] + result.cache_read_tokens * entry["cached_input"]
    total += result.output_tokens * entry["output"]
    return total / 1_000_000


def run_codex(
    prompt: str,
    images: list[object],
    workdir: Path,
    profile: str = "balanced",
    *,
    runner: Any = subprocess.run,
    clock: Any = time.monotonic,
    timeout: float = 1800,
) -> ModelResult:
    """Run Codex from a directory containing only copied image inputs."""
    names = _copy_images(images, workdir)
    image_args = [part for name in names for part in ("-i", name)]
    argv = [
        "codex",
        "exec",
        "-p",
        profile,
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "-c",
        "web_search=disabled",
        # Blindness is enforced, not asked for: with no shell, exec, browser, app or MCP tool,
        # codex cannot read the repository (where the other answers live) or the web.
        "-c",
        "mcp_servers={}",
        *(part for feature in CODEX_DISABLED for part in ("--disable", feature)),
        "-C",
        str(workdir),
        *image_args,
        "--",
        "-",
    ]
    completed, wall_s = _run(argv, prompt, workdir, runner, timeout, clock)
    records = _json_lines(completed.stdout, completed)
    messages = [
        record.get("item", {}).get("text")
        for record in records
        if record.get("type") == "item.completed" and record.get("item", {}).get("type") == "agent_message"
    ]
    turns = [record.get("usage") for record in records if record.get("type") == "turn.completed"]
    if not messages or not isinstance(messages[-1], str) or not turns or not isinstance(turns[-1], dict):
        raise _error("unparseable model output", completed)
    usage = turns[-1]
    result = ModelResult(
        text=messages[-1],
        model=f"codex:{profile}",
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cache_read_tokens=int(usage.get("cached_input_tokens", 0)),
        cache_write_tokens=int(usage.get("cache_write_input_tokens", 0)),
        cost_usd=None,
        wall_s=wall_s,
        usage=usage,
    )
    result.cost_usd = price(result.model, result)
    return result


def run_grok(
    prompt: str,
    workdir: Path,
    *,
    runner: Any = subprocess.run,
    clock: Any = time.monotonic,
    timeout: float = 3600,
) -> ModelResult:
    """Run Grok on text-only inputs from its isolated working directory."""
    (workdir / "prompt.txt").write_text(prompt, encoding="utf-8")
    # --verbatim stops the CLI moving prompt text past ~100k characters into a side file,
    # which this tool-less reviewer cannot read.
    argv = [
        "grok",
        "--verbatim",
        "--prompt-file",
        "prompt.txt",
        "--output-format",
        "json",
        "--disable-web-search",
        "--disallowed-tools",
        GROK_DISALLOWED,
        "--no-subagents",
        "--cwd",
        str(workdir),
    ]
    completed, wall_s = _run(argv, "", workdir, runner, timeout, clock)
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise _error(f"unparseable model output ({error.msg})", completed) from error
    if not isinstance(response, dict) or not isinstance(response.get("text"), str):
        raise _error("unparseable model output", completed)
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    model_usage = response.get("modelUsage") if isinstance(response.get("modelUsage"), dict) else {}
    if len(model_usage) != 1:
        raise _error("unparseable model output", completed)
    return ModelResult(
        text=response["text"],
        model=next(iter(model_usage)),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
        cost_usd=float(response["total_cost_usd"]) if response.get("total_cost_usd") is not None else None,
        wall_s=wall_s,
        usage=usage,
    )


def parse_json_object(text: str) -> dict:
    """Parse the object embedded in a model response, optionally fenced as JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < start:
        raise ModelError("model output does not contain a JSON object")
    try:
        value = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as error:
        raise ModelError(f"model output is not JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ModelError("model output is not a JSON object")
    return value
