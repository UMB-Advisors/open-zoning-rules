# open-zoning-rules

An open dataset of US local zoning use rules for industrial-scale facility types. Each jurisdiction, district, and use-class cell records a status, exact evidence quote, section, primary-source URL, source date, and confidence grade.

Status: pre-release, Z0 pilot.

## Use classes

| Key | Use class |
| --- | --- |
| `datacenter` | Datacenter |
| `warehouse_distribution` | Warehouse and distribution |
| `heavy_industrial_hazmat` | Heavy industrial and hazardous materials |
| `lp_gas` | LP-gas storage and transfill |
| `cannabis_cultivation_processing` | Cannabis cultivation and processing |
| `utility_generation` | Utility-scale generation |
| `battery_storage` | Battery energy storage |

## Statuses

| Status | Meaning |
| --- | --- |
| `permitted` | Allowed by right, possibly subject to objective standards |
| `conditional` | Allowed only after a discretionary approval (conditional use, special exception, special use permit) |
| `prohibited` | Expressly not allowed |
| `unlisted` | The use is not named in the code and no definition captures it. Usually means a text amendment or a use determination is needed |

## Confidence grades

| Grade | Meaning |
| --- | --- |
| A | A human checked the cell against the source; never a legal sign-off. |
| B | The extracting model and two independent reviewer models agree, and every quote matches the source text. |
| C | Extracted and quote-checked, but the reviewers disagreed or only one ran. |

A cell drops one grade when its source has not been re-checked for 12 months. Cells in planned-development or conditionally rezoned districts are capped at C, because the rezoning case file governs those parcels.

## Use at your own risk

This is a research dataset, not a legal determination. It is published as is, with no warranty. Before relying on any answer, get outside confirmation at every grade, including A: a zoning verification letter or use determination from the jurisdiction's planning department, or advice from a land-use attorney or planner.

## Sources policy

Only primary sources are accepted: the jurisdiction's own site and GIS. Third-party hosts are denied in [policy/denylist.txt](policy/denylist.txt) and checked in CI.

## Licences

Code is Apache-2.0 under [LICENSE](LICENSE). Data is CC-BY-4.0 under [DATA_LICENSE](DATA_LICENSE). Suggested attribution: “open-zoning-rules contributors, CC-BY-4.0”.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
uv run python -m ozr.contamination
```

## Contributions

Correction PRs are welcome once the evidence template lands. Corrections are treated as claims and verified against the cited source.
