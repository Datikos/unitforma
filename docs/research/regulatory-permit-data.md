# Regulatory permit data as a project source (Georgia: tas.ge / Tbilisi Architecture Service)

**Status:** researched on 2026-10-25 against permit `documentId=1127975` (a III-class multi-apartment
building in Tbilisi, "corrected project approval + construction permit", decided 2026-02-24).
Working prototype: `tools/research/tasge/extract_permit.py` and `scan_plans.py`.

## 1. How the public permit page works

| Layer | Finding |
|---|---|
| `https://tas.ge/?p=publicpage&documentId=<id>` | A 2011-era shell page (jQuery 1.6, DWR). It only embeds an iframe. |
| `https://docs.tbilisi.gov.ge/architect/public.html?docId=<id>` | The real page: an ExtJS application that loads ~180 JS modules and then makes **one data call**. |
| `POST https://docs.tbilisi.gov.ge/architect/dwr/call/plaincall/UserMethods.getUserDocumentLastMotion.dwr` with `c0-param0=string:<docId>` | Returns the complete permit record (≈ 370 KB) as DWR JavaScript. **It replays with a plain HTTP POST**, no cookies or browser session needed (the `windowName=` line must be present). |
| `https://docs.tbilisi.gov.ge/DownloadServlet?downloadCase=2&attachedFileId=<id>` | Attachment download (PDF, JPG, `.pla` Archicad, `.rar`). Unauthenticated. |
| `https://docs.tbilisi.gov.ge/NewArchitectureResponse?documentId=<id>&motionId=<id>` | The decision document (order) as PDF, text layer present on the generated pages. |
| `https://docs.tbilisi.gov.ge/ArchitectureViewMessage?messageId=<id>` | Correspondence letters as PDF (the sample is a scanned image, no text layer). |
| `https://esign.tbilisi.gov.ge/api/signature/download/file?fileId=<id>` | Electronically signed decision files (third host; needs its own allow-list entry). |
| `robots.txt` | Not present (404). No API documentation, no terms-of-use page found on the site. |

Nothing is indexed by search engines; the pages are only reachable with a `documentId`. There is no
list or search endpoint for the public (the site's own search says "in preparation").

## 2. What the record contains (structure of the DWR payload)

`sources[1]` is the document wrapper with these sections (counts from the sample):

| Section | Content | Use for Unitforma |
|---|---|---|
| `document` | `documentNo` (AR11127975), `documentId`, `createDateStr`, `registrationDate`, `deadLineDate`, `address`, `documentStatusId`, `responseText` (decision HTML), `cachedInfo` (XML with nomenclature) | Project identity, dates, decision text |
| `cachedInfo` → `nomenklature` | category ("multi-apartment residential building"), class (III), action ("change of agreed project"), stages ("project approval", "construction permit") | Project type and permit stage |
| `docClassCalculatorValues` (6) | K2 calculation area 3610.4 m², height 14.7 m, depth below grade 4.05 m, max span 7.4 m, foundation type, lifts | Building parameters |
| `mapInfos` (1) | National registry (NAPR) parcel: cadastral code `01.72.16.097.088`, address, area 4865 m², purpose, owner (company + ID), zone flags | Site/parcel; join key to napr.gov.ge |
| `docValues` (360, all revisions) + `fieldsetPojos` (36 fieldsets with field labels) | Every form field with its Georgian label: request text, previous order numbers/dates, functional purpose, **technical-economic indicators** (plot area, footprint 5074.9, total 4321.5, residential 2556.3, summer 394.7, basement 633.7, stairs/lobby 736.8 m², volume 14381.1 m³, heights, K1/K2/K3 as "κ=0.9 (3610.4/4144)"), construction permit fee, plus **personal data** of the architect, client, experts (names, personal numbers, phones, emails) | Areas and parameters; PII must be dropped |
| `attachedFiles` (170 active incl. upload revisions) | per fieldset: general plan (PDF + `.pla`), landscaping, photos, **floor plans PDF (51 pages)**, sections, facades, height scheme, renders, **Archicad `.pla` of the building**, structural conclusion, utilities scheme, visiting-card images, expert report, energy declaration, schedule, power of attorney | The drawings for the ingestion pipeline |
| `oldResponseMotions` (4), `userSignatures` (3), `messages` (7) | Decision versions, signed files, correspondence | Audit trail |
| `docAuthor`, `executorEmployee` | Applicant and the official handling the case, with personal data | Never store |

Observed mapping: `documentStatusId = 3` renders as "თანხმობა" (consent/approved) on the page; other
status ids are unknown until more samples are checked.

## 3. The drawings themselves (sample)

The floor-plan attachment is an Archicad PDF export ("GSPublisherVersion"): 51 pages, fully vector
(5 000–40 000 line objects per plan sheet), A1 sheets at 1:100, with a text layer. Georgian text in
the CAD font surfaces as a Latin transliteration (`bina #32` = "apartment №32", `m.1/100` = scale,
`gegma 00.00, +1.00, +2.00 niSnulebze` = "plan at levels 0.00, +1.00, +2.00"). Per sheet the scanner
finds apartment labels, areas ("42.7 m2" next to each apartment), level markers, grid axes and parking
labels (`A9/10-24 12.5 m2`). On the sample the scanner finds 42 distinct apartment labels and 26 parking spaces across the four architectural plan sheets (pages 2–5; later sheets are discipline copies). Areas are printed per apartment, which gives the mapping workflow an
authoritative schedule to verify measured polygons against.

Consequences for plan §13: this is the **best case** for assisted extraction (clean vectors, labels,
areas, scale). Scanned sheets and letters still need OCR or manual work. Even here the apartment
boundary is not a labelled polygon in the PDF; it must be proposed from the vector lines and confirmed
by a reviewer.

## 4. Feasibility verdict

| Task | Verdict | Notes |
|---|---|---|
| Fetch a permit by id and get structured data | **Yes, easy** | One POST, parse DWR (prototype does this in ~150 lines, standard library). |
| Bootstrap a project from it (name, address, parcel, category, class, areas, heights, decision date) | **Yes** | `permit` + `nomenclature` + `class_calculator` + `technical_indicators` + `parcels`. |
| Pull the drawings into the document pipeline | **Yes** | `attachments[].download_url`; take `latest_in_fieldset = true`; classify by fieldset title (site plan, floor plans, sections, facades, renders). |
| Derive floors and apartment count | **Assisted** | Level markers and apartment labels per sheet give floor candidates and counts; reviewer confirms. |
| Derive unit polygons and areas | **Assisted / manual** | Polygons proposed from vectors, areas verified against the printed per-apartment areas (plan §13.2). |
| Use the Archicad `.pla` | **Later** | No open parser; ask the developer for IFC export instead (plan §4.3). |
| Discover permits (search, listing) | **No** | No public search; the developer must know its `documentId`. |
| Keep data current | **Polling only** | No change feed; re-fetch on demand or daily for linked projects. |

## 5. Risks and constraints

- **Undocumented interface.** The DWR endpoint is an internal remoting call of a municipal application;
  it can change or be closed without notice. Keep the import behind a feature flag, store the raw
  payload per fetch for reprocessing, and fail soft.
- **Terms of use.** None published. The data is public-information by Georgian law, but the site is not
  built for automated access: one fetch per user action, cache results, identify the client in the
  User-Agent, no crawling, no bulk enumeration of ids.
- **Personal data.** The record includes personal numbers, phones and emails of the applicant, the
  architect, experts and the handling official. The extractor removes these by label; the raw payload
  must never be stored outside a short-lived processing step. The decision text also names people.
- **Inconsistent identifiers.** The parcel in `mapInfos` (01.72.16.097.088) differs from the cadastral
  code quoted in the decision text (72.16.21.437) and from codes on the general plan: parcels are
  re-registered over a project's life. Store all and let the reviewer pick the current one.
- **Third host for signed files** (`esign.tbilisi.gov.ge`) and image-only letters.
- **Georgian-only labels.** Labels are stable field definitions (`fieldsetPojos`), so a one-time
  Georgian → internal field mapping table is enough; do not rely on machine translation at runtime.

## 6. Proposed epic E10 — Regulatory import (after Phase 2)

1. (M) `regulatory` module: `fetch_permit(doc_id)` port of the prototype into the backend (httpx, same
   DWR parser), raw payload stored in object storage with 24 h retention, normalised record stored on
   `projects.regulatory_source` and a `regulatory_permits` table (document id, numbers, dates, status,
   nomenclature, parcel(s), indicators JSON, attachment manifest).
2. (M) Project bootstrap wizard: paste a permit id → preview → create project + building + floors from
   levels found on the plan sheets → import latest attachments as documents (kind by fieldset).
3. (S) Field mapping table (Georgian label → internal key) with tests on the sample record.
4. (M) Plan-sheet pre-scan job (port of `scan_plans.py`): page kinds, apartment labels and areas as
   reviewer hints in the mapping editor.
5. (S) Re-check job: daily refresh for linked projects, diff of status/decision/attachments, notification.

Estimated L–XL in total; depends on Phase 2 (documents, mapping) being in place.
