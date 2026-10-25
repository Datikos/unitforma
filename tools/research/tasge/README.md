# tas.ge permit research tools

Findings and feasibility: `docs/research/regulatory-permit-data.md`.

| Script | Purpose | Requirements |
|---|---|---|
| `extract_permit.py <docId>` | Fetches the permit record through the same remote call the public page uses, parses it, filters personal data, emits JSON (metadata, nomenclature, class calculator, parcels, technical indicators, fields, attachments with download URLs, decisions, signed files). `--download-dir` fetches attachments. | Python 3.11+, standard library only. Network access to `docs.tbilisi.gov.ge`. |
| `scan_plans.py <pdf>` | Page inventory of a drawing PDF: vector/text presence, page kind, apartment and parking labels, areas, level markers, scales, grid axes; optional PNG renders. | `pip install pdfplumber pypdfium2` |
| `capture_tasge.js <docId>` | Playwright capture of the rendered page (screenshot, DOM label/value pairs, XHR log). Only needed when the page structure changes. | Node 18+, `npm install playwright` |

```bash
python3 extract_permit.py 1127975 --out permit.json --download-dir ./files
python3 scan_plans.py "./files/<id>_<floor plans>.pdf" --out scan.json --render-dir ./png
```

Rules: one record per call, no enumeration of ids, keep the `User-Agent` identifying Unitforma, never
commit raw payloads or downloaded files (they contain personal data). `sample/` holds a PII-filtered
output for the reference permit.
