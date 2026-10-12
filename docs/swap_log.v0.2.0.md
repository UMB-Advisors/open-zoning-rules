# Pilot swap log (v0.2.0)

**Date:** 2026-10-11 · **Step:** Z0.12 swaps · Supersedes `docs/swap_log.v0.1.0.md`, which is kept.

## TL;DR

- Four maintainer-approved swaps (2026-10-11) bring the pilot back to 10 jurisdictions that each have their zoning text on their own government site.
- Out: Polk County FL, Hillsborough County FL, City of Atlanta GA, Coweta County GA. In: Palm Beach County FL, Santa Rosa County FL, Hall County GA, Cherokee County GA.
- Lake County FL stays. Its only text is an unadopted draft, so every Lake cell is labelled `code_status: unadopted_draft` and capped at grade C.
- The swapped-out jurisdictions are retired, not deleted, where frozen known answers still cite them. Their known answers are out of scope and unscored.

## Swaps applied 2026-10-11

| Out | In | Reason (maintainer, 2026-10-11) |
|---|---|---|
| Polk County, FL (us-12105) | Palm Beach County, FL (us-12099) | Polk's code exists only on a code publisher whose terms the maintainer reads as forbidding LLM use, and on its own site only by public records request |
| Hillsborough County, FL (us-12057) | Santa Rosa County, FL (us-12113) | Hillsborough's current code (with the use table) exists only on a code publisher whose terms the maintainer reads as forbidding LLM use; its own site carries only a 2022 supplement |
| City of Atlanta, GA (us-1304000) | Hall County, GA (us-13139) | Atlanta's zoning ordinance is reachable only through a code publisher whose terms the maintainer reads as forbidding LLM use; the city site refuses automated fetches |
| Coweta County, GA (us-13077) | Cherokee County, GA (us-13057) | Coweta's zoning ordinance exists only on a code publisher whose terms the maintainer reads as forbidding LLM use |

The publishers' terms were not re-read for this step; the reason is the maintainer's stated reason. Whatever their terms say, the spec forbids extracting from a code publisher, and all four publishers are on the denylist.

## Why each new pick

| In | Own-site text | Data-center relevance |
|---|---|---|
| Palm Beach County, FL | The Unified Land Development Code, Supplement 32, as article PDFs on `pbc.gov` (Articles 1, 4 and 5 registered; Article 3 fetched and left out, see the licence matrix) | Article 4's Light Industrial use matrix lists "Data and Information Processing", read as the datacenter class. The county's own September 24, 2026 hearing agenda lists "Large-Scale Data Center Moratorium – Second Reading and Adoption"; the outcome is not on a county page (see below) |
| Santa Rosa County, FL | The full Land Development Code (Ord. 2025-25, 2025-11-10) as one PDF on `santarosa.fl.gov` | The code has no use called a data center; its "Technology Business" use is read as datacenter in some cells. A 2026 moratorium is reported, but no county-domain copy was found |
| Hall County, GA | The Unified Development Code adopted 2026-09-10, one PDF on `hallcounty.org` | Sec. 7.6.2 defines data centers in four tiers; the allowed use table lists "All data center" as SU in I-1 and I-2 only |
| Cherokee County, GA | Zoning Ordinance articles and Table 7.2 as PDFs on `cherokeecountyga.gov` | Table 7.2 lists "Data Processing, Hosting, and Related Services" (NAICS 514210). A 2026 moratorium is reported on the county's news page; the resolution itself is on a vendor portal |

## Retired jurisdictions

| Jurisdiction | Directory | Why it is kept or removed |
|---|---|---|
| Polk County, FL (us-12105) | **Removed** (and its `primary_hosts` entry) | No known answer cites it |
| Hillsborough County, FL (us-12057) | Kept, `retired` | Known answer `hillsborough-base-datacenter` cites district M |
| City of Atlanta, GA (us-1304000) | Kept, `retired` | Known answers `atlanta-beltline-datacenter` and `atlanta-i-mix-datacenter` |
| Coweta County, GA (us-13077) | Kept, `retired` | Known-answer amendment `coweta-datacenter-moratorium-2026` |

`tests/known_answers.json` is frozen and was not edited. `ozr.triage` still validates every known answer against its jurisdiction and district, so the three directories stay. They carry `retired: {date, reason}`, `ozr` stage selection (`--all`, the default release set) skips them, and they never had cells, so nothing of theirs is released. Their run ledgers are kept.

The 4 new jurisdictions have no known answers: the file was frozen before the first extraction and cannot be extended.

## Lake County, FL

Kept by maintainer decision. `jurisdiction.json` carries `code_status: unadopted_draft`; every published Lake cell carries the same field and is capped at C by `ozr grade` and the release gate.

## Amendment records not written

| Jurisdiction | Action reported | What the county's own site has | Recorded |
|---|---|---|---|
| Palm Beach | Large-Scale Data Center definition and one-year moratorium, second reading 2026-09-24 | The September 24, 2026 hearing agenda and the second-reading staff report, both written before the vote. The county's ordinance library has no copy of the adopted ordinance | Nothing: the outcome is not confirmed on a county page |
| Santa Rosa | One-year moratorium on large-scale data centers, 2026-07-23 | A business impact estimate for the proposed ordinance. Board agendas and minutes are on a vendor portal | Nothing |
| Cherokee | 30-day moratorium 2026-07-21, extended 180 days 2026-08-18 | A county news release describing the votes. The resolution and minutes are on a vendor portal | Nothing: a press release is not a copy of the resolution |
| Hall | A 180-day suspension of data-center special-use applications from 2026-02-26 | The resolution is on the agenda vendor's storage host, and it expired on its own terms on 2026-08-26 | Nothing |

Under spec rule 5 none of these would change a cell; each would only mark affected cells stale.
