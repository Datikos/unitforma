# tas.ge permit-page capture (research tool)

`tas.ge` is the public permit portal of the Tbilisi Municipality Architecture Service. A permit page
such as `https://tas.ge/?p=publicpage&documentId=1127975` holds the regulator's view of a project:
applicant, address, cadastral code, permit decisions and the attached architectural documents.

`capture_tasge.js` renders one permit page with Playwright and saves, next to the script:
screenshot, rendered HTML, the list of XHR/fetch calls with JSON samples (to discover any data
endpoint), label/value pairs, tables, and attachment links (name, extension, URL pattern).

```bash
cd tools/research/tasge
npm init -y >/dev/null && npm install playwright && npx playwright install chromium
node capture_tasge.js 1127975
```

The output feeds the feasibility assessment in `docs/research/regulatory-permit-data.md`.
Respect the site's terms and rate limits; this is a one-page research capture, not a crawler.
