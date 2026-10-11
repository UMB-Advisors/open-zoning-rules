# Z0 human audit

`z0_audit_sheet.v0.1.0.csv` holds 60 published cells for a blind human check. They were drawn by `python -m ozr audit` with seed `20261011` (`pipeline/ozr/audit.py`): 15 cells per status, spread round-robin across the five extracted jurisdictions. The sheet is frozen. Do not redraw it or edit any column except `human_status` and `human_notes`.

The Z0.8 gate fixes withheld 17 of the v0.1.0 cells, so `z0_audit_sheet.v0.2.0.csv` was drawn from the new published set with the same sampler and seed.

**Use `z0_audit_sheet.v0.3.0.csv`.** Z0.9 added a sixth jurisdiction, us-51061 (Fauquier County), which changes the strata (status by jurisdiction), so v0.3.0 was drawn from the six jurisdictions' published cells with the same sampler and seed. 49 of its 60 rows are also in v0.2.0 and 11 are Fauquier rows. All three files are frozen; label only v0.3.0.

## Label from the source first

**Before you look at anything else, label every row from the source document.** Do not open `cells.json`, `cells.extracted.json`, `cells.review.*.json`, the release, `reports/accuracy.json`, the reports in `docs/`, or the pull requests until all 60 rows are labelled. The audit measures how often the models agree with a person reading the law, and it only works if that person has not seen their answers.

For each row:

1. Open `source_url`. That is the jurisdiction's own copy of the code.
2. Find the district's whole use list or use-table column. `section` says where the pipeline looked, but it can point at the wrong place or hint at an answer. Read the whole list for the district, the table key, and any definition of the use, and do not stop at the cited section.
3. Decide which local uses fall in the `use_class` (the classes are listed in the repository `README.md` and defined in `taxonomy/v1.json`).
4. Write one status in `human_status`, and a short reason with the section you relied on in `human_notes`.

## Status values

These are the rules in `taxonomy/v1.json`, which the models also followed:

| Status | Use it when |
|---|---|
| `permitted` | Allowed by right, possibly with objective standards (P, PS, P*) |
| `conditional` | Allowed only after a discretionary approval: conditional use, special exception, special use permit (C, CU, SE, S, SUP) |
| `prohibited` | Expressly not allowed in the district. A blank table cell is `prohibited` when the table key says a blank means not allowed. A use allowed only by rezoning to a planned development or overlay, or only as an accessory use, is `prohibited` in the base district |
| `unlisted` | The use is not named in the code and no definition captures it. A clause saying "uses not listed are prohibited" does not turn an unlisted cell into `prohibited`; it stays `unlisted` |

The `us-12069` (Lake County) rows cite an unadopted draft ordinance, because it is the only copy of that code on the county's own server. Label what that document says and note "draft" in `human_notes`. Do not look for the adopted code on a third-party code host; the repository's denylist (`policy/denylist.txt`) bans those hosts.

The `us-51061` (Fauquier County) source URLs are on the county's own site, which serves a bot wall to automated clients; open them in an ordinary browser.

If none of these fits, or the source cannot be read, write `unclear` and explain in `human_notes`. Pending amendments and moratoria do not change the status; note them instead.

## When you finish

- Record the minutes you spent in `human_notes` on the first row (for example `audit time: 115 min`).
- Commit the labelled sheet as a new version, `z0_audit_sheet.v0.4.0.csv`, and leave v0.1.0 to v0.3.0 unchanged.

Audited cells become grade A. Grade A means a person checked the cell against the source text. It is not a legal sign-off.
