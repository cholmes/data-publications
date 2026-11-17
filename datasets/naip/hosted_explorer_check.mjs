// Check 7 of research/naip-index-20261117/hosting-criteria.md: the production explorer reads the hosted index.
//
//   node hosted_explorer_check.mjs --modules NODE_MODULES --out NEW_FILE [--size BYTES]
//
// NODE_MODULES must hold playwright-core. Opens the explorer at Alta, Utah, reading in the browser, and records
// every request to stac/naip.parquet (each must carry a Range header) and to quad COGs under nthh/naip/, and
// page errors. Passes when the index was read only with ranges, at least one quad COG was requested, and the
// page reported no error.
import {existsSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join, resolve} from 'node:path';

const args=Object.fromEntries(process.argv.slice(2).reduce((pairs,value,index,all)=>value.startsWith('--')?[...pairs,[value.slice(2),all[index+1]]]:pairs,[]));
for(const name of ['modules','out'])if(!args[name]){console.error(`missing --${name}`);process.exit(2);}
if(existsSync(args.out)){console.error('Use a new output path; earlier results are kept.');process.exit(2);}
const {chromium}=createRequire(join(resolve(args.modules),'x.js'))('playwright-core');
const PAGE='https://experiments.folia.sh/stac-geoparquet/?lng=-111.64&lat=40.59&zoom=14&execution=browser';
// The explorer reads through its range cache, which passes requests on to data.source.coop.
const HOSTS=['https://data.source.coop','https://naip-range-cache.me-521.workers.dev'];
const isIndex=url=>HOSTS.some(host=>url===host+'/nthh/naip/stac/naip.parquet');
const QUAD=/^https:\/\/(data\.source\.coop|naip-range-cache\.me-521\.workers\.dev)\/nthh\/naip\/[a-z]{2}\/\d{4}\/\d+cm\/rgb\/.+\.tif$/;
const SIZE=Number(args.size||44289015);   // the hosted quad index's size, which the cache must report

const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}});
const index=[],quads=[],errors=[];
page.on('pageerror',error=>errors.push(String(error)));
page.on('request',request=>{
 const url=request.url(),range=request.headers().range||null;
 if(isIndex(url))index.push({method:request.method(),range});
 else if(QUAD.test(url))quads.push({url,range});
});
const responses=[];
page.on('response',response=>{if(isIndex(response.url()))responses.push(response.status());});
await page.goto(PAGE,{waitUntil:'load',timeout:120000});
for(let waited=0;waited<60000&&!quads.length;waited+=1000)await page.waitForTimeout(1000);
await page.waitForTimeout(3000);
await browser.close();
// The cache must serve the new bytes: the same ranges read through it and from data.source.coop.
const {createHash}=await import('node:crypto');
const cacheRanges=[];
for(const range of ['-131072','0-65535','20000000-20065535']){
 const read=async host=>{const r=await fetch(host+'/nthh/naip/stac/naip.parquet',{headers:{Range:'bytes='+range}});return {status:r.status,contentRange:r.headers.get('content-range'),sha256:createHash('sha256').update(Buffer.from(await r.arrayBuffer())).digest('hex')};};
 const [source,cache]=[await read(HOSTS[0]),await read(HOSTS[1])];
 cacheRanges.push({range,source,cache,passed:source.status===206&&cache.status===206&&source.sha256===cache.sha256&&String(cache.contentRange).endsWith('/'+SIZE)});
}
const ranged=index.filter(r=>r.method==='GET').every(r=>r.range);
const report={schema_version:1,page:PAGE,index_requests:index,index_response_statuses:responses,
 quad_requests:quads.length,first_quads:quads.slice(0,5).map(q=>q.url),page_errors:errors,
 cache_ranges:cacheRanges,
 status:index.length>0&&ranged&&quads.length>0&&!errors.length&&cacheRanges.every(r=>r.passed)?'passed':'failed'};
writeFileSync(args.out,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({index_requests:index.length,ranged,quads:quads.length,errors:errors.length,status:report.status}));
process.exit(report.status==='passed'?0:1);
