# Pilot swap log (v0.1.0)

**Date:** 2026-10-09 · **Step:** Z0.2 triage

## TL;DR

- Two swaps were applied: City of Port St. Lucie, FL went out and Lake County, FL came in. Prince William County, VA went out and Fauquier County, VA came in.
- One swap was triggered but not applied: Coweta County, GA stays in, because the only GA alternate fails the same test.
- Polk County, FL, Coweta County, GA and City of Atlanta, GA need a human decision on the primary-host rule.

**The swap rule.** If a pick has no usable primary copy of its zoning ordinance (the code exists only on a third-party host, and the jurisdiction's own site has no adopted ordinance or zoning PDF), the same state's alternate comes in. A swap can also be made for coverage.

## Swaps

| Date | Out | In | Reason |
|---|---|---|---|
| 2026-10-09 | City of Port St. Lucie, FL (us-1258715) | Lake County, FL (us-12069) | The city has no primary copy. Its Planning and Zoning page links the zoning code only to a third-party publisher, and its charter and ordinances page redirects there. The rationale for picking it also failed: the withdrawn 2026 data-center application was in unincorporated St. Lucie County, not the city. Lake County is no stronger on the primary-copy test (its adopted LDR is also only with a third-party publisher). It was taken for coverage: a data-center moratorium adopted 2026-09-08 and a pending schedule-of-uses amendment, both on the county's own file server. |
| 2026-10-09 | Prince William County, VA (us-51153) | Fauquier County, VA (us-51061) | Prince William's own zoning page sends readers to a third-party code host. Its domain has only individual amendment and draft PDFs, not the adopted ordinance. Fauquier posts its full ordinance as article PDFs on its own site. (That site refuses automated fetches; see the licence matrix.) |
| 2026-10-09 | (none) Coweta County, GA stays | (none) | The swap rule is triggered, since Coweta's zoning ordinance is reachable only through a third-party publisher. It was not applied: the GA alternate, Fayette County, publishes its zoning chapter the same way, so swapping would gain nothing and would lose the GA moratorium case. |

## Kept picks that fail or partly fail the primary-copy test

| Jurisdiction | Status | What is on its own domain |
|---|---|---|
| Polk County, FL | analyst_fetch; needs human decision | Planning page and ordinance index only. Copies of ordinances are by public records request. No FL alternate remains. |
| Hillsborough County, FL | partial; analyst_fetch for the use table | LDC Supplement 50 (2022): replacement pages with no use table and no unlisted-use clause. 2026 Board agenda backup. |
| Coweta County, GA | analyst_fetch; needs human decision | Zoning Division page only. Minutes recording the 2025-12-16 data-center amendments and the 2026 moratorium are on a vendor-hosted meeting portal. |
| City of Atlanta, GA | analyst_fetch; needs human decision | The city site refuses automated fetches. The adopted data-center ordinances (24-O-1218, 24-O-1222) are on the vendor-hosted Council legislation portal. |

## Rationale checks

| Jurisdiction | Rationale in the plan | Result |
|---|---|---|
| Polk County, FL | Industrial corridor; FL cannabis preemption case | Partly supported. The cannabis preemption is statewide (s. 381.986(11), F.S.). The county's own records show a 2024 warehouse and distribution separation amendment. |
| City of Port St. Lucie, FL | Hostile: 2026 data-center withdrawal | Failed. The application was in unincorporated St. Lucie County. |
| Hillsborough County, FL | Permissive / control; zoning on its own ArcGIS | Confirmed (CC BY 4.0 layer). The control role is weakened: on 2026-08-05 the Board directed staff to draft a data-center moratorium, deferred because state law bars new restrictive regulations in listed counties before 2027-10-01. |
| Loudoun County, VA | Explicit datacenter use; by-right ended by a 2025 amendment | Confirmed. The code defines the use, and ZOAM-2024-0001 (2025-03-18) requires a special exception in IP, GI and MR-HI. |
| Pittsylvania County, VA | Hostile, rural; a rezoning denied 6-1 in 2025 | Confirmed by news coverage. The code has since added a defined data-center use (Sec. 35-142) and an M-SVMS mega-site district. |
| Town of Warrenton, VA | Removed data centers from its code, 2025 | Confirmed. The town's July 2026 Article 3 lists no data centers in the industrial district, and Sec. 2-10 prohibits unlisted uses. |
| Coweta County, GA | Mixed: approval 3-2, then a moratorium | Partly confirmed, and the plan's dates are wrong. The Board minutes record the approval on 2026-04-07 (not 2025) and a second moratorium from 2026-06-16 to 2026-12-13. |
| Douglas County, GA | Permissive / control, part of a cluster (recalled from memory) | Partly. The county code now names the use as special-use only in OI, LI, LI-R and HI, which reads as regulated rather than permissive. A 2025 moratorium expired in September 2025. |
| City of Atlanta, GA | Restrictions near the BeltLine and transit, 2024 (recalled from memory) | Confirmed on the Council's legislation portal: 24-O-1218 and 24-O-1222, both adopted 2024-09-03. |

## Coverage after the swaps

| Status class | Where it appears in the known answers |
|---|---|
| permitted | Pittsylvania M-SVMS, Fauquier BP (quote not yet verified), Atlanta I-MIX (parcel-specific) |
| conditional | Loudoun IP, GI and MR-HI (amended after the source text), Pittsylvania M-2, Douglas OI, LI, LI-R and HI |
| prohibited | Warrenton I, Douglas (10 districts, from the table key), Atlanta BeltLine Overlay |
| unlisted | Hillsborough (representative cell M), Lake (representative cell LM) |
| moratorium or amendment records | Lake (moratorium and pending amendment), Coweta (moratorium), Loudoun (ZOAM-2024-0001), Warrenton (2025 removal) |
| preemption | FL cannabis (state siting), VA cannabis and battery storage, GA hazardous waste and LP gas |
