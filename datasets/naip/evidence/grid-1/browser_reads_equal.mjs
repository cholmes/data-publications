// As browser_reads.mjs, but with every layout given the same overview depth: quads and
// tiles get a separate overview file (4.8 m per pixel and coarser) drawn below zoom 13.6.
// The "switch" view sits just above that zoom, the worst case for the full-resolution files.
//   OUT=<dir for screenshots> node <this file, copied into the experiment dir> > browser-reads-equal.jsonl
import { chromium } from 'playwright-core';
const P = 'https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1/';
const OV = '&switch=13.6&overview=' + P + 'overview/utm12_e400_n4400-ov3.tif';
const LAYOUTS = [['quads', '&host=s3'], ['quads+overview', '&host=s3' + OV], ['tiles+overview', '&url=' + P + 'index/tiles-stac.parquet' + OV],
  ['square', '&url=' + P + 'index/square2-stac.parquet']];
const VIEWS = [['street', -111.80, 40.60, 17], ['switch', -111.64, 40.59, 13.6], ['canyon', -111.64, 40.59, 12], ['region', -111.59, 40.20, 11]];
const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
for (const [view, lng, lat, zoom] of VIEWS) for (const [layout, extra] of LAYOUTS) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:18561/naip-deck.html?year=2024&lng=${lng}&lat=${lat}&zoom=${zoom}${extra}`);
  const row = { view, layout };
  try {
    await page.waitForFunction(() => window.naipDeck?.state === 'ready' || window.naipDeck?.state === 'failed', null, { timeout: 180000 });
    await page.waitForFunction(() => performance.now() - window.naipNet.lastMs > 3000, null, { timeout: 180000 });
  } catch (e) { row.timeout = true; }
  Object.assign(row, await page.evaluate(() => ({ state: naipDeck.state, files_in_view: naipDeck.scenes, drawn: naipDeck.loaded,
    index_requests: naipIndexNet.requests, index_bytes: naipIndexNet.bytes, last_image_ms: Math.round(naipNet.lastMs),
    image_requests: naipNet.requests, image_bytes: naipNet.bytes, files_touched: naipNet.files.size, errors: naipDeck.errors.slice(0, 3) })));
  await page.screenshot({ path: `${process.env.OUT}/equal-${view}-${layout}.png` });
  console.log(JSON.stringify(row));
  await context.close();
}
await browser.close();
