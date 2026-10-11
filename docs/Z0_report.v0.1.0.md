# Z0 pilot report (v0.1.0)

**Date:** 2026-10-11 · **Covers:** grading, measurement (Z0.6) and release preparation (Z0.7) for the Z0 pilot. **Status: not tag-ready.** The consumer contract passes, but the repository's own release gate fails.

## TL;DR

- **The release gate fails, so v0.1.0 cannot be tagged.** The manifest passes the consumer contract `zoning-atlas.release/0.1`, but `ozr release` reports 134 district coverage errors and 3 statute-quote errors. The coverage gate requires a cell for every district and class, while spec section 7 withholds any cell that fails a gate. Both cannot hold, and resolving that is a decision for the maintainer.
- **The Z0 exit is not met.** Only 5 of the 10 pilot jurisdictions have ordinance text on their own hosts; the other 5 need an analyst fetch. Listed-status agreement is "insufficient data": there are 18 permitted and 16 conditional model-gold cells, and the minimum is 50 each. Unlisted recall (0.946), unlisted precision (1.000) and the disputed share (0.084) pass.
- **Nearly half the universe is excluded from model-gold.** In 365 of 910 cells at least one reviewer's label failed the gates, and 76 more are disputed, so 48.5% is excluded. Among cells both reviewers labelled, the disputed share is 13.9%, close to the 15% limit. Douglas alone is at 29.1%.
- **Four known-answer cells are wrong in the published set:** Loudoun MR-HI, Pittsylvania M-2 and Douglas OI and C-H, all `datacenter`. Two are gate gaps that the gates cannot see: a symbol attributed to the wrong table column, and an absence gate satisfied by one explained mention of a term. They block the tag.
- **Cost of one clean pass per jurisdiction (Claude and grok, priced):** median $5.63, range $3.30 to $28.28. Codex is unpriced: 7.1M tokens.

## What is measured

Everything below is **model-panel agreement**: how often the extractor agrees with a reference built from two other models, codex and grok, which labelled the same text blind. The reference set, model-gold, is the cells where codex and grok agree with each other.

> What is measured is agreement between the extractor and a reference built from two other models that labelled the same text blind. It does not measure agreement with the law as a planner would read it: three models reading the same ambiguous table the same wrong way is invisible to this method.

> **Reliance notice.** This is a research dataset, not a legal determination. Before relying on any answer, at every grade, get a zoning verification letter or use determination from the planning department, or a land-use attorney or planner.

Both texts are carried verbatim in `reports/accuracy.json` (`caveat`, `reliance_notice`) and in the release manifest (`reliance_notice`).

## Scope

| Jurisdiction | Districts | Universe (districts x 7 classes) | Published | Withheld at grade | No extractor cell passed the gates |
|---|---|---|---|---|---|
| us-5183136 Town of Warrenton, VA | 12 | 84 | 68 | 16 | 0 |
| us-51143 Pittsylvania County, VA | 14 | 98 | 72 | 19 | 7 |
| us-12069 Lake County, FL (unadopted draft) | 22 | 154 | 110 | 25 | 19 |
| us-51107 Loudoun County, VA | 57 | 399 | 356 | 29 | 14 |
| us-13097 Douglas County, GA | 25 | 175 | 170 | 0 | 5 |
| **Total** | 130 | **910** | **776** | **89** | **45** |

A cell is withheld at grade when no reviewer label for it passed the gates (`python -m ozr grade`). The last column counts keys where the extractor's own output failed the gates (Z0.4b), so there was nothing to grade. Withheld and rejected together are the 134 missing cells that fail the release coverage gate.

Measurement and grading ran on these five only. The other five have no ordinance text in the cache (see the analyst-fetch list).

## Gates

| Gate | Value | Threshold | Result |
|---|---|---|---|
| Listed status (permitted, conditional, prohibited) | 0.974 (222 of 228 model-gold cells; see note) | at least 0.90, with at least 50 model-gold cells per status | **insufficient data**: permitted 18, conditional 16, prohibited 194 |
| Unlisted recall | 0.946 | at least 0.85, 50 cells | **pass** (241 model-gold unlisted) |
| Unlisted precision | 1.000 | at least 0.85, 50 cells | **pass** |
| Disputed share, all cells | 0.084 (76 / 910) | at most 0.15 | **pass** |
| Disputed share, cells both reviewers labelled | 0.139 (76 / 545) | (not a plan gate) | reported |
| Excluded from model-gold (disputed + reviewer missing) | 0.485 (441 / 910) | (not a plan gate) | reported; a high exclusion rate is itself a finding |
| Known-answer cells | 15 match, 5 miss, 1 unscored | any miss investigated before release | **5 misses**, see below |
| Mutation test (pre-set criterion) | Douglas met; Loudoun not met | the pipeline changes with the text | **mixed**, see below |
| Consumer contract `zoning-atlas.release/0.1` (`ozr.contract.check_release`) | 0 errors | 0 errors | **pass** |
| Release gate (`ozr release`: schema, hashes, cell gates, coverage, statute quotes) | 137 errors | 0 errors | **fail** |
| Z0 phase exit: 10 jurisdictions | 5 | 10 | **fail** |

Note on listed status: the value is the share of the 228 model-gold permitted, conditional and prohibited cells where the extractor's status matches. With too few permitted and conditional cells, the pooled figure is dominated by prohibited cells and is not evidence for the other two.

**Other measures** (from `reports/accuracy.json`):
- Lower bound, counting every disputed cell as an extractor miss: 0.826.
- Codex and grok agreement, Cohen's kappa over the 545 cells both labelled: 0.759.
- Gate rejection rate: extractor 4.9%, codex 23.8%, grok 26.2%.

### By jurisdiction

| Jurisdiction | Model-gold | Disputed | Reviewer missing | Disputed / both labelled | Listed agreement | Unlisted recall | Unlisted precision |
|---|---|---|---|---|---|---|---|
| Warrenton | 59 | 1 | 24 | 0.017 | (no listed gold) | 1.000 | 1.000 |
| Pittsylvania | 17 | 9 | 72 | 0.346 | 1.000 | 1.000 | 1.000 |
| Lake (draft) | 69 | 2 | 83 | 0.028 | 1.000 | 0.962 | 1.000 |
| Loudoun | 247 | 13 | 139 | 0.050 | 0.963 | 1.000 | 1.000 |
| Douglas | 77 | 51 | 47 | **0.398** | 1.000 | **0.645** | 1.000 |

Douglas carries two thirds of the disputed cells. The known-answer misses below show at least one cause: a symbol read into the wrong column of Table 2.2. By district family, industrial districts have the highest disputed share (0.179) and the lowest unlisted recall (0.792). The full breakdown is in `reports/accuracy.json` under `by_family`.

## Known-answer cells

`tests/known_answers.json` was frozen before the first extraction call (Z0.5 report). 21 of its cells fall in the five extracted jurisdictions.

| Result | Count | Cells |
|---|---|---|
| Extractor matches the cited status | 15 | Loudoun IP and GI; Pittsylvania M-SVMS; Douglas LI, LI-R, HI, AG, R-A, R-LD, R-MD, R-HD, R-MH, PRD, C-G, PSP |
| Extractor misses, cell published | 4 | Loudoun MR-HI, Pittsylvania M-2, Douglas OI, Douglas C-H |
| Extractor misses, cell withheld | 1 | Warrenton I |
| Unscored | 1 | Lake LM: the extractor's cell was rejected at the gates |

Loudoun IP and GI match the cited status (conditional, by the 2025 amendment) and differ from the pre-amendment table in the cached source, which still shows P. That is expected; they are not extractor errors.

**Root cause of each miss** (all `datacenter`):

| Cell | Expected | Extractor | Published as | Cause |
|---|---|---|---|---|
| us-51107/MRHI | conditional | permitted | permitted, C (`single`) | The extractor applied the amendment for IP and GI from a prose source but took MR-HI from the pre-amendment table, though the same amendment sentence names all three districts. Codex agreed with the extractor; grok's label failed the gates. |
| us-51143/M-2 | conditional | unlisted | unlisted, C (`single`) | Sec. 35-403 lists "Data centers" as a special use in M-2. The absence gate checks each taxonomy term once, so one explained mention of "data center" (the Sec. 35-142 standards) cleared the term, and the Sec. 35-403 mention was never confronted. **Gate gap.** |
| us-13097/OI | conditional | prohibited | prohibited, C (`disputed`) | In the table text, the 518210 row has `S` in the OI column (10th of the header) and blanks in C-G, C-H and PSP. The extractor put the `S` under C-H. The table gate checks the row label, the column header and the symbol separately, and never checks that the symbol sits in that header's column. **Gate gap.** Codex, which had the page images, read it correctly. |
| us-13097/C-H | prohibited | conditional | conditional, C (`disputed`) | The same column offset as OI. |
| us-5183136/I | prohibited | unlisted | withheld | Both reviewer labels failed the gates. The taxonomy is ambiguous for a use the code defines (Article 12) but lists in no district: the known answer treats it as prohibited, and the extractor applied the `unlisted_not_prohibited` rule. |

These four published cells are wrong at grade C. They were not edited or withheld by hand. They block the tag until the gate gaps are fixed and the cells re-graded, or the maintainer decides otherwise.

## Mutation test

From the Z0.5 report, criterion fixed before the runs:

| Jurisdiction | Flipped cells | Moved the expected way | Noise (unflipped cells that changed) | Result |
|---|---|---|---|---|
| Douglas | 13 | 13 (1.00) | 2.6% | criterion met |
| Loudoun | 25 | 9 (0.36) | 0.3% | **criterion not met** |

For Loudoun, 10 of the 25 counted cells sit on unflipped rows of other tables. On the 15 cells whose column really was flipped, 9 moved the expected way (0.60). That figure comes from a hand analysis made after the run, not from the pre-set measure.

`reports/accuracy.json` also carries Lake's `mutation.json`. That run used the superseded Z0.4 text, before Z0.4b rebuilt the tables, and it did not meet its criterion. It was not re-run.

## Human audit

The 60-cell sample is drawn and frozen: `audit/z0_audit_sheet.v0.1.0.csv`, seed 20261011, sha256 `d752cfb3...a136`. It has 15 cells per status, spread across the five jurisdictions. The sheet carries no model answer, and `audit/README.md` tells the auditor to label from the source first.

- 24 of the 60 cells are model-gold, so the human-vs-model-gold agreement will rest on n = 24. The human-vs-extractor agreement uses all 60. At n = 60 the 95% interval is about +/-8 points.
- No auditor is named, and no labels exist yet. **The audit is owed.**

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

`python -m ozr release --version 0.1.0 --published 2026-10-11` wrote `releases/v0.1.0/` with `manifest.json` and nine files: `cells.json`, `cells.parquet`, `jurisdictions.json`, `sources.json`, `amendments.json`, `state_rules.json`, `taxonomy.json`, `accuracy.json` and `denylist.txt`.

- **Consumer contract:** `ozr.contract.check_release(manifest)` returns no errors.
- **Release gate:** fails with 137 errors. The full output is in `docs/test-results/z0.7_release.v0.1.0.md`.
  - **134 coverage errors**, one per missing district and class. These are the 45 cells rejected at extraction and the 89 withheld at grade. The gate was not loosened and no placeholder rows were added. There are two ways out, and the choice is the maintainer's:
    - (a) The coverage gate accepts a key listed in a release `withheld.json` with its reason.
    - (b) Withheld keys ship as explicit rows with a null value and confidence `unverified`, which the contract allows. This needs a schema change.
  - **3 statute-quote errors.** The eight statute sources were fetched for this release; five quotes match.
    - `ga-lp_gas` and `ga-utility_generation`: the enrolled-bill PDFs interleave line numbers ("61", "62", ...) with the text.
    - `va-cannabis_cultivation_processing`: the triage quote reads "§ 4.1-630 ," and the statute reads "§ 4.1-630,".
    - Fixing either means editing triage data or the canonicaliser, which is outside release preparation.
- **No district polygons.** Every zoning layer's `redistribute_geometry` is `unknown`, so no `districts.*.geoparquet` is written. The consumer has to resolve districts itself (spec 10, interface issue 1).
- **`amendments.json` is empty.** No jurisdiction has an amendment record. Lake's adopted 2026-09-08 data-center moratorium is therefore not recorded, and its cells are not marked stale by it. Lake's cells also come from an unadopted draft ordinance.
- **`schema_url`** points at `blob/v0.1.0/...`, a tag that does not exist yet. It resolves once the release is tagged.

## Still owed

1. **A decision on coverage versus withholding** (option a or b above), then a release that passes its own gate.
2. **The four wrong published cells.** Fix the two gate gaps (the column-position check for table evidence, and a per-occurrence absence gate), re-grade, and re-score the known answers. Decide the Warrenton taxonomy question.
3. **Lake.** Either record the moratorium and pending amendment as amendment records, or hold Lake out of v0.1.0 because its text is an unadopted draft.
4. **The three statute quotes.**
5. **The five analyst-fetch jurisdictions**, without which the Z0 exit (10 jurisdictions) and the listed-status minimum counts cannot be met.
6. **The human audit:** name an auditor, label the 60 cells blind, and record the minutes.
7. **Review and merge** of this branch, then the **tag** `v0.1.0` and a GitHub release carrying the data files, recorded as proof. None of these has been done.
