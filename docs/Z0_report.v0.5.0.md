# Z0 pilot report (v0.5.0)

**Date:** 2026-10-11 · **Covers:** the Z0 pilot through Z0.11:
- grading and measurement (Z0.6)
- release (Z0.7)
- gate fixes (Z0.8)
- Fauquier County and OCR (Z0.9)
- review fixes (Z0.10, two rounds)
- structural gate rules (Z0.11)

This version supersedes `docs/Z0_report.v0.4.0.md`, which is kept.

**Status: the release gate passes, but the release is not tag-ready.** The human audit is owed, only 6 of 10 jurisdictions are in, and the stack is not reviewed or merged.

## TL;DR

- **494 published, 577 withheld, out of 1,071 district-class keys in six jurisdictions.** Before Z0.11 the split was 518 and 553. `ozr release` exits 0, and the consumer contract `zoning-atlas.release/0.1` reports 0 errors over 494 records. Every withheld key is in `releases/v0.1.0/withheld.json` with the failed gate and the run id: 537 at extraction, 39 at review, 1 superseded.
- **Z0.11 replaced special-case heuristics with three structural rules:**
  - Prose evidence for a listed status must name a taxonomy term of the class.
  - Amendment records declare their resulting status, and only a declared result can supersede a cell.
  - The prose-grid check scans the whole ordinance.

  No published status changed. 24 cells were withheld, all by the first rule, and 9 lost a dissenting reviewer label. Of the 24, 7 are Pittsylvania `utility_generation` cells resting on a footnote that names no use, and 6 are Pittsylvania cells whose text says "power generation", a phrase the taxonomy lacks.
- **Listed-status agreement is still "insufficient data":** 0.978 over model-gold permitted 2, conditional 12 and prohibited 168, against a minimum of 50 per status. The rules that would add listed gold are deferred:
  - Loudoun subdistrict columns
  - Lake continuation pages
  - Loudoun GIS subareas
  - (smaller) the "power generation" taxonomy gap
- **The disputed share passes at 0.010, but read it with its counterweight.** Counted as defined (both reviewer labels passed and differ), it fell from 0.027 because the stricter gates reject dissenting labels. Counting a gate-rejected reviewer label as dissent gives 0.691, or 0.603 when only rejected labels that differ from the extractor count.
- **No known-answer cell is published with a wrong status.** The score is 15 match, 2 miss (both withheld) and 5 unscored. The known-answer check has not been blind since Z0.8, and the human audit on `audit/z0_audit_sheet.v0.5.0.csv` is owed.
- **The Z0 exit is not met.** 6 of 10 jurisdictions are in.

## What is measured

Everything below is **model-panel agreement**: how often the extractor agrees with a reference built from two other models, codex and grok, which labelled the same text blind. The reference set, model-gold, is the cells where codex and grok agree.

> What is measured is agreement between the extractor and a reference built from two other models that labelled the same text blind. It does not measure agreement with the law as a planner would read it: three models reading the same ambiguous table the same wrong way is invisible to this method.

> **Reliance notice.** This is a research dataset, not a legal determination. Before relying on any answer, at every grade, get a zoning verification letter or use determination from the planning department, or a land-use attorney or planner.

Both texts are carried verbatim in `reports/accuracy.json` and in the release manifest.

## Scope

| Jurisdiction | Districts | Universe | Published | Withheld at extraction | Withheld at review | Withheld as superseded |
|---|---|---|---|---|---|---|
| us-5183136 Town of Warrenton, VA | 12 | 84 | 43 (44) | 36 | 5 | 0 |
| us-51143 Pittsylvania County, VA | 14 | 98 | **33 (53)** | 56 | 9 | 0 |
| us-12069 Lake County, FL (unadopted draft) | 22 | 154 | 42 (42) | 112 | 0 | 0 |
| us-51107 Loudoun County, VA | 57 | 399 | 246 (247) | 142 | 10 | 1 |
| us-13097 Douglas County, GA | 25 | 175 | 105 (105) | 64 | 6 | 0 |
| us-51061 Fauquier County, VA | 23 | 161 | 25 (27) | 127 | 9 | 0 |
| **Total** | 153 | **1,071** | **494 (518)** | **537** | **39** | **1** |

Z0.10 values are in brackets. Published by status: prohibited 275, unlisted 170, conditional 38, permitted 11. Published by grade: B 275, C 219.

The other four (Hillsborough, Polk, Atlanta, Coweta) have no ordinance text the pipeline may fetch. See the analyst-fetch list.

## Gates

| Gate | Value | Threshold | Result |
|---|---|---|---|
| Listed status (permitted, conditional, prohibited) | 0.978 (model-gold: permitted 2, conditional 12, prohibited 168) | at least 0.90, with at least 50 model-gold cells per status | **insufficient data** |
| Unlisted recall | 0.985 (135 model-gold unlisted) | at least 0.85, with at least 50 gold-unlisted cells | **pass** |
| Unlisted precision | 1.000 | at least 0.85, with at least 50 extractor-unlisted gold cells | **pass** |
| Disputed share, all cells, as defined | 0.010 (11 / 1,071) | at most 0.15 | **pass** |
| Disputed share, gate-rejected reviewer labels counted as dissent | 0.691 (740 / 1,071) | (not a plan gate) | reported; would fail |
| The same, only rejected labels that differ from the extractor | 0.603 (646 / 1,071) | (not a plan gate) | reported; would fail |
| Kappa, codex and grok | 0.938 | (not a plan gate) | reported |
| Lower bound (every disputed cell counted as a miss) | 0.948 | (not a plan gate) | reported |
| Excluded from model-gold (disputed + reviewer missing) | 0.704 (754 / 1,071) | (not a plan gate) | reported; a high exclusion rate is itself a finding |
| Gate rejection rate: extractor, codex, grok | 0.501, 0.523, 0.629 | (not a plan gate) | reported |
| Known-answer cells | 15 match, 2 miss (both withheld), 5 unscored | any miss investigated before release | **no miss published** |
| Mutation test (pre-set criterion) | Douglas met; Loudoun not met | the pipeline changes with the text | **mixed**, unchanged since Z0.5 |
| Consumer contract `zoning-atlas.release/0.1` | 0 errors over 494 records (Python port and reference implementation) | 0 errors | **pass** |
| Release gate (`ozr release`) | 0 errors | 0 errors | **pass** |
| Z0 phase exit: 10 jurisdictions | 6 | 10 | **fail** |

### Disputed share, two ways

The plan gate counts a key as disputed only when both reviewer labels passed the gates and their statuses differ. Each time the gates get stricter, more dissenting labels are rejected and the share falls: 0.031 in Z0.10 round 1, 0.027 in round 2, 0.010 now. Z0.11's 97 newly rejected grok labels account for most of the last drop. So the number measures label survival as much as agreement.

`ozr measure` now also reports two variants, overall and by jurisdiction. Both count a key as dissent when a reviewer has no accepted label but has a gate-rejected one:
- the first counts any such label;
- the second counts only one whose status differs from the extractor's.

| Jurisdiction | As defined | Rejected label = dissent | Rejected and differing |
|---|---|---|---|
| Warrenton | 0.000 | 0.583 | 0.571 |
| Pittsylvania | 0.000 | 0.857 | 0.796 |
| Lake (draft) | 0.000 | 0.714 | 0.714 |
| Loudoun | 0.008 | 0.516 | 0.406 |
| Douglas | 0.011 | 0.749 | 0.669 |
| Fauquier | 0.037 | 0.994 | 0.814 |
| **All** | **0.010** | **0.691** | **0.603** |

Both variants exceed 0.15 everywhere. The reviewers are not disagreeing with the extractor. On most keys, at least one of them did not produce a label the gates accept. That is the same fact as the 0.704 exclusion rate, seen from the dispute side.

### Listed agreement: why it is still "insufficient data", and the levers

Model-gold has 2 permitted and 12 conditional cells; each status needs 50. No gate change can create gold. Gold needs keys where both reviewers produce labels that pass. The deferred rules that would add listed keys:

| Lever | What it needs | Keys it touches |
|---|---|---|
| **Loudoun subdistrict columns** (TC, TRC, PDRV) | A multi-column binding rule for tables whose columns are subdistricts | 14 |
| **Lake continuation pages** | A maintainer decision on table pages whose header does not repeat | 18 |
| **Loudoun GIS subareas** (TR1LF and four others) | A primary text that names the subareas | 24 |
| "Power generation" in `taxonomy/v1.json` | A taxonomy patch (Z0.11 finding) | 6 Pittsylvania `utility_generation` |

Even all of these together would not reach 50 permitted. The four analyst-fetch jurisdictions are the larger lever.

### What the gates check now

- **Table evidence.** Unchanged since Z0.10.
  - The quote must read `<row_label> | <column_header> | <symbol>`.
  - The symbol must map to the status through the quoted table key.
  - The column header must bind the district, by a quoted alias or by unambiguous formatting.
  - Every placement of the row and column in the reconstructed grids must hold the cited symbol.
- **Prose evidence** for permitted, conditional or prohibited (Z0.11, rule 1):
  - It must contain a taxonomy term of the cell's class on token boundaries, so a legend line, footnote, district lead-in or unlisted-use clause cannot carry a listed status.
  - It may not overlap a quoted table-key line.
  - In a prohibited-by-default jurisdiction it may not quote the unlisted-use clause.
- **Prose-grid placement** (Z0.11, rule 3): prose evidence is rejected when any source of the jurisdiction has a reconstructed table or OCR grid row that names a term of the cell's class under a header that binds the cell's district. Each source is scanned on its own, and a header binds only through its own source's text. A cell that quotes an adopted amendment with a matching declared result is exempt.
- **Absence evidence.** Unchanged:
  - Every occurrence of every class term must be explained within its own source.
  - Every declared non-geometry source must have cached text.
  - An unlisted cell is capped at C when the jurisdiction text has an OCR layer.
- **SUPERSEDED** (Z0.11, rule 2):
  - Only an adopted text amendment with a declared result for the cell's class and district can supersede it. It does so when it postdates the cited source, when the date is unknown, or when the cell contradicts the declared status.
  - The exemption needs the cell's status to equal the declared result. In addition, either the cell quotes the result's operative text from the result's source, or a reviewed `incorporated_in` quote holds. That quote must name a class term, say more than class terms, and not be a district code or table symbol.
  - A moratorium, a pending amendment, or any record without a declared result never supersedes (spec rule 5).
  - A record the gate cannot interpret still fails closed.
- **Amendment records.** They are schema-checked in the release. `results` is allowed only on adopted text amendments, and a blank reference is refused. Each result quote must be found in the amendment's source or an `incorporated_in` source, must name a class term, and must not contain the amendment's reference or id.
- **Grade.** Evidence matched only in OCR text caps a cell at C. A parcel-specific district caps it at C.

### By jurisdiction

| Jurisdiction | Model-gold | Disputed | Reviewer missing | Listed agreement | Unlisted recall | Unlisted precision | Disputed share |
|---|---|---|---|---|---|---|---|
| Warrenton | 35 | 0 | 49 | (no listed gold) | 1.000 | 1.000 | 0.000 |
| Pittsylvania | 14 | 0 | 84 | (no listed gold) | 1.000 | 1.000 | 0.000 |
| Lake (draft) | 44 | 0 | 110 | (no listed gold) | 0.955 | 1.000 | 0.000 |
| Loudoun | 179 | 3 | 217 | 0.971 | 1.000 | 1.000 | 0.008 |
| Douglas | 44 | 2 | 129 | 1.000 | (no unlisted gold) | (none) | 0.011 |
| Fauquier | 1 | 6 | 154 | 1.000 | (no unlisted gold) | (none) | 0.037 |

Pittsylvania lost its listed model-gold: its three `utility_generation` agreements quoted "power generation" or the footnote.

## Z0.11: what changed in the data

All 24 newly withheld cells, and the 9 that keep their status with one dissent fewer, are listed with the quote behind each in `docs/test-results/z0.11_structural_gates.v0.1.0.md`. In summary:

| Group | Cells | Disposition |
|---|---|---|
| Pittsylvania `utility_generation` resting on the footnote "d. Requires a Special Use Permit unless otherwise permitted by right." (A-1, B-1, B-2, C-1 and M-1 from the extractor; M-2 and M-SVMS from grok) | 7 | Withheld. The footnote does not name the use; the rule works as intended |
| Pittsylvania `utility_generation` quoting "Public utilities (... power generation ...)" or "Power generation" (MHP, R-1, RC-1, RE, RMF, RPD) | 6 | Withheld. A taxonomy gap; RC-1 and RE were grade B. Deferred to a maintainer decision |
| Pittsylvania: extractor quotes outside the taxonomy ("Chemicals manufacturing", "Petroleum ... refining") or naming another class ("Power stations" for battery storage) | 3 | Withheld |
| Warrenton I `lp_gas` ("Fuel, coal, oil distribution storage yards") | 1 | Withheld; the text does not name LP gas |
| Keys whose only passing reviewer label quoted a generic clause ("No structure shall hereafter be erected ...", the Fauquier intent clause, a district list heading): Fauquier M-G and M-R datacenter, Loudoun C1 `utility_generation`, and Pittsylvania M-1, M-2 and M-SVMS warehouse and M-SVMS `lp_gas` | 7 | Withheld at review |
| Pittsylvania and Fauquier `lp_gas` unlisted cells that lose a grok `prohibited` label quoting a generic clause | 9 | Still published, `unlisted`, disputed to single, grade C unchanged |

Rule 2 and rule 3 moved no cell:
- Loudoun IP and GI datacenter stay published as `conditional` through ZOAM-2024-0001's declared result.
- Loudoun MR-HI stays withheld as superseded.
- The four Fauquier battery-storage cells stay published through the reviewed incorporation record and the declared result.

Warrenton and Douglas have no amendment records to migrate. The only records are Loudoun's and Fauquier's.

## Known-answer cells

`tests/known_answers.json` was frozen before the first extraction call and has never been edited. 22 of its cells fall in the six extracted jurisdictions.

> **This is not a blind check, and has not been since Z0.8.**
> - The table-grid and per-occurrence absence gates were designed against Pittsylvania M-2 and Douglas OI and C-H.
> - The SUPERSEDED gate was added to resolve Loudoun MR-HI.
> - Z0.11's declared result for ZOAM-2024-0001 reads the same county sentence that the known answers cite.
>
> The 60-cell human audit is the only blind check.

| Result | Z0.9 | Z0.10 | Z0.11 |
|---|---|---|---|
| Extractor matches the expected status | 15 | 15 | 15 |
| Miss, cell published | 1 (Loudoun MR-HI) | 0 | 0 |
| Miss, cell withheld | 1 (Warrenton I) | 2 (Warrenton I; Loudoun MR-HI, superseded) | 2 (unchanged) |
| Unscored (no extractor cell passed) | 5 | 5 | 5: Lake LM, Pittsylvania M-2, Douglas OI, Douglas C-H, Fauquier BP |

## Mutation test

The criterion was fixed before the runs. There has been no new run since Z0.5:

| Jurisdiction | Flipped cells | Moved the expected way | Noise | Result |
|---|---|---|---|---|
| Douglas | 13 | 13 (1.00) | 2.6% | criterion met |
| Loudoun | 25 | 9 (0.36) | 0.3% | **criterion not met** |

## Human audit

The published set changed again: 10 of the 60 rows of `audit/z0_audit_sheet.v0.4.0.csv` are now withheld. `audit/z0_audit_sheet.v0.5.0.csv` was drawn with the same sampler and seed (20261011; sha256 `edcbe668...cec7`), and 48 of its 60 rows are also in v0.4.0. Versions v0.1.0 to v0.4.0 are kept unchanged.

**No auditor is named and no labels exist. The audit is owed.**

## Cost and time

There were no model calls in Z0.8, Z0.10 or Z0.11. The per-jurisdiction extraction and review costs in v0.4.0 stand: median $7.39 priced, range $3.30 to $28.28. The Z0.11 re-gate took about 11 minutes, 8.5 of them for Douglas.

## Swaps

| Out | In | Reason |
|---|---|---|
| City of Port St. Lucie, FL | Lake County, FL | No primary copy of the code |
| Prince William County, VA | Fauquier County, VA | No adopted ordinance on the county's own domain |
| (Coweta County, GA stays) | | The swap rule was triggered, but the only GA alternate fails the same test |

## Analyst-fetch list

| Jurisdiction | What is needed | Why |
|---|---|---|
| us-12057 Hillsborough County, FL | The Land Development Code use table and unlisted-use clause | Its own site carries only replacement pages with no use table |
| us-12105 Polk County, FL | The Land Development Code | Copies are by public records request |
| us-1304000 City of Atlanta, GA | The zoning ordinance, including the 2024 data-center ordinances | The city site refuses automated fetches |
| us-13077 Coweta County, GA | The zoning ordinance | Reachable only through a third-party publisher |

## Release

`python -m ozr release --version 0.1.0 --published 2026-10-11` writes `releases/v0.1.0/` and exits 0. The hashes are in `docs/test-results/z0.11_structural_gates.v0.1.0.md`.

- **Amendment records:**
  - **Loudoun ZOAM-2024-0001**, adopted. It declares `conditional` for datacenter in IP, GI and MR-HI.
  - **Fauquier's 2025-04-10 energy storage amendment**, adopted. It declares `conditional` for battery storage in RA, BP, I-1 and I-2, quoted from the codified Article 3 row.
  - **Lake** records neither its adopted 2026-09-08 data-center moratorium nor its pending amendment. Under spec rule 5, neither would change a cell. Recording them would mark the affected cells stale.
- **No district polygons.** Every zoning layer's `redistribute_geometry` is `unknown`.
- **`schema_url`** points at `blob/v0.1.0/...`, a tag that does not exist yet.

## Still owed

1. **The human audit** on `audit/z0_audit_sheet.v0.5.0.csv`: name an auditor, label the 60 cells blind, and record the minutes.
2. **Withheld cells that a rule, a source or a taxonomy decision could restore:**
   - Loudoun subdistrict columns (14 cells), Loudoun GIS subareas (24 cells) and Lake continuation pages (18 cells), as above.
   - "Power generation" and the near-miss forms "Chemicals manufacturing" and "refining" (Z0.11): a taxonomy patch.
   - Fauquier's scanned table rows need better OCR or a recorded human transcription.
   - Fauquier's footnoted (`P25`) and combined (`SP/SE`) symbols need key entries.
   - The `unlisted` cells withheld since Z0.8 need a prompt that lists every term occurrence.
   - Prose-grid placement semantics (review residuals x5 and g4) and the class-term row match. The match is too broad: "Electrical substation distribution centers" counts as a warehouse row. It is also too narrow: a "Warehousing ..." row names no taxonomy term, so it is never checked against prose that does name one. The broad side fails closed; the narrow side is a residual gap.
3. **Lake.** Record its moratorium and pending amendment, or hold Lake out of v0.1.0 because its text is an unadopted draft.
4. **Other open items:**
   - The Warrenton taxonomy question: a use the code defines but lists in no district.
   - The `lp_gas` reviewer disagreement in Fauquier.
   - A `taxonomy/v1.json` patch for the text that says only reviewers check symbols.
5. **The four analyst-fetch jurisdictions.** Without them, the Z0 exit (10 jurisdictions) and the listed-status minimum counts cannot be met.
6. **Review and merge of the stack (#1 to #12).** After that come the tag `v0.1.0` and a GitHub release carrying the data files, recorded as proof. None of these has been done.
