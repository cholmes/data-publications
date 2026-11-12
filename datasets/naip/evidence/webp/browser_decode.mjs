// Draw one COG alone in the deck.gl demo at a street view and a whole-quad view, and report
// errors, image requests, bytes and decode time per block. For the WebP pass marks.
//   OUT=<dir> node <this file, copied into the experiment dir> > browser-decode.jsonl
import { chromium } from 'playwright-core';
const P = 'https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1/webp/';
const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
for (const round of [1, 2]) for (const [view, zoom] of [['street', 17], ['quad', 12.5]]) for (const file of ['jpeg-65-65', 'jpeg-65-85', 'webp-60', 'webp-70']) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:18561/naip-deck.html?year=2024&lng=-111.655&lat=40.59&zoom=${zoom}&switch=99&overview=${P}${file}.tif`);
  const row = { round, view, file };
  try {
    await page.waitForFunction(() => window.naipDeck?.state === 'ready' || window.naipDeck?.state === 'failed', null, { timeout: 120000 });
    await page.waitForFunction(() => performance.now() - window.naipNet.lastMs > 3000, null, { timeout: 120000 });
  } catch (e) { row.timeout = true; }
  Object.assign(row, await page.evaluate(() => {
    const jobs = naipDeck.trace?.decodeJobs || [], ms = jobs.map(j => j.roundTripMs).sort((a, b) => a - b);
    return { state: naipDeck.state, errors: naipDeck.errors.slice(0, 3), image_requests: naipNet.requests, image_bytes: naipNet.bytes,
      blocks_decoded: jobs.length, decode_ms_median: ms.length ? Math.round(ms[ms.length >> 1] * 10) / 10 : null,
      decode_ms_sum: Math.round(ms.reduce((a, b) => a + b, 0)), sample: jobs[0] && Object.fromEntries(Object.entries(jobs[0]).filter(([k]) => k !== 'href')) };
  }));
  if (round === 1) await page.screenshot({ path: `${process.env.OUT}/decode-${view}-${file}.png` });
  console.log(JSON.stringify(row));
  await context.close();
}
await browser.close();
