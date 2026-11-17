// Check 9 of display-plan.md: draw the display package in a browser from loopback, with range requests.
//
//   node browser_check.mjs --display DIR --modules NODE_MODULES --report NEW_FILE
//
// NODE_MODULES must hold playwright-core, maplibre-gl and pmtiles (any checkout that has them). Serves DIR with
// byte ranges and CORS on a loopback port, opens a page that draws each layer with the package's own style, and
// records: features drawn for a whole state and a whole county, the name read from the outline under the first
// drawn label after lighting it, page errors, and every request for the archive (all must be ranges).
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {createReadStream, existsSync, readFileSync, statSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {extname, join, normalize, resolve} from 'node:path';

const args=Object.fromEntries(process.argv.slice(2).reduce((pairs,value,index,all)=>value.startsWith('--')?[...pairs,[value.slice(2),all[index+1]]]:pairs,[]));
for(const name of ['display','modules','report'])if(!args[name]){console.error(`missing --${name}`);process.exit(2);}
if(existsSync(args.report)){console.error('Use a new report path; earlier reports are kept.');process.exit(2);}
const display=resolve(args.display),modules=resolve(args.modules);
const {chromium}=createRequire(join(modules,'x.js'))('playwright-core');
const TYPES={'.json':'application/json','.pmtiles':'application/vnd.pmtiles','.js':'text/javascript','.css':'text/css','.html':'text/html'};
// name, style, layer, [west, south, east, north] to fit, least features that must be drawn
const VIEWS=[['Colorado, counties','census_counties','census_counties',[-109.06,36.99,-102.04,41.0],40],
 ['Franklin County OH, places','census_places','census_places',[-83.26,39.81,-82.77,40.16],10],
 ['Franklin County OH, townships','census_towns','census_towns',[-83.26,39.81,-82.77,40.16],5]];
const PAGE=`<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/modules/maplibre-gl/dist/maplibre-gl.css">
<style>html,body,#map{margin:0;height:100%;background:#10140f}</style><div id="map"></div>
<script src="/modules/maplibre-gl/dist/maplibre-gl.js"></script><script src="/modules/pmtiles/dist/pmtiles.js"></script>
<script>maplibregl.addProtocol('pmtiles',new pmtiles.Protocol().tile);
window.draw=async(styleName,layer,bounds)=>{
 const address=new URL('/display/styles/'+styleName+'.json',location.href),style=await (await fetch(address)).json();
 for(const source of Object.values(style.sources))source.url='pmtiles://'+new URL(source.url,address).href;
 document.getElementById('map').innerHTML='';
 const map=new maplibregl.Map({container:'map',style,bounds,fitBoundsOptions:{padding:24},attributionControl:false});
 await new Promise(done=>map.once('idle',done));
 const middle=[map.getCanvas().clientWidth/2,map.getCanvas().clientHeight/2];
 style.layers.unshift({id:layer+'-fill',type:'fill',source:'data','source-layer':layer,paint:{'fill-color':'#f3d27a','fill-opacity':['case',['boolean',['feature-state','lit'],false],0.3,0.001]}});
 map.addLayer(style.layers[0]);await new Promise(done=>map.once('idle',done));
 const drawn=new Set(map.queryRenderedFeatures({layers:[layer+'-fill']}).map(f=>f.id)).size;
 const labels=map.queryRenderedFeatures({layers:[layer+'-label']}).length;
 // The pointer goes where the first drawn name is, since the middle of a county can be a city outside any township.
 const named=map.queryRenderedFeatures({layers:[layer+'-label']})[0],at=named?map.project(named.geometry.coordinates):middle;
 const under=map.queryRenderedFeatures([at.x??at[0],at.y??at[1]],{layers:[layer+'-fill']})[0];
 let lit=null;
 if(under){map.setFeatureState({source:'data',sourceLayer:layer,id:under.id},{lit:true});lit=map.getFeatureState({source:'data',sourceLayer:layer,id:under.id}).lit===true;}
 return {zoom:map.getZoom(),drawn,labels,under:under?{id:under.id,name:under.properties.name,kind:under.properties.kind}:null,lit};
};</script>`;

const requests=[];
const server=createServer((request,response)=>{
 const path=decodeURIComponent(new URL(request.url,'http://x').pathname);
 if(path==='/'){response.writeHead(200,{'content-type':'text/html'});response.end(PAGE);return;}
 const [,root,...rest]=path.split('/'),base=root==='display'?display:root==='modules'?modules:null,file=base&&normalize(join(base,...rest));
 if(!file||!file.startsWith(base)||!existsSync(file)||!statSync(file).isFile()){response.writeHead(404);response.end();return;}
 const size=statSync(file).size,range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||''),head={'content-type':TYPES[extname(file)]||'application/octet-stream','access-control-allow-origin':'*','accept-ranges':'bytes'};
 if(file.endsWith('.pmtiles'))requests.push({range:request.headers.range||null});
 if(range){const start=Number(range[1]),end=Math.min(size-1,range[2]?Number(range[2]):size-1);response.writeHead(206,{...head,'content-range':`bytes ${start}-${end}/${size}`,'content-length':end-start+1});createReadStream(file,{start,end}).pipe(response);}
 else{response.writeHead(200,{...head,'content-length':size});createReadStream(file).pipe(response);}
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({channel:'chrome',headless:true}),page=await browser.newPage({viewport:{width:1440,height:900}});
const errors=[];page.on('pageerror',error=>errors.push(String(error)));
await page.goto(origin);
const views=[];
for(const [name,style,layer,bounds,least] of VIEWS){
 const result=await page.evaluate(([s,l,b])=>window.draw(s,l,b),[style,layer,bounds]);
 views.push({name,layer,least,...result,passed:result.drawn>=least&&result.labels>0&&Boolean(result.under?.name)&&result.lit===true});
}
await browser.close();server.close();
const archive=join(display,'assets','outlines.pmtiles'),whole=requests.filter(r=>!r.range).length;
const report={schema_version:1,archive_sha256:createHash('sha256').update(readFileSync(archive)).digest('hex'),served_from:'loopback',
 views,page_errors:errors,archive_requests:requests.length,archive_requests_without_range:whole,
 status:views.every(v=>v.passed)&&!errors.length&&requests.length>0&&whole===0?'passed':'failed'};
writeFileSync(args.report,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
process.exit(report.status==='passed'?0:1);
