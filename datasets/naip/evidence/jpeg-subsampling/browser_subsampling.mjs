// Draw the full-colour (4:4:4) and halved-colour (4:2:0) test COGs in the deck.gl demo page,
// each as a single file, at street and canyon zoom; record errors and save screenshots.
//   cd <experiment dir with playwright-core> && node <this file> <out dir> > browser-subsampling.jsonl
// Needs the demo's dev server on 127.0.0.1:18561.
import { chromium } from 'playwright-core';
const P = 'https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1/subsampling/';
const out = process.argv[2];
const CASES = [['zion', -112.95, 37.25], ['nhkanc', -71.40, 44.00]];
const browser = await chromium.launch({ headless: process.env.HEADED !== '1', args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
for (const [name, lng, lat] of CASES) for (const code of ['444', '420']) for (const zoom of [18, 13]) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:18561/naip-deck.html?lng=${lng}&lat=${lat}&zoom=${zoom}&switch=30&overview=${encodeURIComponent(P + name + '-' + code + '.tif')}`);
  const row = { name, code, zoom };
  try {
    await page.waitForFunction(() => window.naipDeck?.state === 'ready' || window.naipDeck?.state === 'failed', null, { timeout: 120000 });
    await page.waitForFunction(() => performance.now() - window.naipNet.lastMs > 3000, null, { timeout: 120000 });
  } catch (e) { row.timeout = true; }
  Object.assign(row, await page.evaluate(() => ({ state: naipDeck.state, drawn: naipDeck.loaded, image_requests: naipNet.requests,
    image_bytes: naipNet.bytes, ready_ms: Math.round(naipDeck.readyMs || 0), errors: naipDeck.errors.slice(0, 3) })));
  await page.screenshot({ path: `${out}/browser-${name}-${code}-z${zoom}.png` });
  console.log(JSON.stringify(row));
  await context.close();
}
await browser.close();
