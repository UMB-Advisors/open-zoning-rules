# Licence and source matrix (v0.1.0)

**Date:** 2026-10-09 · **Step:** Z0.2 triage · **Data:** `jurisdictions/<id>/sources.json`, `policy/primary_hosts.json`

## TL;DR

- 10 jurisdictions, 30 registered sources, all on a host the jurisdiction owns (checked by `python -m ozr.triage`).
- 6 jurisdictions have a usable primary copy of their zoning text: Loudoun, Pittsylvania, Warrenton, Douglas, and partial copies for Hillsborough and Lake. Polk, Coweta and Atlanta are `analyst_fetch`. Fauquier publishes its code on its own site, but the site refuses automated fetches.
- Only Hillsborough's zoning layer grants redistribution (CC BY 4.0). Coweta's policy forbids re-use. Every other layer is `unknown`, so the release ships pointers rather than polygons.
- Three questions need a human decision. They are listed at the end.

## How to read it

- **Host** is the host of the requested URL. The primary-host rule is checked on that host. Redirect targets are checked against the denylist only.
- **Owner evidence** is why the host counts as the jurisdiction's own.
- **Triage** is the `sources.json` value: `ok`, `geometry_restricted` (GIS terms do not grant redistribution) or `analyst_fetch` (no usable primary copy, so a human must request one).
- For ordinance text, `redistribute_geometry` is `unknown` by convention, because the field applies to geometry. Enacted law is not copyrightable (spec 6).
- The rows marked **not registered** were not fetched, or are hosted by a vendor. They have no `sources.json` entry, and are listed so nothing is dropped silently.

## Matrix

| Jurisdiction | Source | Kind | Host | Owner evidence | Terms | Redistribute geometry | Triage |
|---|---|---|---|---|---|---|---|
| Polk County, FL (us-12105) | us-12105-planning-tools | ordinance | www.polkfl.gov | County site | The page links the Land Development Code only to a third-party code publisher | unknown | analyst_fetch |
| Polk County, FL | us-12105-ordinance-index | amendment | apps.polk-county.net | County ordinance index, linked from polkfl.gov | "To obtain a copy of an ordinance, please submit a Public Records Request" | unknown | analyst_fetch |
| Polk County, FL | us-12105-gis-flu | gis_layer | gis.polk-county.net | County ArcGIS Server; copyright names the county GIS/IT Division and Office of Planning and Development | Copyright text only ("Updated September 20, 2016"); no licence or terms page found | unknown | geometry_restricted |
| Hillsborough County, FL (us-12057) | us-12057-ldc-page | ordinance | hcfl.gov | County site (hillsboroughcounty.org redirects there) | Links the compiled code only to a third-party publisher | unknown | analyst_fetch |
| Hillsborough County, FL | us-12057-ldc-supp50 | ordinance | hcfl.gov | County asset link. **It redirects to assets.contentstack.io**, the county CMS's asset store | Public record. Supplement 50 only (through Ord. 22-13, 2022-06-15), with no use table and no unlisted-use clause | unknown | analyst_fetch |
| Hillsborough County, FL | us-12057-bocc-2026-08-05 | minutes | eagenda.hcfl.gov | County agenda portal on the county domain | Public record | unknown | ok |
| Hillsborough County, FL | us-12057-gis-zoning | gis_layer | services.arcgis.com, org apTfC6SUmnNfnxuF | Org name "Hillsborough County ArcGIS Online Community (AGOL)" | "This work is licensed under a Creative Commons Attribution 4.0 International License." | yes | ok |
| Lake County, FL (us-12069) | us-12069-planning-page | ordinance | c.lakecountyfl.gov | County site | Links the adopted Land Development Regulations only to a third-party publisher. The county ordinances page refuses automated fetches | unknown | analyst_fetch |
| Lake County, FL | us-12069-ord-2026-xx-draft | amendment | c.lakecountyfl.gov | County file server, 2026-10-07 Planning and Zoning Board packet | Public record. **Unadopted draft**; it reprints Sec. 3.01.02 and the Sec. 3.01.03 schedule of uses | unknown | ok |
| Lake County, FL | us-12069-gis-zoning | gis_layer | gis.lakecountyfl.gov | County ArcGIS Server; copyright "Lake County Economic Growth" | Metadata: users must acknowledge Lake County, and new data generated from it is to be made available on request. The GIS policy says data is "freely available for download" with no explicit redistribution grant | unknown | geometry_restricted |
| Loudoun County, VA (us-51107) | us-51107-zo-ch3, us-51107-zo-ch12 | ordinance | www.loudoun.gov | County DocumentCenter | Public record. Adopted 2023-12-13 text (clean copies dated 11-21-23); later amendments are not included | unknown | ok |
| Loudoun County, VA | us-51107-zo-faq | ordinance | www.loudoun.gov | County FAQ confirming that the PDFs are the adopted text | Public record | unknown | ok |
| Loudoun County, VA | us-51107-dc-phase1 | amendment | www.loudoun.gov | County project page for ZOAM-2024-0001 | Public record | unknown | ok |
| Loudoun County, VA | us-51107-gis-zoning | gis_layer | logis.loudoun.gov | County ArcGIS Server (Office of Mapping and Geographic Information) | Disclaimer only; no open-data licence found | unknown | geometry_restricted |
| Pittsylvania County, VA (us-51143) | us-51143-zo-ch35 | ordinance | www.pittsylvaniacountyva.gov | County DocumentCenter. View/1268 is current; View/1060 and View/251 are a stale May 2024 copy | Public record | unknown | ok |
| Pittsylvania County, VA | us-51143-gis-zoning | gis_layer | services2.arcgis.com, org mTpBDvIjv8OhMDVd | Org name "Pittsylvania County" | No licence on the item. Other items cite a county GIS licence agreement that was not found. **The layer is parcel-based and carries owner names and addresses:** only `PC_ZONE_CODE` is used | unknown | geometry_restricted |
| Town of Warrenton, VA (us-5183136) | us-5183136-zo-page, -zo-art2, -zo-art3, -zo-art12 | ordinance | www.warrentonva.gov | Town DocumentCenter | Public record. The amendment table runs to ZOTA-26-1 (2026-07-14) | unknown | ok |
| Town of Warrenton, VA | us-5183136-gis-zoning | gis_layer | services3.arcgis.com, org 7Q2bdSYWSeUYx2U5 | Org urlKey `townwarrenton`; item "TOW Zoning Districts", access information "Town of Warrenton". The town GIS page links the org's apps | Item licence text: the Town assumes no legal responsibility; data "for DISPLAY PURPOSES ONLY". No redistribution grant | unknown | geometry_restricted |
| Fauquier County, VA (us-51061) | Zoning Ordinance page and Articles 2, 3, 15 (**not registered**) | ordinance | www.fauquiercounty.gov | County site | **Not fetched.** The site returns HTTP 403 from a bot wall to the project user agent, with or without browser-style headers. Getting past it would need a disguised client, which is not done. The page states the code is amended through 2026-07-09 (triage, not re-read) | unknown | analyst_fetch (not registered) |
| Fauquier County, VA | us-51061-gis-zoning | gis_layer | services.arcgis.com, org oAoeYJ1kqmAwcEC2 | Org name "FAUQUIER COUNTY MAPS" | No licence on the item; other items carry a no-liability disclaimer. Proffers are in a separate layer | unknown | geometry_restricted |
| Coweta County, GA (us-13077) | us-13077-zoning-division | ordinance | www.coweta.ga.us | County site | Links the zoning ordinance (Code Appendix A) only to a third-party publisher | unknown | analyst_fetch |
| Coweta County, GA | us-13077-gis-zoning | gis_layer | coweta-gis-web.coweta.ga.us | County ArcGIS Server | GIS Information Policy (2008): non-governmental organisations receive data under an agreement that "prohibits selling and re-use of the data" | no | geometry_restricted |
| Coweta County, GA | Board minutes (**not registered**) | minutes | cowetacoga.api.civicclerk.com | Meeting portal linked from the county site, **hosted by a vendor** | Public record. Cited by the moratorium amendment record only | n/a | human decision |
| Douglas County, GA (us-13097) | us-13097-udc-page, us-13097-udc | ordinance | www.douglascountyga.gov | County site. The page says the third-party copy "does not reflect all adopted changes", so the county PDF is the authoritative copy | Public record. Updates through August 2026; PDF metadata 2026-08-18 | unknown | ok |
| Douglas County, GA | us-13097-gis-zoning | gis_layer | maps.douglascountyga.gov | County ArcGIS Server | No licence on the service. The county GIS FAQ says data is available for purchase | unknown | geometry_restricted |
| City of Atlanta, GA (us-1304000) | Part 16 Zoning (**not registered**) | ordinance | www.atlantaga.gov | City site | **Not fetched**: HTTP 403 to automated requests. The layer's description field links each district to a third-party publisher, which is not used | unknown | analyst_fetch (not registered) |
| City of Atlanta, GA | us-1304000-gis-zoning, us-1304000-gis-overlay | gis_layer | gis.atlantaga.gov | City Department of City Planning ArcGIS Server | Published as Open Data; copyright, licence and access fields are empty | unknown | geometry_restricted |
| City of Atlanta, GA | Ordinances 24-O-1218 and 24-O-1222 (**not registered**) | amendment | atlantacityga.iqm2.com | City Council legislation portal, **hosted by a vendor** | Public record (certified ordinance PDFs). Cited by two known-answer cells | n/a | human decision |

## How dates were set

| Field | Rule |
|---|---|
| `code_version` | The adoption or amendment date the fetched text itself states. Loudoun is 2023-12-13 (county FAQ). Pittsylvania is 2026-08-18, the latest amendment stamp; 24 other stamps read 08/16/2026. Warrenton is 2026-07-14 (ZOTA-26-1 in the town's amendment table). Hillsborough is 2022-06-15, which is Supplement 50 only, **not** the current code. All others are `unknown` because no full code text was fetched (Douglas says only "Updates through August 2026"). |
| `source_date`, ordinance | The date the document states. Otherwise the PDF modification date (Douglas 2026-08-18; Lake draft 2026-09-22). Otherwise `unknown`. |
| `source_date`, GIS | `editingInfo.dataLastEditDate` where the service reports it (Hillsborough, Pittsylvania, Warrenton, Fauquier). Otherwise the latest value of the layer's own date field: Lake `OrdDate` 2026-09-01, Loudoun `ZO_UPD_DATE` 2026-07-30, Coweta `last_edited_date` 2026-10-01, Atlanta `LASTUPDATE` 2026-08-25. Polk has no date field values, so its copyright date 2016-09-20 is used, which also flags the layer as possibly stale. Douglas is `unknown`. |

## Needs human decision

1. **Polk County, FL.** The county hosts no copy of its Land Development Code; it is reachable only through the third-party publisher or a public records request. There is no second FL alternate. Options: keep Polk as `analyst_fetch` (a records request to the clerk), or name a new FL alternate.
2. **Coweta County, GA and City of Atlanta, GA.** Neither hosts its zoning text on its own domain. Their adopted data-center amendments and minutes sit on vendor-hosted official portals (CivicClerk, Granicus iqm2). Options: accept official vendor-hosted portals as primary for adopted records, plus an analyst fetch of the full code; or source new GA alternates. The only GA alternate, Fayette, also publishes its zoning chapter only through a third-party publisher.
3. **Fauquier County, VA.** The full code is on the county's own site, but the site blocks automated fetches. A human download of Articles 2, 3, 5 and 15 (and Article 3's image-only use table) is needed before Z0.3 can hash and segment it.

## Other caveats

- **Hillsborough:** the hcfl.gov asset link resolves to assets.contentstack.io. The primary-host rule passes on the requested hcfl.gov URL, and the final host is recorded as `final_url`.
- **Lake:** its only text source is an unadopted draft. Rows the draft leaves unchanged are usable with care. The adopted LDR is `analyst_fetch`.
- **Loudoun:** the own-domain PDFs predate ZOAM-2024-0001 (2025-03-18). The current text exists only on a third-party interactive host, which is not used.
- **Polk:** layer 9 is "Future Land Use 2030". The county uses unified land-use districts, so `FLU_LDC` carries the LDC district code. The layer's copyright text is dated 2016-09-20. PD, PUD, SPD and DRI overlay layers (1 to 4) are not yet in the district list.
