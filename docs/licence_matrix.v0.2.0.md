# Licence and source matrix (v0.2.0)

**Date:** 2026-10-11 · **Step:** Z0.12 swaps · **Data:** `jurisdictions/<id>/sources.json`, `policy/primary_hosts.json` · Supersedes `docs/licence_matrix.v0.1.0.md`, which is kept.

## TL;DR

- The pilot is 10 jurisdictions again. Four swap-ins replace four picks whose code exists only on a code publisher (maintainer approval, 2026-10-11; see `docs/swap_log.v0.2.0.md`).
- All 15 new sources are on a host the county owns, fetched in one batch with the project user agent on 2026-10-11 and hashed. `python -m ozr.triage` passes.
- No new layer grants redistribution, so the release still ships pointers, not polygons, for every new jurisdiction.
- The rows for Loudoun, Pittsylvania, Warrenton, Fauquier, Douglas and Lake are unchanged from v0.1.0. Lake's only text is an unadopted draft, now labelled on every cell (`code_status: unadopted_draft`).
- Polk, Hillsborough, Atlanta and Coweta are retired. Their v0.1.0 rows stand as a record; none of their sources is used.

## New rows

| Jurisdiction | Source | Kind | Host | Owner evidence | Terms | Redistribute geometry | Triage |
|---|---|---|---|---|---|---|---|
| Palm Beach County, FL (us-12099) | us-12099-uldc-art1, -art4, -art5 (ULDC Articles 1, 4 and 5, Supplement 32) | ordinance | pbc.gov | The county's ULDC page; `www.pbcgov.org`, `pbcgov.org` and `www.pbc.gov` all resolve to the county portal `discover.pbc.gov` | The ULDC disclaimer: content is made available "for informational purposes only" and "provided 'as is' without warranty of any kind". Enacted law, public record | unknown | ok |
| Palm Beach County, FL | us-12099-gis-zoning (Planning_Open_Data MapServer layer 9) | gis_layer | maps.co.palm-beach.fl.us | Copyright text "Palm Beach County Planning Zoning & Building GIS/Information Technology Section" | No licence or redistribution grant on the service. The layer also carries city zoning, marked "(city)"; only unincorporated codes are districts | unknown | geometry_restricted |
| Santa Rosa County, FL (us-12113) | us-12113-ldc (Land Development Code, Ord. 2025-25, 2025-11-10) | ordinance | www.santarosa.fl.gov | County DocumentCenter. A HEAD request returns 404; GET returns the PDF | Enacted law, public record; no terms on the page | unknown | ok |
| Santa Rosa County, FL | us-12113-gis-zoning (Zoning FeatureServer layer 0) | gis_layer | services.arcgis.com, org `Eg4L1xEv2R3abuQd` | Portal record: name "Santa Rosa County, Florida - GIS Data Portal", urlKey `SantaRosaGIS`, description "GIS department for the Santa Rosa County, Florida Board of County Commissioners". The county's Mapping/GIS page links `santarosagis.maps.arcgis.com` | Item licence empty. The summary says the data is "to be used to provide vector data for zoning analysis"; updated 2026-09-28 for the 2026-09-24 Board meeting | unknown | geometry_restricted |
| Hall County, GA (us-13139) | us-13139-udc (Unified Development Code, adopted 2026-09-10) | ordinance | www.hallcounty.org | County DocumentCenter; every page is stamped "Adopted 09/10/2026" | Enacted law, public record | unknown | ok |
| Hall County, GA | us-13139-gis-zoning (ZoningTab MapServer layer 15) | gis_layer | hallgis.hallcounty.org | County ArcGIS Server on the county domain | No licence, copyright or terms on the service | unknown | geometry_restricted |
| Cherokee County, GA (us-13057) | us-13057-zo-art4, -art5, -art6, -art7, -t72, -art16, -art18 (Zoning Ordinance Articles 4, 5, 6, 7, 16 and 18 and Table 7.2) | ordinance | cherokeecountyga.gov | The county's Zoning Ordinance page | Enacted law, public record; no terms on the page | unknown | ok |
| Cherokee County, GA | us-13057-gis-zoning (ZoningOnline MapServer layer 3) | gis_layer | gis.cherokeecountyga.gov | County ArcGIS Server on the county domain | No licence on the service. **The layer is parcel-based and carries owner names and mailing addresses**: only the `Zoning` field is read, with distinct-value queries | unknown | geometry_restricted |

`policy/primary_hosts.json` gains `pbc.gov`, `pbcgov.org` and `co.palm-beach.fl.us` for us-12099; `santarosa.fl.gov` plus ArcGIS org `Eg4L1xEv2R3abuQd` for us-12113; `hallcounty.org` for us-13139; and `cherokeecountyga.gov` for us-13057. The us-12105 entry is removed with its directory.

## Fetched and left out

| Jurisdiction | Document | Why it is not registered |
|---|---|---|
| Palm Beach | ULDC Article 3, Overlays and Zoning Districts (sha256 `fd0c3122...`) | It was fetched and segmented. Its district-list pages alone (215) would have doubled every model prompt, to about 335,000 tokens, which is past what the reviewers have handled before. It contains no term of the classes most likely to be unlisted (data center, cannabis, battery storage, LP gas). The absence gate does not read it; unlisted Palm Beach cells are as good as Articles 1, 4 and 5 |
| Palm Beach | The rest of the ULDC (Articles 2 and 6 to 18) | Not fetched. The use matrices and use definitions are in Article 4 |
| Cherokee | Articles 1 to 3, 8 to 15, 17 and 19 to 27 | Not fetched. Article 17 was read in triage: it has no unlisted-use clause |

## How dates were set

| Field | Rule |
|---|---|
| `code_version` | Santa Rosa 2025-11-10 (the LDC revision table: Ord. 2025-25). Hall 2026-09-10 (the adoption stamp). Palm Beach and Cherokee `unknown`: Palm Beach states "Supplement 32 (Printed 10/25)" and lists four 2025-2026 ordinances not yet incorporated; Cherokee's articles carry different dates |
| `source_date`, ordinance | The date the document states (Cherokee from each article's date stamp, Hall 2026-09-10, Santa Rosa 2025-11-10). Palm Beach `unknown` |
| `source_date`, GIS | Santa Rosa `editingInfo.dataLastEditDate` (2026-09-28). Palm Beach the latest `DT_CHG` (2026-08-13). Hall the latest `ZN_EDIT_DA` (2026-09-24). Cherokee `unknown`: no date field |

## District universes

| Jurisdiction | Districts | From | Left out |
|---|---|---|---|
| Palm Beach | 40 | Distinct `FCODE` values without "(city)" | `None` |
| Santa Rosa | 63 | Distinct `DISTRICT` values, including the airport-zone variants (`R1-APZ 1`, `M2-CZ`, ...) as their own districts | `CITY`, `WATER`, `RAIL` |
| Hall | 19 | Distinct `ZN_CLASS` values | none. R-SF, R-TH and M-U, new in the 2026 UDC, have no polygons yet |
| Cherokee | 22 | Distinct `Zoning` values | `NULL` (5 polygons) and `C` (1 polygon, no such district). `R-15`, `R-30`, `R-40` and `R-80` spellings (54, 50, 54 and 1 polygons) duplicate `R15`, `R30`, `R40` and `R80`; the pointer carries the common spelling. `CP` is in the ordinance but has no polygons |

Planned-development districts are `parcel_specific` (capped at C): Palm Beach PUD, MUPD, MXPD, PIPD, RVPD, TMD and the AGR and RR planned variants; Santa Rosa PUD, PBD and NB-PMUD; Hall's legacy PCD, PCFD, PID, POD and PRD; Cherokee PUD, PDTND and TND.

`conditional_zoning_unmapped` is true for all four. Palm Beach has a Conditional Overlay Zone that `FCODE` does not show; Santa Rosa's code records rezoning conditions; Hall's layer flags conditions per polygon (`ZN_CONDITI` C or N), which a district pointer cannot carry; Cherokee's Article 18 lets the Board approve a rezoning "with or without conditions", and its layer has no condition field.
