// Mark 4 of research/catalog-presentation-20261117/criteria.md: Portolan draws the NAIP map layer.
//
//   node portolan_map_check.mjs --modules NODE_MODULES --browser URL --catalog URL --out NEW_DIR
//
// Opens BROWSER#/external/<CATALOG host and path>/naip/collection.json in headless Chrome, records
// every request to overviews/national-latest.tif (each GET must carry a Range header), page errors,
// and a screenshot for inspection. Passes when the file was read only with ranges, at least once,
// with 206 answers, and no page error names it.
import {existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join, resolve} from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, all) =>
  value.startsWith('--') ? [...pairs, [value.slice(2), all[index + 1]]] : pairs, []));
for (const name of ['modules', 'browser', 'catalog', 'out']) if (!args[name]) { console.error(`missing --${name}`); process.exit(2); }
if (existsSync(args.out)) { console.error('Use a new output path; earlier results are kept.'); process.exit(2); }
mkdirSync(args.out, {recursive: true});
const {chromium} = createRequire(join(resolve(args.modules), 'x.js'))('playwright-core');
const FILE = 'https://data.source.coop/nthh/naip/overviews/national-latest.tif';
const page_url = `${args.browser}#/external/${args.catalog.replace('://', ':/')}/naip/collection.json`;

const browser = await chromium.launch({channel: 'chrome', headless: true});
const page = await browser.newPage({viewport: {width: 1280, height: 900}});
const requests = [], errors = [];
page.on('pageerror', error => errors.push(String(error)));
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
page.on('request', request => { if (request.url() === FILE) requests.push({method: request.method(), range: request.headers().range || null}); });
const statuses = [];
page.on('response', response => { if (response.url() === FILE) statuses.push(response.status()); });
await page.goto(page_url, {waitUntil: 'load', timeout: 120000});
for (let waited = 0; waited < 60000 && !statuses.length; waited += 1000) await page.waitForTimeout(1000);
await page.waitForTimeout(8000);
await page.screenshot({path: join(args.out, 'naip-page.png')});
await browser.close();
const gets = requests.filter(r => r.method === 'GET');
const fileErrors = errors.filter(e => e.includes('national-latest'));
const report = {schema_version: 1, page: page_url, file: FILE, requests, response_statuses: statuses,
  page_errors: errors, status: gets.length > 0 && gets.every(r => r.range) && statuses.length > 0
    && statuses.every(s => s === 206) && !fileErrors.length ? 'rendered_pending_visual_review' : 'failed'};
writeFileSync(join(args.out, 'report.json'), JSON.stringify(report, null, 1) + '\n');
console.log(JSON.stringify({gets: gets.length, statuses: [...new Set(statuses)], errors: errors.length, status: report.status}));
process.exit(report.status === 'failed' ? 1 : 0);
