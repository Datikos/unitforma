# Regulatory permit data as a source for project structure (Georgia, tas.ge)

**Status:** open research item (2026-10-25). The tas.ge page could not be fetched from the
planning environment (network policy), so the field inventory below is a hypothesis to confirm
with `tools/research/tasge/capture_tasge.js`.

## Why it matters
The Tbilisi Architecture Service permit record is an authoritative, dated description of a
project: cadastral parcel, address, permit type/number/status, land-use coefficients (K1/K2),
number of floors and height, total area, often the number of apartments, and the approved
architectural project as attached documents (PDF drawings, sometimes DWG, site plan, expert
reports, decisions). For Unitforma this is a natural **project bootstrap source**: a developer
pastes a permit `documentId`, and the platform pre-fills the project, buildings and floors and
pulls the drawings into the document pipeline as revision 1 with `source = regulator`.

## What is likely automatable (to confirm)
| Data | Expected form | Extraction |
|---|---|---|
| Permit metadata (applicant, address, cadastral code, dates, status) | HTML label/value pairs or a JSON XHR | Easy if JSON exists; otherwise HTML parsing with Georgian labels mapped to fields |
| Building parameters (floors, height, K1/K2, total area, units) | Same | Easy; validate numeric formats |
| Attached documents | Links to PDF/DWG | Download, hash, classify (site plan, floor plans, sections) → existing `documents` pipeline |
| Floor plans → units | PDF content | Same assisted workflow as any upload (plan §13); permits do not change the human-verification requirement |

Stable identifiers to store on `projects`: `regulator_source = tas.ge`, `regulator_document_id`,
`cadastral_code` (joinable to the national public registry, napr.gov.ge). Record the capture
timestamp and keep the raw payload for audit.

## Risks and checks
- No documented API or open-data feed was found; scraping a municipal site needs a terms-of-use
  check and polite access (one request per user action, caching, no crawling).
- Georgian-only labels and possible JS rendering: the capture script records the XHR calls so an
  undocumented JSON endpoint can be used instead of HTML parsing where it exists.
- Permit documents describe the *approved* design, which can differ from marketing material;
  keep them as a separate document kind (`permit`) and let reviewers decide what becomes the
  sales plan.

## Next step
Run the capture from a machine with internet access (or after allow-listing `tas.ge` in the
cloud environment), attach the inventory here, and decide whether to add epic **E10 Regulatory
import** to the backlog (estimated M–L once the page structure is known).
