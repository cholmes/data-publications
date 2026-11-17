// Browser check of the hosted display package, written as the evidence scripts/source_publish/validate_hosted.py reads.
//
//   node hosted_browser_check.mjs prepare --plan IMMUTABLE_PLAN --out NEW_DIR
//   node hosted_browser_check.mjs run --plan IMMUTABLE_PLAN --controls DIR/browser-controls.json \
//        --config DIR/viewer-config.json --modules NODE_MODULES --out NEW_DIR
//
// prepare writes the viewer configuration (the views and the hosted style addresses) and the frozen browser cases,
// bound to the upload plan by its SHA-256. It reads nothing from the network. Commit both before running.
//
// run serves only a small page and the map libraries from loopback. Styles and tiles come from Source Cooperative.
// For each case it opens a fresh page, draws the layer with the package's own hosted style, lights the outline under
// the first drawn name, and records every request to a planned object: its Range, status, Content-Range, lengths,
// media type, CORS headers and the SHA-256 of the bytes the browser received. A case passes when enough outlines and
// at least one name are drawn, the outline under the name is lit and named, every tile request is a 206 range
// answer consistent with the plan, and the page raised no error.
//
// What it does not do: read the GeoParquet in the browser (the validator's subset query covers those files), or
// check anything about the accuracy of the boundaries. Style files are fetched whole (they are 2 KB) and are listed
// under style_requests, apart from the range requests. Glyphs come from the style's own glyph host.
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {extname, join, normalize, resolve} from 'node:path';

const [mode,...rest]=process.argv.slice(2);
const args=Object.fromEntries(rest.reduce((pairs,value,index,all)=>value.startsWith('--')?[...pairs,[value.slice(2),all[index+1]]]:pairs,[]));
const fail=message=>{console.error(message);process.exit(2);};
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const canonical=value=>JSON.stringify(sortKeys(value),null,2)+'\n';
function sortKeys(value){return Array.isArray(value)?value.map(sortKeys):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,sortKeys(value[key])])):value;}

const DATASET='us-census-places',ORIGIN='https://data.source.coop',OWNER='nthh',CASE_LIMIT=128*1024*1024,TOTAL_LIMIT=1024*1024*1024;
// layer id of the display asset, tile layer, view name, [west, south, east, north] to fit, least outlines drawn
const VIEWS=[['census-counties','census_counties','colorado',[-109.06,36.99,-102.04,41.0],40],
 ['census-places','census_places','franklin-county-oh',[-83.26,39.81,-82.77,40.16],10],
 ['census-towns','census_towns','franklin-county-oh',[-83.26,39.81,-82.77,40.16],5]];

for(const name of ['plan','out'])if(!args[name])fail(`missing --${name}`);
if(existsSync(args.out))fail('Use a new output directory; earlier results are kept.');
const planBytes=readFileSync(args.plan),plan=JSON.parse(planBytes),planSha=sha(planBytes);
const product=plan.products.find(item=>item.dataset_id===DATASET);
if(!product)fail('the plan has no us-census-places product');
const display=product.display_publication,release=product.release;
const files=plan.files.filter(item=>item.object_key.startsWith(`${DATASET}/`)&&!item.mutable);
const objects=Object.fromEntries(files.map(item=>[`${ORIGIN}/${OWNER}/${item.object_key}`,{size_bytes:item.size_bytes,sha256:item.sha256,content_type:item.content_type}]));
const assetUrl=id=>{const asset=display.assets.find(item=>item.id===id);return asset&&`${ORIGIN}/${OWNER}/${DATASET}/${asset.href}`;};
const styleUrl=id=>{const asset=display.assets.find(item=>item.id===id);return asset&&`${ORIGIN}/${OWNER}/${DATASET}/${asset.style_href}`;};
const prefixes=[`${DATASET}/releases/${release}/`,`${DATASET}/display/${display.release}/`];

if(mode==='prepare'){
 const config={schema_version:1,object_origin:ORIGIN,dataset_id:DATASET,release,display_release:display.release,viewport:{width:1440,height:900},
  views:VIEWS.map(([layer_id,source_layer,name,bounds,least])=>({layer_id,source_layer,name,bounds,least_outlines:least,style_url:styleUrl(layer_id),display_object_url:assetUrl(layer_id)}))};
 if(config.views.some(view=>!objects[view.style_url]||!objects[view.display_object_url]))fail('a view names an object outside the plan');
 const configBytes=canonical(config);
 const controls={schema_version:1,object_origin:ORIGIN,plan_sha256:planSha,viewer_config_sha256:sha(configBytes),objects,
  products:[{dataset_id:DATASET,product_id:DATASET,release,display_release:display.release,planned_object_prefixes:prefixes,planned_object_url_prefixes:prefixes.map(prefix=>`${ORIGIN}/${OWNER}/${prefix}`),catalog_url:`https://source.coop/${OWNER}/${DATASET}`}],
  cases:config.views.map(view=>({id:`${DATASET}-${view.layer_id}-${view.name}`,dataset_id:DATASET,layer_id:view.layer_id,view:{name:view.name,bounds:view.bounds}}))};
 mkdirSync(args.out,{recursive:true});
 writeFileSync(join(args.out,'viewer-config.json'),configBytes);
 const controlBytes=canonical(controls);writeFileSync(join(args.out,'browser-controls.json'),controlBytes);
 console.log(JSON.stringify({cases:controls.cases.length,viewer_config_sha256:controls.viewer_config_sha256,browser_controls_sha256:sha(controlBytes)}));
 process.exit(0);
}
if(mode!=='run')fail('first argument must be prepare or run');
for(const name of ['controls','config','modules'])if(!args[name])fail(`missing --${name}`);
const controlBytes=readFileSync(args.controls),controls=JSON.parse(controlBytes),controlsSha=sha(controlBytes);
const configBytes=readFileSync(args.config),config=JSON.parse(configBytes);
if(controls.plan_sha256!==planSha||controls.viewer_config_sha256!==sha(configBytes))fail('controls are not bound to this plan and viewer configuration');
const modules=resolve(args.modules),{chromium}=createRequire(join(modules,'x.js'))('playwright-core');
const PAGE=`<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/modules/maplibre-gl/dist/maplibre-gl.css">
<style>html,body,#map{margin:0;height:100%;background:#10140f}</style><div id="map"></div>
<script src="/modules/maplibre-gl/dist/maplibre-gl.js"></script><script src="/modules/pmtiles/dist/pmtiles.js"></script>
<script>maplibregl.addProtocol('pmtiles',new pmtiles.Protocol().tile);
window.draw=async(styleUrl,layer,bounds)=>{
 const style=await (await fetch(styleUrl)).json();
 for(const source of Object.values(style.sources))source.url='pmtiles://'+new URL(source.url,styleUrl).href;
 const map=new maplibregl.Map({container:'map',style,bounds,fitBoundsOptions:{padding:24},attributionControl:false,preserveDrawingBuffer:true});
 await new Promise(done=>map.once('idle',done));
 const drawn=new Set(map.queryRenderedFeatures({layers:[layer+'-fill']}).map(f=>f.id)).size;
 const names=map.queryRenderedFeatures({layers:[layer+'-label']}),at=names[0]&&map.project(names[0].geometry.coordinates);
 const under=at&&map.queryRenderedFeatures([at.x,at.y],{layers:[layer+'-fill']})[0];
 let lit=null;
 if(under){map.setFeatureState({source:'data',sourceLayer:layer,id:under.id},{lit:true});lit=map.getFeatureState({source:'data',sourceLayer:layer,id:under.id}).lit===true;await new Promise(done=>map.once('idle',done));}
 return {zoom:map.getZoom(),drawn,labels:names.length,under:under?{id:under.id,name:under.properties.name,kind:under.properties.kind}:null,lit,source_urls:Object.values(style.sources).map(source=>source.url)};
};</script>`;
const TYPES={'.js':'text/javascript','.css':'text/css'};
const server=createServer((request,response)=>{
 const path=decodeURIComponent(new URL(request.url,'http://x').pathname);
 if(path==='/'){response.writeHead(200,{'content-type':'text/html'});response.end(PAGE);return;}
 const [,root,...parts]=path.split('/'),file=root==='modules'&&normalize(join(modules,...parts));
 if(!file||!file.startsWith(modules)||!existsSync(file)||!statSync(file).isFile()){response.writeHead(404);response.end();return;}
 response.writeHead(200,{'content-type':TYPES[extname(file)]||'application/octet-stream'});createReadStream(file).pipe(response);
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const uiOrigin=`http://127.0.0.1:${server.address().port}`;
mkdirSync(args.out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true}),cases=[],screenshots=[],styleRequests=[],otherHosts=new Set();
for(const frozen of controls.cases){
 const view=config.views.find(item=>item.layer_id===frozen.layer_id&&item.name===frozen.view.name);
 const page=await browser.newPage({viewport:config.viewport}),errors=[],pending=[];
 page.on('pageerror',error=>errors.push(String(error)));
 page.on('response',response=>{
  const url=response.url();
  if(url.startsWith(uiOrigin))return;
  if(!url.startsWith(`${ORIGIN}/${OWNER}/${DATASET}/`)){otherHosts.add(new URL(url).host);return;}
  if(response.request().method()!=='GET')return;
  pending.push((async()=>{
   const range=response.request().headers().range||null,headers=response.headers();let body=null;
   try{body=await response.body();}catch(error){errors.push(`no body for ${url}: ${error}`);}
   return {url,range,status:response.status(),content_range:headers['content-range']||null,content_length:headers['content-length']===undefined?null:Number(headers['content-length']),
    body_bytes:body?body.length:null,body_sha256:body?sha(body):null,content_type:headers['content-type']||null,cors:headers['access-control-allow-origin']||null,
    expose_headers:headers['access-control-expose-headers']||null,planned_sha256:objects[url]?.sha256||null};
  })());
 });
 await page.goto(uiOrigin);
 let result=null;
 try{result=await page.evaluate(([style,layer,bounds])=>window.draw(style,layer,bounds),[view.style_url,view.source_layer,view.bounds]);}catch(error){errors.push(String(error));}
 const shot=`${frozen.id}.png`;await page.screenshot({path:join(args.out,shot)});screenshots.push(shot);
 const records=await Promise.all(pending);await page.close();
 const ranged=[],blocked=[];
 for(const record of records){
  if(record.url===view.style_url&&!record.range){styleRequests.push({case_id:frozen.id,...record,status_check:record.status===200&&record.body_sha256===record.planned_sha256?'passed':'failed'});continue;}
  const size=objects[record.url]?.size_bytes,match=/^bytes=(\d+)-(\d+)$/.exec(record.range||''),length=match?Number(match[2])-Number(match[1])+1:null;
  const good=Boolean(match)&&size!==undefined&&record.status===206&&record.content_range===`bytes ${match[1]}-${match[2]}/${size}`&&record.content_length===length&&record.body_bytes===length;
  ranged.push({...record,status_check:good?'passed':'failed'});
 }
 const transferred=ranged.reduce((sum,record)=>sum+(record.body_bytes||0),0);
 const drew=Boolean(result)&&result.drawn>=view.least_outlines&&result.labels>0&&Boolean(result.under?.name)&&result.lit===true;
 const asked=ranged.some(record=>record.url===view.display_object_url);
 cases.push({id:frozen.id,dataset_id:DATASET,layer_id:frozen.layer_id,view:frozen.view,
  status:drew&&asked&&!errors.length&&ranged.length>0&&ranged.every(record=>record.status_check==='passed')&&transferred<=CASE_LIMIT?'passed':'failed',
  display_object_url:view.display_object_url,display_sha256:objects[view.display_object_url].sha256,least_outlines:view.least_outlines,render:result,
  requests:ranged,transferred_bytes:transferred,errors,blocked_requests:blocked});
}
await browser.close();server.close();
const total=cases.reduce((sum,item)=>sum+item.transferred_bytes,0),tested=[...new Set(cases.flatMap(item=>item.requests.map(record=>record.url)))].sort();
const passed=cases.every(item=>item.status==='passed')&&styleRequests.every(item=>item.status_check==='passed')&&total<=TOTAL_LIMIT;
const build=sha(readFileSync(new URL(import.meta.url)));
const evidence={schema_version:1,dataset_id:DATASET,selected_dataset_id:DATASET,product_id:DATASET,release,display_release:display.release,status:passed?'passed':'failed',
 plan_sha256:planSha,browser_cases_sha256:controlsSha,viewer_config_sha256:controls.viewer_config_sha256,viewer_build_sha256:build,
 viewer_build:'SHA-256 of hosted_browser_check.mjs, which holds the page; map libraries come from the node_modules given',
 checked_at:new Date().toISOString(),ui_origin:uiOrigin,case_ids:cases.map(item=>item.id),expected_case_count:controls.cases.length,
 tested_object_urls:tested,screenshots,planned_object_prefixes:prefixes,planned_object_url_prefixes:prefixes.map(prefix=>`${ORIGIN}/${OWNER}/${prefix}`),
 transfer_ceiling_bytes_per_case:CASE_LIMIT,transfer_ceiling_bytes_total:TOTAL_LIMIT,total_transferred_bytes:total,
 cases,style_requests:styleRequests,other_hosts_contacted:[...otherHosts].sort(),blocked_requests:[],errors:cases.flatMap(item=>item.errors)};
writeFileSync(join(args.out,'hosted-browser-evidence.json'),JSON.stringify(evidence,null,2)+'\n');
console.log(JSON.stringify({status:evidence.status,total_transferred_bytes:total,cases:cases.map(item=>({id:item.id,status:item.status,drawn:item.render?.drawn,labels:item.render?.labels,under:item.render?.under,requests:item.requests.length,bytes:item.transferred_bytes,errors:item.errors}))},null,2));
process.exit(passed?0:1);
