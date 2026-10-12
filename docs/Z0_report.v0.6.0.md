# Z0 pilot report (v0.6.0)

**Date:** 2026-10-12 · **Covers:** the Z0 pilot through Z0.12, the approved swaps. This version supersedes `docs/Z0_report.v0.5.0.md`, which is kept. Detail and evidence: `docs/test-results/z0.12_swaps.v0.1.0.md`.

**Status: 10 jurisdictions are registered and the release gate passes, but Z0 is not complete.**
- Two of the four new jurisdictions are not fully reviewed: codex hit its usage limit (reset 2026-10-17 20:57), and grok failed intermittently on Palm Beach's very long prompt.
- The human audit is owed.
- The stack is not reviewed or merged.

## TL;DR

- **704 published, 1,375 withheld, over 2,079 district-class keys in 10 jurisdictions.** Z0.11 had 494 and 577 over 1,071 keys in 6.
  - `ozr release` exits 0. The consumer contract `zoning-atlas.release/0.1` reports 0 errors over 704 records, in both the Python port and the reference implementation.
  - The withheld keys: 1,280 at extraction, 94 at review, 1 superseded.
  - **Palm Beach publishes nothing.** All 280 of its cells are withheld.
- **Swaps applied** (maintainer approval 2026-10-11): Polk to Palm Beach FL, Hillsborough to Santa Rosa FL, Atlanta to Hall GA, Coweta to Cherokee GA. The four retired picks are kept only where frozen known answers cite them. Lake stays, and every Lake cell is labelled `unadopted_draft` and capped at C.
- **Gates over the 8 jurisdictions where both reviewers ran:**
  - Listed agreement 0.978: **insufficient data** (gold permitted 3, conditional 12, prohibited 168).
  - Unlisted recall 0.939 and precision 1.000: pass.
  - Disputed share 0.015: pass. Counting gate-rejected labels as dissent gives 0.709, or 0.630 when only labels that differ count. Both would fail.
- **No known-answer miss is published.** The score is 15 match, 2 miss (both withheld) and 5 unscored, unchanged from Z0.11. It has not been blind since Z0.8. The new jurisdictions have no known answers, and the retired ones' 4 are out of scope.
- **$72.20 priced for the four new jurisdictions**, plus 6.1 M unpriced codex tokens, over 11.2 h of model time. That includes $11.15 of discarded or failed runs.
- **Z0 exit: not met.** The 10 jurisdictions are registered, but 2 are not fully reviewed. The listed-status minimum counts are not met. The human audit is owed.

## Published and withheld

| Jurisdiction | Districts | Universe | Published | Withheld at extraction | at review | superseded | Reviewers |
|---|---|---|---|---|---|---|---|
| us-5183136 Town of Warrenton, VA | 12 | 84 | 43 | 36 | 5 | 0 | codex, grok |
| us-51143 Pittsylvania County, VA | 14 | 98 | 33 | 56 | 9 | 0 | codex, grok |
| us-12069 Lake County, FL (unadopted draft) | 22 | 154 | 42 (all C) | 112 | 0 | 0 | codex, grok |
| us-51107 Loudoun County, VA | 57 | 399 | 246 | 142 | 10 | 1 | codex, grok |
| us-13097 Douglas County, GA | 25 | 175 | 105 | 64 | 6 | 0 | codex, grok |
| us-51061 Fauquier County, VA | 23 | 161 | 25 | 127 | 9 | 0 | codex, grok |
| **us-13139 Hall County, GA (new)** | 19 | 133 | **47** | 85 | 1 | 0 | codex, grok |
| **us-13057 Cherokee County, GA (new)** | 22 | 154 | **42** | 112 | 0 | 0 | codex, grok |
| **us-12113 Santa Rosa County, FL (new)** | 63 | 441 | **121** (all C, single or disputed) | 289 | 31 | 0 | grok only |
| **us-12099 Palm Beach County, FL (new)** | 40 | 280 | **0** | 257 | 23 | 0 | none |
| **Total** | 297 | **2,079** | **704** | **1,280** | **94** | **1** | |

- Published by status: prohibited 376, unlisted 260, conditional 41, permitted 27.
- Published by grade: B 278, C 426.
- The six Z0.11 jurisdictions are unchanged except Lake, where 37 cells went from B to C and all 42 gained `code_status`.

New data-center answers worth reading:
- **Hall:** I-1 and I-2 are `conditional` (special use, Sec. 7.6.2), and the other mapped districts are `prohibited`.
- **Cherokee:** LI and OI are `permitted` ("Data Processing, Hosting, and Related Services", `O`), both disputed and graded C.
- **Santa Rosa** maps "Technology Business" to datacenter inconsistently, so both `prohibited` and `unlisted` appear.

## Gates

| Gate | 8 jurisdictions, both reviewers | 10 jurisdictions (`accuracy.json`) | Threshold | Result |
|---|---|---|---|---|
| Listed status agreement | 0.978 (gold: permitted 3, conditional 12, prohibited 168) | same | at least 0.90, with at least 50 gold per status | **insufficient data** |
| Unlisted recall | 0.939 (198 gold unlisted) | same | at least 0.85, with at least 50 gold | pass |
| Unlisted precision | 1.000 | same | at least 0.85 | pass |
| Disputed share, as defined | 0.015 (21 / 1,358) | 0.010 (21 / 2,079) | at most 0.15 | pass |
| Disputed share, gate-rejected label = dissent | 0.709 | 0.560 | (not a plan gate) | reported; would fail |
| The same, rejected and differing | 0.630 | 0.494 | (not a plan gate) | reported; would fail |
| Kappa, codex and grok | 0.905 | same | (not a plan gate) | reported |
| Lower bound | 0.908 | same | (not a plan gate) | reported |
| Known-answer cells | 15 match, 2 miss (withheld), 5 unscored | same | no miss published | pass |
| Mutation test | Douglas met, Loudoun not met (Z0.5) | same | | mixed |
| Consumer contract | 0 errors / 704 | | 0 errors | pass |
| Release gate (`ozr release`) | exit 0 | | 0 errors | pass |
| Z0 exit: 10 jurisdictions | 10 registered; 8 fully reviewed | | 10 | **not met** |

- **Why two columns.** The 10-jurisdiction disputed shares look better only because Santa Rosa and Palm Beach keys have no codex label, so they can be neither disputed nor dissenting. Read the 8-jurisdiction column.
- **The gold minimums are still far off.** Hall and Cherokee add 64 gold cells, but only 3 permitted and 12 conditional exist in total. The levers from v0.5.0 still stand, and two new ones follow:
  - Cherokee's `Res` column and blanks;
  - the codex reviews owed for Santa Rosa and Palm Beach.

## Known answers

`tests/known_answers.json` was frozen before the first extraction and has never been edited.

- **In scope:** 22 cells in the six original jurisdictions. 15 match, 2 miss (Loudoun MR-HI and Warrenton I, both withheld) and 5 are unscored.
- **Out of scope:** Hillsborough M, Atlanta BeltLine and I-MIX, and the Coweta moratorium amendment. Their jurisdictions are retired.
- **The new jurisdictions:** none has a known answer.

> **This score is not blind.** The gates that decide it were designed or tightened against the same known answers (Z0.8, Z0.10, Z0.11). The 60-cell human audit is the only blind check.

## Cost per jurisdiction (Z0.12)

| Jurisdiction | Priced USD | Unpriced codex tokens | Model wall time | Notes |
|---|---|---|---|---|
| Hall | 11.69 | 707,210 | 1.44 h | $3.60 of it is a discarded first extraction over interleaved two-column text |
| Cherokee | 11.66 | 968,366 | 2.22 h | clean |
| Santa Rosa | 27.31 | 4,425,516 | 5.29 h | all codex tokens are from 3 failed reviews |
| Palm Beach | 21.54 | 0 | 2.23 h | $7.55 is 2 failed grok reviews |

For the six earlier jurisdictions, see v0.4.0 (median $7.39 priced, range $3.30 to $28.28). Z0.12 jurisdictions are larger, and the clean-pass cost per new jurisdiction ran $8.09 to $27.31.

## Human audit

`audit/z0_audit_sheet.v0.6.0.csv` was drawn with the same sampler and seed (20261011, sha256 `bbe51b7f...50c5`). 37 of its 60 rows are also in v0.5.0. **No auditor is named and no labels exist.** The sheet includes Santa Rosa rows that have one reviewer only. Hall rows carry reversed column headers in their quotes (for example `All data center | 1-I | SU`), because the PDF text layer reads the rotated header that way.

## Still owed

1. **Codex reviews for Santa Rosa and Palm Beach** after 2026-10-17 20:57, then grade, measure, release, a v0.7.0 audit sheet and both contract checks (commands in the evidence doc). Codex also emitted malformed JSON (a stray `}`) on Santa Rosa before the quota ran out, so a rerun may need a smaller chunk or a retry policy.
2. **A grok review for Palm Beach.** grok failed on one of 8 chunks in each of two runs, saying it could not see the middle of the prompt. A rerun may pass; a smaller segment set is the more reliable fix.
3. **Palm Beach gate fit:** hierarchical section labels such as "Art. 4.B.5.C.2", letter-spaced matrix headers, and duplicated `I L` columns.
4. **The human audit** on v0.6.0, or v0.7.0 once the owed reviews land.
5. **Withheld-cell rule decisions:**
   - From v0.5.0: Loudoun subdistrict columns and GIS subareas, Lake continuation pages, "power generation" and the other taxonomy near-misses, Fauquier OCR and footnoted symbols, and an unlisted prompt that lists every term occurrence.
   - New:
     - Cherokee's blank cells, unkeyed because the rule is in a separate PDF, and its `Res` column;
     - Santa Rosa `A` and symbols that carry a section reference ("C 5. 07");
     - Palm Beach `D` mapped to conditional (confirm);
     - the 40-image cap.
6. **Amendment records:** none was written for the four new counties (see the swap log). The Cherokee moratorium is in force but not recorded, so its cells are not marked stale.
7. **Merge the stack (#1 to #13), then:**
   - **The fingerprint key.** `ozr.fingerprints` reports "none configured".
   - **The tag `v0.1.0`** and a GitHub release carrying the data files, recorded as proof. None of these has been done.
