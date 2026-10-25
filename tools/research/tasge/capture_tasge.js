// Playwright capture script for a tas.ge public permit page.
// Usage (from a machine/session that can reach tas.ge):
//   node capture_tasge.js 1127975 [outDir]
// Produces: page.png, rendered.html, network.json, dom_inventory.json, documents.json
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const docId = process.argv[2] || '1127975';
  const out = process.argv[3] || path.join(__dirname, 'capture_' + docId);
  fs.mkdirSync(out, { recursive: true });
  const url = `https://tas.ge/?p=publicpage&documentId=${docId}`;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const net = [];
  page.on('request', r => { if (['xhr', 'fetch'].includes(r.resourceType())) net.push({ url: r.url(), method: r.method(), postData: r.postData(), type: r.resourceType() }); });
  page.on('response', async r => {
    const e = net.find(x => x.url === r.url() && !x.status);
    if (!e) return;
    e.status = r.status(); e.contentType = r.headers()['content-type'] || '';
    e.isJson = /json/i.test(e.contentType);
    if (e.isJson) { try { e.sample = (await r.text()).slice(0, 4000); } catch {} }
  });
  const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
  fs.writeFileSync(path.join(out, 'main_response.json'), JSON.stringify({ status: resp && resp.status(), headers: resp && resp.headers() }, null, 2));
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(out, 'page.png'), fullPage: true });
  fs.writeFileSync(path.join(out, 'rendered.html'), await page.content());
  fs.writeFileSync(path.join(out, 'network.json'), JSON.stringify(net, null, 2));
  const inventory = await page.evaluate(() => {
    const txt = e => (e.textContent || '').replace(/\s+/g, ' ').trim();
    const headings = [...document.querySelectorAll('h1,h2,h3,h4,legend,.panel-title,.card-header')].map(txt).filter(Boolean);
    const pairs = [];
    document.querySelectorAll('tr').forEach(tr => { const c = tr.querySelectorAll('th,td'); if (c.length === 2) pairs.push({ label: txt(c[0]), value: txt(c[1]) }); });
    document.querySelectorAll('dt').forEach(dt => pairs.push({ label: txt(dt), value: txt(dt.nextElementSibling) }));
    document.querySelectorAll('label').forEach(l => { const v = l.nextElementSibling; if (v) pairs.push({ label: txt(l), value: txt(v) }); });
    const tables = [...document.querySelectorAll('table')].map(t => ({ headers: [...t.querySelectorAll('th')].map(txt), rows: [...t.querySelectorAll('tbody tr')].slice(0, 50).map(tr => [...tr.querySelectorAll('td')].map(txt)) }));
    const docs = [...document.querySelectorAll('a[href]')].map(a => ({ text: txt(a), href: a.href })).filter(a => /download|file|attach|\.pdf|\.dwg|\.zip|\.doc|\.jpg|documentId|fileId/i.test(a.href + a.text));
    return { title: document.title, lang: document.documentElement.lang, charset: document.characterSet, headings, pairs, tables, docs };
  });
  fs.writeFileSync(path.join(out, 'dom_inventory.json'), JSON.stringify(inventory, null, 2));
  fs.writeFileSync(path.join(out, 'documents.json'), JSON.stringify(inventory.docs, null, 2));
  console.log('saved to', out, '| xhr/fetch calls:', net.length, '| pairs:', inventory.pairs.length, '| docs:', inventory.docs.length);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
