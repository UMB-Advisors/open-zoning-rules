# Z0 pilot report (v0.2.0)

**Date:** 2026-10-11 · **Covers:** grading, measurement (Z0.6), release preparation (Z0.7) and the gate fixes (Z0.8) for the Z0 pilot. Supersedes `docs/Z0_report.v0.1.0.md`, which is kept. **Status: the release gate passes; not tag-ready.** One published known-answer cell is still wrong, the human audit is owed, and only 5 of 10 jurisdictions are in.

## TL;DR

- **The release gate passes.** `ozr release` exits 0 and the consumer contract `zoning-atlas.release/0.1` reports 0 errors. Coverage now follows spec section 7: a cell that fails a gate is withheld and listed, with the gate and run id, in `releases/v0.1.0/withheld.json`.
- **The stricter gates publish fewer cells: 550 of 910, down from 776.** 205 of the 226 cells no longer published are `unlisted` cells whose model outputs did not explain every occurrence of a class term in the code. No model was re-run; recovering them needs a prompt that lists every occurrence, and new runs.
- **Known answers: 15 match, 2 miss, 4 unscored** (before the fixes: 15, 5, 1). Pittsylvania M-2 and Douglas OI and C-H are now withheld, not corrected. **Loudoun MR-HI is still published wrong**: the cited 2023 table says P, and the amendment that makes it conditional is not applied. That needs a maintainer decision.
- **The known-answer score is no longer a blind check.** The gates were fixed against those exact cells. The 60-cell human audit is now the only blind check of the pipeline.
- **The Z0 exit is still not met:** 5 of 10 jurisdictions, and listed-status agreement has too few permitted and conditional cells to judge.

## What is measured

Everything below is **model-panel agreement**: how often the extractor agrees with a reference built from two other models, codex and grok, which labelled the same text blind. The reference set, model-gold, is the cells where codex and grok agree with each other.

> What is measured is agreement between the extractor and a reference built from two other models that labelled the same text blind. It does not measure agreement with the law as a planner would read it: three models reading the same ambiguous table the same wrong way is invisible to this method.

> **Reliance notice.** This is a research dataset, not a legal determination. Before relying on any answer, at every grade, get a zoning verification letter or use determination from the planning department, or a land-use attorney or planner.

Both texts are carried verbatim in `reports/accuracy.json` (`caveat`, `reliance_notice`) and in the release manifest (`reliance_notice`).

## Scope

| Jurisdiction | Districts | Universe (districts x 7 classes) | Published | Withheld: no extractor cell passed | Withheld: no reviewer label passed |
|---|---|---|---|---|---|
| us-5183136 Town of Warrenton, VA | 12 | 84 | 44 | 35 | 5 |
| us-51143 Pittsylvania County, VA | 14 | 98 | 53 | 41 | 4 |
| us-12069 Lake County, FL (unadopted draft) | 22 | 154 | 60 | 76 | 18 |
| us-51107 Loudoun County, VA | 57 | 399 | 288 | 104 | 7 |
| us-13097 Douglas County, GA | 25 | 175 | 105 | 64 | 6 |
| **Total** | 130 | **910** | **550** | **320** | **40** |

`python -m ozr grade` writes every withheld key to `jurisdictions/<jid>/cells.withheld.json` with the gate that failed (extraction, review or grade), its errors and the run id. No cell failed at grade itself.

Measurement and grading ran on these five only. The other five have no ordinance text in the cache (see the analyst-fetch list).

## Gates

| Gate | Value | Threshold | Result |
|---|---|---|---|
| Listed status (permitted, conditional, prohibited) | 0.972 (model-gold: permitted 18, conditional 14, prohibited 185) | at least 0.90, with at least 50 model-gold cells per status | **insufficient data** |
| Unlisted recall | 0.985 (135 model-gold unlisted) | at least 0.85, 50 cells | **pass** |
| Unlisted precision | 1.000 (133 extractor-unlisted model-gold cells) | at least 0.85, 50 cells | **pass** |
| Disputed share, all cells | 0.021 (19 / 910) | at most 0.15 | **pass** |
| Disputed share, cells both reviewers labelled | 0.051 (19 / 371) | (not a plan gate) | reported |
| Excluded from model-gold (disputed + reviewer missing) | 0.613 (558 / 910) | (not a plan gate) | reported; a high exclusion rate is itself a finding |
| Known-answer cells | 15 match, 2 miss, 4 unscored | any miss investigated before release | **2 misses**, see below |
| Mutation test (pre-set criterion) | Douglas met; Loudoun not met | the pipeline changes with the text | **mixed**, unchanged from v0.1.0 |
| Consumer contract `zoning-atlas.release/0.1` | 0 errors over 550 records | 0 errors | **pass** |
| Release gate (`ozr release`: schema, hashes, cell gates, coverage with recorded withholding, statute quotes) | 0 errors | 0 errors | **pass** |
| Z0 phase exit: 10 jurisdictions | 5 | 10 | **fail** |

**These figures are not comparable with v0.1.0.** The fixed gates rejected many reviewer labels as well as extractor cells (gate rejection rate: extractor 35.2%, codex 38.8%, grok 49.9%, up from 4.9%, 23.8% and 26.2%), so model-gold now rests on fewer and easier cells. Codex-grok kappa over the 371 cells both labelled is 0.912 and the lower bound, counting every disputed cell as a miss, is 0.927. Both rose for the same reason.

### What the gates check

The v0.1.0 report said the table gate checks the row label, the column header and the symbol separately. That was wrong: the symbol was never checked. From Z0.8:

- **Table evidence.** The quote must read `<row_label> | <column_header> | <symbol>`. The row label, column header and section must occur on token boundaries. The symbol must map to the status through the jurisdiction's quoted table key or the taxonomy's local forms (a blank only through a quoted key). The symbol must also sit in the cited column of the reconstructed table grid.
- **Absence evidence.** Every occurrence of every class term in the whole jurisdiction's text, with hyphen and space treated alike and `-s`, `-es` and `-ies` plurals, must lie inside an explanation quote that says more than the term itself.

### By jurisdiction

| Jurisdiction | Model-gold | Disputed | Reviewer missing | Disputed / both labelled | Listed agreement | Unlisted recall | Unlisted precision |
|---|---|---|---|---|---|---|---|
| Warrenton | 35 | 1 | 48 | 0.028 | (no listed gold) | 1.000 | 1.000 |
| Pittsylvania | 17 | 9 | 72 | 0.346 | 1.000 | 1.000 | 1.000 |
| Lake (draft) | 60 | 0 | 94 | 0.000 | 1.000 | 0.955 | 1.000 |
| Loudoun | 194 | 3 | 202 | 0.015 | 0.961 | 1.000 | 1.000 |
| Douglas | 46 | 6 | 123 | 0.115 | 1.000 | (no unlisted gold) | (none) |

## Known-answer cells

`tests/known_answers.json` was frozen before the first extraction call and was not edited. 21 of its cells fall in the five extracted jurisdictions.

> **This is no longer a blind check.** The table-grid and per-occurrence absence gates were designed, and their tests written, against Pittsylvania M-2 and Douglas OI and C-H. The score below therefore shows that the fixes catch the cells they were built for. It says nothing about how often the pipeline is right elsewhere. The 60-cell human audit is now the only blind check.

| Result | Before the Z0.8 fixes | After |
|---|---|---|
| Extractor matches the cited status | 15 | 15 |
| Miss, cell published | 4: Loudoun MR-HI, Pittsylvania M-2, Douglas OI, Douglas C-H | 1: Loudoun MR-HI |
| Miss, cell withheld | 1: Warrenton I | 1: Warrenton I |
| Unscored (no extractor cell passed the gates) | 1: Lake LM | 4: Lake LM, Pittsylvania M-2, Douglas OI, Douglas C-H |

The "before" column uses the corrected rule that a miss is a mismatch with the expected status. The v0.1.0 `accuracy.json` listed 7 misses because it also counted Loudoun IP and GI, which match the expected status (conditional, by the 2025 amendment) and differ only from the pre-amendment table in the cached source. They are now listed separately as source-text differences.

| Cell | Expected | Now | Why |
|---|---|---|---|
| us-51143/M-2 `datacenter` | conditional | withheld | "data center" occurs 33 times in the code; the extractor explained 5. The unexplained ones include the Sec. 35-403 special-use list |
| us-13097/OI `datacenter` | conditional | withheld | The 518210 row has S in the OI column of Table 2.2; the extractor cited a blank |
| us-13097/C-H `datacenter` | prohibited | withheld | The C-H column is blank; the extractor cited S. The C-H-C overlay cell read the same column and is withheld too |
| us-51107/MRHI `datacenter` | conditional | **published `permitted`, grade C, `single`** | Not a gate gap. The cited 2023 table shows P, so every gate passes. ZOAM-2024-0001 (adopted 2025-03-18) requires a special exception in IP, GI and MR-HI. The extractor applied it for IP and GI from a prose source, but not for MR-HI |
| us-5183136/I `datacenter` | prohibited | withheld | Unchanged: both reviewer labels fail the gates, and the taxonomy question (a use the code defines but lists in no district) is open |

**MR-HI blocks the tag** until the maintainer decides how to handle it: record ZOAM-2024-0001 as an amendment record (spec 3.1 rule 5), re-extract Loudoun, or correct the cell through the two-maintainer path (spec 12).

## Mutation test

From the Z0.5 report, criterion fixed before the runs:

| Jurisdiction | Flipped cells | Moved the expected way | Noise (unflipped cells that changed) | Result |
|---|---|---|---|---|
| Douglas | 13 | 13 (1.00) | 2.6% | criterion met |
| Loudoun | 25 | 9 (0.36) | 0.3% | **criterion not met** |

For Loudoun, 10 of the 25 counted cells sit on unflipped rows of other tables. On the 15 cells whose column really was flipped, 9 moved the expected way (0.60). That figure comes from a hand analysis made after the run, not from the pre-set measure.

`reports/accuracy.json` also carries Lake's `mutation.json`. That run used the superseded Z0.4 text, before Z0.4b rebuilt the tables, and it did not meet its criterion. It was not re-run.

## Human audit

The published set changed, so the sample was redrawn. 17 of the 60 cells in `audit/z0_audit_sheet.v0.1.0.csv` are no longer published. `audit/z0_audit_sheet.v0.2.0.csv` uses the same sampler and seed 20261011 (sha256 `93c511ad...2acd`). It has 15 cells per status, spread across the five jurisdictions; 28 rows are also in v0.1.0. v0.1.0 is kept unchanged.

- 27 of the 60 cells are model-gold, so the human-vs-model-gold agreement will rest on n = 27. The human-vs-extractor agreement uses all 60. At n = 60 the 95% interval is about +/-8 points.
- No auditor is named, and no labels exist yet. **The audit is owed, and it is now the only blind check.**

## Cost and time

Read from the run ledgers (`runs/<id>.jsonl`). Costs are as `claude -p` and `grok` reported them. Codex calls are unpriced because `policy/model_prices.json` lists no codex prices, so codex is given as tokens. Hours are summed model wall time, not step wall time.

**One clean pass:** the final extraction, codex review and grok review for each jurisdiction.

| Jurisdiction | Claude extract (USD) | Grok review (USD) | Priced total (USD) | Codex tokens (unpriced) | Model hours |
|---|---|---|---|---|---|
| Warrenton | 2.08 | 1.99 | 4.07 | 574,969 | 0.61 |
| Pittsylvania | 2.48 | 3.15 | 5.63 | 473,541 | 1.10 |
| Lake (draft) | 2.37 | 0.94 | 3.30 | 468,345 | 1.51 |
| Loudoun | 11.32 | 16.97 | 28.28 | 3,192,672 | 4.41 |
| Douglas | 9.53 | 6.98 | 16.52 | 2,389,983 | 2.56 |
| **Median (range)** | | | **5.63 (3.30 to 28.28)** | | **1.51 (0.61 to 4.41)** |

**Total spent**, including superseded runs, the first extraction attempts and the mutation runs (Lake, Loudoun and Douglas only): $159.25 priced, a median of $12.92 per jurisdiction (range $8.51 to $75.61), 12.3M codex tokens and 24.1 model hours. The mutation and superseded runs skew this figure, so use the clean pass for planning.

`reports/accuracy.json` reports `cost.dollars` and `cost.hours` as null. Its rule drops a jurisdiction from the summary when any call in it is unpriced, and every jurisdiction has codex calls. The figures above are computed from the same ledgers with codex left out of the dollar total.

Human minutes were not recorded in the ledgers for triage, analyst-fetch requests or report review.

The Z0.8 gate fixes made no model calls: the committed model outputs were re-gated with `python -m ozr regate`, so the figures above are unchanged.

## Swaps

From `docs/swap_log.v0.1.0.md`:

| Out | In | Reason |
|---|---|---|
| City of Port St. Lucie, FL | Lake County, FL | No primary copy of the code. The data-center withdrawal was in the unincorporated county, not the city |
| Prince William County, VA | Fauquier County, VA | No adopted ordinance on the county's own domain |
| (Coweta County, GA stays) | | The swap rule was triggered, but the only GA alternate fails the same test |

## Analyst-fetch list

These five have no ordinance text the pipeline may fetch. A person has to obtain the adopted code from the jurisdiction itself (a clerk request or a manual download from its own site), never from a third-party code host.

| Jurisdiction | What is needed | Why |
|---|---|---|
| us-12057 Hillsborough County, FL | The Land Development Code use table and unlisted-use clause | Its own site carries only replacement pages (Supplement 50) with no use table |
| us-12105 Polk County, FL | The Land Development Code | Copies are by public records request |
| us-1304000 City of Atlanta, GA | The zoning ordinance, including the 2024 data-center ordinances | The city site refuses automated fetches |
| us-13077 Coweta County, GA | The zoning ordinance | Reachable only through a third-party publisher |
| us-51061 Fauquier County, VA | The zoning ordinance article PDFs | The county site refuses automated fetches |

## Release

`python -m ozr release --version 0.1.0 --published 2026-10-11` wrote `releases/v0.1.0/` with `manifest.json` and ten files: `cells.json`, `cells.parquet`, `jurisdictions.json`, `sources.json`, `amendments.json`, `state_rules.json`, `withheld.json`, `taxonomy.json`, `accuracy.json` and `denylist.txt`. It exits 0. The hashes are in `docs/test-results/z0.8_gate_fixes.v0.1.0.md`.

- **Consumer contract:** `ozr.contract.check_release(manifest)` returns no errors, and every record passes `check_answer`. The consumer contract reference implementation reads only the manifest and the files it lists, so the added `withheld.json` is a listed, hashed JSON file and changes nothing for the consumer.
- **Coverage (decision: option a).** A district and class with no published cell must be listed in `withheld.json` with the gate that failed and the run id, and a failure record with the same key and run id must exist in the grade output. 360 keys are withheld this way. A missing key with no failure record still fails the gate.
- **Statute quotes.** All 8 match. The two Georgia enrolled bills are matched after the source text's printed line counter is stripped; the quotes themselves are never normalised. The Virginia quote's data was corrected to read "§ 4.1-630," as the statute does.
- **No district polygons.** Every zoning layer's `redistribute_geometry` is `unknown`, so no `districts.*.geoparquet` is written. The consumer has to resolve districts itself (spec 10, interface issue 1).
- **`amendments.json` is empty.** No jurisdiction has an amendment record. Lake's adopted 2026-09-08 data-center moratorium and Loudoun's ZOAM-2024-0001 are therefore not recorded. Lake's cells also come from an unadopted draft ordinance.
- **`schema_url`** points at `blob/v0.1.0/...`, a tag that does not exist yet.

## Still owed

1. **Loudoun MR-HI `datacenter`,** published wrong: an amendment record, a re-extraction, or a correction (see Known-answer cells).
2. **The human audit** on `audit/z0_audit_sheet.v0.2.0.csv`: name an auditor, label the 60 cells blind, and record the minutes. It is the only blind check left.
3. **Coverage of `unlisted`.** 205 previously published `unlisted` cells are withheld because no output explains every term occurrence. The prompt shows at most 5 lines per term, so recovering them needs a prompt that lists every occurrence, then a re-extraction and re-review.
4. **Lake.** Either record the moratorium and pending amendment as amendment records, or hold Lake out of v0.1.0 because its text is an unadopted draft. Its "P, C" table cells have no key and are withheld.
5. **The Warrenton taxonomy question** (a use the code defines but lists in no district).
6. **`taxonomy/v1.json`** still says the table symbol is checked only by reviewers; that text needs a taxonomy patch release.
7. **The five analyst-fetch jurisdictions**, without which the Z0 exit (10 jurisdictions) and the listed-status minimum counts cannot be met.
8. **Review and merge** of this stack, then the **tag** `v0.1.0` and a GitHub release carrying the data files, recorded as proof. None of these has been done.
