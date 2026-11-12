// Cold browser reads of the same three views from each layout with the deck.gl demo page,
// counting image requests and bytes. A new browser context per read, so nothing is cached.
//   cd <experiment dir with playwright-core> && node <this file> > browser-reads.jsonl
// Needs the demo's dev server on 127.0.0.1:18561.
import { chromium } from 'playwright-core';
const P = 'https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1/index/';
const LAYOUTS = [['quads', '&host=s3'], ['tiles', '&url=' + P + 'tiles-stac.parquet'], ['square', '&url=' + P + 'square-stac.parquet']];
const VIEWS = [['street', -111.80, 40.60, 17], ['canyon', -111.64, 40.59, 12], ['region', -111.59, 40.20, 11]];
const browser = await chromium.launch({ headless: process.env.HEADED !== '1', args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
for (const [view, lng, lat, zoom] of VIEWS) for (const [layout, extra] of LAYOUTS) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:18561/naip-deck.html?year=2024&lng=${lng}&lat=${lat}&zoom=${zoom}${extra}`);
  const row = { view, layout };
  try {
    await page.waitForFunction(() => window.naipDeck?.state === 'ready' || window.naipDeck?.state === 'failed', null, { timeout: 180000 });
    // settled: no image request for three seconds
    await page.waitForFunction(() => performance.now() - window.naipNet.lastMs > 3000, null, { timeout: 180000 });
  } catch (e) { row.timeout = true; }
  Object.assign(row, await page.evaluate(() => ({ state: naipDeck.state, files_in_view: naipDeck.scenes, drawn: naipDeck.loaded,
    index_requests: naipDeck.catalogRequests, index_bytes: naipDeck.catalogBytes, index_ms: Math.round(naipDeck.queryMs || 0),
    ready_ms: Math.round(naipDeck.readyMs || 0), last_image_ms: Math.round(naipNet.lastMs), image_requests: naipNet.requests,
    image_bytes: naipNet.bytes, files_touched: naipNet.files.size, errors: naipDeck.errors.slice(0, 3) })));
  await page.screenshot({ path: new URL(`browser-${view}-${layout}.png`, import.meta.url).pathname });
  console.log(JSON.stringify(row));
  await context.close();
}
await browser.close();
