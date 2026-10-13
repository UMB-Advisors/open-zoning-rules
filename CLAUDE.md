# open-zoning-rules agent notes

Commands:

```sh
uv sync --locked
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run python -m ozr.contamination
uv run python -m ozr.fingerprints --rev-range A..B
```

Nothing private ever enters this repository: no client names, sites, runs, or briefs. Demand signal is confidential and the fingerprint check enforces it. Use primary sources only.

Show every new test failing first, with evidence in `docs/test-results/`. Docs are versioned `.md`. Commit messages use `type(scope): summary` followed by bullets. Open draft PRs and never push to main.
