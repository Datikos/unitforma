// Playwright capture of the rendered permit page (the ExtJS app on docs.tbilisi.gov.ge).
// Usage: node capture_tasge.js <docId> [outDir]   → page.png, rendered.html, network.json (DWR calls with bodies), fields.json
// Normally not needed: extract_permit.py replays the data call directly. Use this when the page changes.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const docId = process.argv[2] || '1127975';
  const out = process.argv[3] || path.join(__dirname, 'capture_' + docId);
  fs.mkdirSync(out, { recursive: true });
  const url = `https://docs.tbilisi.gov.ge/architect/public.html?docId=${docId}`;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1200 } });
  const net = [];
  page.on('response', async r => {
    const req = r.request();
    if (!['xhr', 'fetch'].includes(req.resourceType())) return;
    const e = { url: r.url(), method: req.method(), status: r.status(), contentType: r.headers()['content-type'] || '' };
    if (r.url().includes('.dwr')) { e.postData = req.postData(); try { e.body = await r.text(); } catch {} }
    net.push(e);
  });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 120000 });
  await page.waitForTimeout(8000);
  await page.screenshot({ path: path.join(out, 'page.png'), fullPage: true });
  fs.writeFileSync(path.join(out, 'rendered.html'), await page.content());
  fs.writeFileSync(path.join(out, 'network.json'), JSON.stringify(net, null, 2));
  const fields = await page.evaluate(() => {
    const txt = e => (e ? (e.textContent || '').replace(/\s+/g, ' ').trim() : '');
    const res = [];
    document.querySelectorAll('.x-form-item, .x-field').forEach(item => {
      const label = txt(item.querySelector('.x-form-item-label, label'));
      const inp = item.querySelector('input:not([type=hidden]), textarea, select, .x-form-display-field');
      let value = '';
      if (inp) value = inp.tagName === 'DIV' ? txt(inp) : (inp.type === 'checkbox' ? String(inp.checked) : inp.value);
      const links = [...item.querySelectorAll('a[href]')].map(a => a.href);
      if (label || value || links.length) res.push({ label, value, links });
    });
    return res;
  });
  fs.writeFileSync(path.join(out, 'fields.json'), JSON.stringify(fields, null, 2));
  console.log(`saved to ${out} | dwr calls: ${net.filter(e => e.url.includes('.dwr')).length} | fields: ${fields.length}`);
  await browser.close();
})();
