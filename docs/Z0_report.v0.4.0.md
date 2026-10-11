# Z0 pilot report (v0.4.0)

**Date:** 2026-10-11 · **Covers:** the Z0 pilot through Z0.10: grading and measurement (Z0.6), release (Z0.7), gate fixes (Z0.8), Fauquier County and OCR (Z0.9), and the review fixes (Z0.10, two rounds). This version supersedes `docs/Z0_report.v0.3.0.md`, which is kept. **Status: the release gate passes, but the release is not tag-ready.** The human audit is owed, only 6 of 10 jurisdictions are in, and the stack is not reviewed or merged.

## TL;DR

- **Six jurisdictions, 1,071 district-class keys, 518 published.** `ozr release` exits 0, and the consumer contract `zoning-atlas.release/0.1` reports 0 errors over 518 records. Every unpublished key is listed in `releases/v0.1.0/withheld.json` with the gate that failed and the run id.
- **Z0.10 addressed 16 review findings in round 1 and added a SUPERSEDED gate.** A second cross-model review found 6 of those fixes incomplete (the legend rule, the OCR cap, blank grid rows, column binding, the SUPERSEDED exemption and absence sections) plus 4 smaller gaps; round 2 completed them. Published cells fell from 595 to 518 in round 1, round 2 changed no published count or status, and no model was re-run.
  - Legend lines cited as prose: 18 cells.
  - Loudoun columns with no quoted binding to the district: 38 cells.
  - Lake rows on continuation pages that have no header: 18 cells.
  - Loudoun MR-HI, which ZOAM-2024-0001 supersedes: 1 cell.
  - Lost reviewer labels: 2 cells.
  - Round 2 moved 2 published Douglas cells from grade B to C: a grok prose label that agreed with them is now rejected, because Table 2.2 places a matching row under their column.
- **No known-answer cell is now published with a wrong status.** Loudoun MR-HI is withheld by the SUPERSEDED gate. On the extractor's status the score is still 15 match, 2 miss and 5 unscored.
- **The known-answer check is no longer blind** (see below). The human audit on `audit/z0_audit_sheet.v0.4.0.csv` is the only blind check left, and it has not been done.
- **The Z0 exit is not met.** 6 of 10 jurisdictions are in, and listed-status agreement has too few permitted and conditional model-gold cells to judge.

## What is measured

Everything below is **model-panel agreement**: how often the extractor agrees with a reference built from two other models, codex and grok, which labelled the same text blind. The reference set, model-gold, is the cells where codex and grok agree.

> What is measured is agreement between the extractor and a reference built from two other models that labelled the same text blind. It does not measure agreement with the law as a planner would read it: three models reading the same ambiguous table the same wrong way is invisible to this method.

> **Reliance notice.** This is a research dataset, not a legal determination. Before relying on any answer, at every grade, get a zoning verification letter or use determination from the planning department, or a land-use attorney or planner.

Both texts are carried verbatim in `reports/accuracy.json` and in the release manifest.

## Scope

| Jurisdiction | Districts | Universe | Published | Withheld at extraction | Withheld at review | Withheld as superseded |
|---|---|---|---|---|---|---|
| us-5183136 Town of Warrenton, VA | 12 | 84 | 44 | 35 | 5 | 0 |
| us-51143 Pittsylvania County, VA | 14 | 98 | 53 | 41 | 4 | 0 |
| us-12069 Lake County, FL (unadopted draft) | 22 | 154 | 42 | 112 | 0 | 0 |
| us-51107 Loudoun County, VA | 57 | 399 | 247 | 142 | 9 | 1 |
| us-13097 Douglas County, GA | 25 | 175 | 105 | 64 | 6 | 0 |
| us-51061 Fauquier County, VA | 23 | 161 | 27 | 125 | 9 | 0 |
| **Total** | 153 | **1,071** | **518** | **519** | **33** | **1** |

Published by status: prohibited 275, unlisted 173, conditional 53, permitted 17. Published by grade: B 277, C 241.

The other four (Hillsborough, Polk, Atlanta, Coweta) have no ordinance text the pipeline may fetch. See the analyst-fetch list.

## Gates

| Gate | Value | Threshold | Result |
|---|---|---|---|
| Listed status (permitted, conditional, prohibited) | 0.973 (model-gold: permitted 2, conditional 15, prohibited 171) | at least 0.90, with at least 50 model-gold cells per status | **insufficient data** |
| Unlisted recall | 0.985 (135 model-gold unlisted) | at least 0.85, with at least 50 gold-unlisted cells | **pass** |
| Unlisted precision | 1.000 | at least 0.85, with at least 50 extractor-unlisted gold cells | **pass** |
| Disputed share, all cells | 0.027 (29 / 1,071) | at most 0.15 | **pass** |
| Kappa, codex and grok | 0.851 | (not a plan gate) | reported |
| Lower bound (every disputed cell counted as a miss) | 0.897 | (not a plan gate) | reported |
| Excluded from model-gold (disputed + reviewer missing) | 0.700 (750 / 1,071) | (not a plan gate) | reported; a high exclusion rate is itself a finding |
| Gate rejection rate: extractor, codex, grok | 0.486, 0.518, 0.536 | (not a plan gate) | reported |
| Known-answer cells | 15 match, 2 miss (both withheld), 5 unscored | any miss investigated before release | **no miss published** |
| Mutation test (pre-set criterion) | Douglas met; Loudoun not met | the pipeline changes with the text | **mixed**, unchanged since Z0.5 |
| Consumer contract `zoning-atlas.release/0.1` | 0 errors over 518 records (Python port and reference implementation) | 0 errors | **pass** |
| Release gate (`ozr release`) | 0 errors | 0 errors | **pass** |
| Z0 phase exit: 10 jurisdictions | 6 | 10 | **fail** |

In Z0.10 the unlisted recall and precision gates got their own sufficiency counts. Before, one count gated both.

The disputed share fell from 0.031 to 0.027 in round 2 for a reason that is not good news: 4 Douglas grok labels that disagreed with the extractor cited prose (the unlisted-use sentence, or a chemical manufacturing clause) for rows Table 2.2 places, so the new prose-grid rule rejects them, and a rejected label no longer counts as a dispute.

### What the gates check now

- **Table evidence.**
  - The quote must read `<row_label> | <column_header> | <symbol>`. The labels and the section must occur on token boundaries.
  - The symbol must map to the status through the jurisdiction's quoted table key. The taxonomy's local forms count only when the jurisdiction quotes no key.
  - The column header must be the column for the cell's district. It binds by a quoted `column_aliases` entry, or by formatting or a spaced footnote list when exactly one of the jurisdiction's districts reads that way. A header that reads as two districts (`R-1 6` as R16, or as R-1 with footnote 6) fails closed.
  - Every placement of the row and column in the reconstructed table and OCR grids must hold the cited symbol, blanks included. A row binds only to a header on its own page. Only a heading row is skipped: one whose cells before the label are empty and whose values are all blank.
- **Prose and absence evidence** may not overlap any occurrence of a quoted table-key line.
- **Prose evidence** is rejected when the reconstructed table or OCR grid has a row naming a term of the cell's class under a column that binds the cell's district; such a cell must cite the table. In a prohibited-by-default jurisdiction, prose that quotes the unlisted-use clause cannot support a permitted, conditional or prohibited status.
- **Absence evidence.**
  - Every occurrence of every class term in the jurisdiction's text must lie inside an explanation quote whose section is found in the same source as that occurrence.
  - Every declared non-geometry source must have cached text.
  - No term or quote may span two sources.
  - An unlisted cell is capped at grade C when the jurisdiction text has an OCR layer.
- **SUPERSEDED.** A cell fails when an adopted amendment record dated after the cited source touches its class and district. It is exempt only when it cites the amendment's own source and its quote carries the amendment's quote or reference, or when the record has a reviewed `incorporated_in` entry (quote, section and reason, all found in the cited source) whose quote the cell's own quote contains. An unknown date fails closed, and so does an amendment record with an unknown kind or status, or a district that is not one of the jurisdiction's codes.
- **Amendment records** are schema-checked in the release. Their classes and districts must exist, and their source must be registered in `sources.json` with the same URL.
- **Grade.** Evidence matched only in OCR text caps a cell at C. A parcel-specific district caps it at C.

### By jurisdiction

| Jurisdiction | Model-gold | Disputed | Reviewer missing | Listed agreement | Unlisted recall | Unlisted precision | Disputed share |
|---|---|---|---|---|---|---|---|
| Warrenton | 35 | 1 | 48 | (no listed gold) | 1.000 | 1.000 | 0.012 |
| Pittsylvania | 17 | 9 | 72 | 1.000 | 1.000 | 1.000 | 0.092 |
| Lake (draft) | 44 | 0 | 110 | (no listed gold) | 0.955 | 1.000 | 0.000 |
| Loudoun | 179 | 3 | 217 | 0.971 | 1.000 | 1.000 | 0.008 |
| Douglas | 44 | 2 | 129 | 1.000 | (no unlisted gold) | (none) | 0.011 |
| Fauquier | 2 | 14 | 145 | 0.500 | (no unlisted gold) | (none) | 0.087 |

## Known-answer cells

`tests/known_answers.json` was frozen before the first extraction call and has never been edited. 22 of its cells fall in the six extracted jurisdictions.

> **This is not a blind check, and has not been since Z0.8.**
> - The table-grid and per-occurrence absence gates were designed against Pittsylvania M-2 and Douglas OI and C-H.
> - The SUPERSEDED gate was added to resolve Loudoun MR-HI.
> - Z0.10 kept the Douglas Table 2.2 positive control passing when it changed how blank grid cells count.
>
> So the score shows that the gates handle the cells they were built around. It says nothing about how often the pipeline is right elsewhere. The 60-cell human audit is the only blind check.

| Result | Z0.8 | Z0.9 | Z0.10 |
|---|---|---|---|
| Extractor matches the expected status | 15 | 15 | 15 |
| Miss, cell published | 1 (Loudoun MR-HI) | 1 (Loudoun MR-HI) | **0** |
| Miss, cell withheld | 1 (Warrenton I) | 1 (Warrenton I) | 2 (Warrenton I; Loudoun MR-HI, superseded) |
| Unscored (no extractor cell passed) | 4 | 5 (+ Fauquier BP) | 5: Lake LM, Pittsylvania M-2, Douglas OI, Douglas C-H, Fauquier BP |

Scoring is on the extractor's status, so a withheld miss still counts as a miss. The MR-HI withholding reason names the gate and the amendment:

```text
superseded: us-51107/MRHI/datacenter: adopted amendment us-51107-zoam-2024-0001 (ZOAM-2024-0001) (effective 2025-03-18) postdates cited source us-51107-zo-ch3 (2023-11-21) and touches datacenter in MRHI; the cell's evidence does not cite it
```

Loudoun IP and GI cite the amendment's own county page and stay published as `conditional`, which matches the expected answer.

## Mutation test

The criterion was fixed before the runs. There has been no new run since Z0.5:

| Jurisdiction | Flipped cells | Moved the expected way | Noise | Result |
|---|---|---|---|---|
| Douglas | 13 | 13 (1.00) | 2.6% | criterion met |
| Loudoun | 25 | 9 (0.36) | 0.3% | **criterion not met** |

Lake's run used superseded Z0.4 text and was not re-run. Fauquier has no mutation run.

## Human audit

The published set and its strata changed again: us-12069 no longer has a published `permitted` cell. `audit/z0_audit_sheet.v0.4.0.csv` was drawn with the same sampler and seed 20261011 (sha256 `270d2a03...3983`), with 15 cells per status spread across the six jurisdictions. 45 of its 60 rows are also in v0.3.0. Versions v0.1.0 to v0.3.0 are kept unchanged.

**No auditor is named and no labels exist. The audit is owed.**

## Cost and time

These figures cover one clean pass for each jurisdiction (extraction, codex review and grok review), read from `runs/<id>.jsonl`. Codex calls are unpriced, so codex is given in tokens. The Z0.8 and Z0.10 fixes made no model calls.

| Jurisdiction | Claude extract (USD) | Grok review (USD) | Priced total (USD) | Codex tokens | Model hours |
|---|---|---|---|---|---|
| Warrenton | 2.08 | 1.99 | 4.07 | 574,969 | 0.61 |
| Pittsylvania | 2.48 | 3.15 | 5.63 | 473,541 | 1.10 |
| Lake (draft) | 2.37 | 0.94 | 3.30 | 468,345 | 1.51 |
| Loudoun | 11.32 | 16.97 | 28.28 | 3,192,672 | 4.41 |
| Douglas | 9.53 | 6.98 | 16.52 | 2,389,983 | 2.56 |
| Fauquier | 4.40 | 4.73 | 9.14 | 936,291 | 1.76 |
| **Median (range)** | | | **7.39 (3.30 to 28.28)** | | **1.64 (0.61 to 4.41)** |

The total spent on the first five, including superseded and mutation runs, was $159.25 priced (see v0.2.0). Human minutes were not recorded.

## Swaps

| Out | In | Reason |
|---|---|---|
| City of Port St. Lucie, FL | Lake County, FL | No primary copy of the code |
| Prince William County, VA | Fauquier County, VA | No adopted ordinance on the county's own domain. Fauquier is now in, from ten PDFs fetched by hand from the county site |
| (Coweta County, GA stays) | | The swap rule was triggered, but the only GA alternate fails the same test |

## Analyst-fetch list

| Jurisdiction | What is needed | Why |
|---|---|---|
| us-12057 Hillsborough County, FL | The Land Development Code use table and unlisted-use clause | Its own site carries only replacement pages with no use table |
| us-12105 Polk County, FL | The Land Development Code | Copies are by public records request |
| us-1304000 City of Atlanta, GA | The zoning ordinance, including the 2024 data-center ordinances | The city site refuses automated fetches |
| us-13077 Coweta County, GA | The zoning ordinance | Reachable only through a third-party publisher |

## Release

`python -m ozr release --version 0.1.0 --published 2026-10-11` writes `releases/v0.1.0/` and exits 0. The hashes are in `docs/test-results/z0.10_review_fixes.v0.2.0.md`.

- **Amendment records:**
  - **Loudoun ZOAM-2024-0001**, adopted. It feeds the SUPERSEDED gate.
  - **Fauquier's 2025-04-10 energy storage amendment**, adopted. Its `incorporated_in` entry quotes the amended Article 3 row with section 3-320 and a reason, and the four published RA, BP, I-1 and I-2 cells quote that row.
  - **Lake** has neither its adopted 2026-09-08 data-center moratorium nor its pending amendment recorded, and Lake's cells come from an unadopted draft.
- **No district polygons.** Every zoning layer's `redistribute_geometry` is `unknown`.
- **`schema_url`** points at `blob/v0.1.0/...`, a tag that does not exist yet.

## Still owed

1. **The human audit** on `audit/z0_audit_sheet.v0.4.0.csv`: name an auditor, label the 60 cells blind, and record the minutes.
2. **Withheld cells a rule or a source could restore:**
   - Loudoun subdistrict columns (TC, TRC and PDRV, 14 cells) need a multi-column rule.
   - Loudoun GIS subarea codes (TR1LF and four others, 24 cells) need a primary text that names the subareas.
   - Lake continuation pages (18 cells) need a maintainer decision on headers that do not repeat.
   - Fauquier's scanned table rows need better OCR or a recorded human transcription.
   - Fauquier's footnoted (`P25`) and combined (`SP/SE`) symbols need key entries.
   - The 205 `unlisted` cells withheld since Z0.8 need a prompt that lists every term occurrence.
   - The prose-grid rule matches class terms in row labels, so a row such as "Warehouse clubs, supercenters" also forces table evidence for `warehouse_distribution`. It fails closed; a narrower row match is a maintainer decision.
3. **Lake.** Either record its moratorium and pending amendment, or hold Lake out of v0.1.0 because its text is an unadopted draft.
4. **Other open items:**
   - The Warrenton taxonomy question: a use the code defines but lists in no district.
   - The `lp_gas` reviewer disagreement in Fauquier.
   - A `taxonomy/v1.json` patch for the text that says only reviewers check symbols.
5. **The four analyst-fetch jurisdictions.** Without them, the Z0 exit (10 jurisdictions) and the listed-status minimum counts cannot be met.
6. **Review and merge of the stack (#1 to #11).** After that come the tag `v0.1.0` and a GitHub release carrying the data files, recorded as proof. None of these has been done.
