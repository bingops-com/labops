// Browser acceptance against the real gateway and a fake authenticated Coder.
// No account credentials, production API or npm dependencies are used.
import http from 'node:http';
import { once } from 'node:events';
import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, copyFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { createGateway } from '../../apps/workloads/coder/base/dev-proxy.mjs';

const source = new URL('../../apps/workloads/coder/base/', import.meta.url);
const directory=await mkdtemp(`${tmpdir()}/coder-dashboard-`);
const artifacts=new URL('./artifacts/',import.meta.url);await mkdir(artifacts,{recursive:true});
for(const [target,origin] of [['index.html','dev-portal.html'],['dev.css','dev-portal.css'],['dev.js','dev-portal.js'],...['display','display-ext','text','text-ext'].map(name=>[`${name}.woff2`,`dev-fonts/${name}.woff2`])])await copyFile(new URL(origin,source),`${directory}/${target}`);
let mode='ready';
const projects=[{name:'rpg',ports:[4173]},{name:'portal',ports:[5173]},{name:'games',ports:[3000]},{name:'slots',ports:[]}];
const ports=projects.filter(p=>p.ports.length).map(p=>({port:p.ports[0],project:p.name,runtime:'Node.js',status:'ready',http_status:200}));
const coder=http.createServer((req,res)=>{
  if(mode==='login'){res.writeHead(303,{location:'https://coder.lab.bingo/api/v2/applications/auth-redirect'});res.end();return;}
  if(mode==='offline'){res.writeHead(503);res.end();return;}
  res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({workspace:{owner:'bingops',name:'lab',agent:'main'},checked_at:new Date().toISOString(),ports:mode==='empty'?[]:ports,projects,limited:mode==='partial'}));
});coder.listen(0,'127.0.0.1');await once(coder,'listening');
const gateway=createGateway({upstream:`http://127.0.0.1:${coder.address().port}`,portal:pathToFileURL(`${directory}/index.html`)});
gateway.prependListener('request',req=>{req.headers.host='dev.lab.bingo';});gateway.listen(0,'127.0.0.1');await once(gateway,'listening');
const browserPath=process.env.CHROMIUM_BIN||['chromium','google-chrome','chromium-browser'].map(name=>spawnSync('which',[name],{encoding:'utf8'}).stdout.trim()).find(Boolean);
if(!browserPath)throw new Error('Chromium unavailable; set CHROMIUM_BIN');
const browser=spawn(browserPath,['--headless','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-port=0',`--user-data-dir=${directory}/profile`,'about:blank'],{stdio:['ignore','ignore','pipe']});
let socket;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const until=async predicate=>{for(let i=0;i<100;i++){if(await predicate())return;await pause(80);}throw new Error('UI assertion timeout');};
try{
  const endpoint=await new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('Browser startup timeout')),15000);browser.stderr.on('data',chunk=>{output+=chunk;const match=output.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timeout);resolve(match[1]);}});browser.on('error',reject);});
  socket=new WebSocket(endpoint);await once(socket,'open');let seq=0;const pending=new Map(),errors=[];
  socket.addEventListener('message',event=>{const msg=JSON.parse(event.data);if(msg.id){const wait=pending.get(msg.id);if(wait){pending.delete(msg.id);msg.error?wait.reject(new Error(JSON.stringify(msg.error))):wait.resolve(msg.result);}}if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);if(msg.method==='Log.entryAdded'&&/Content Security Policy|violates.*directive/i.test(msg.params.entry.text))errors.push(msg.params.entry.text);});
  const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const call=(method,params)=>send(method,params,sessionId);
  const evaluate=async expression=>{const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const capture=async name=>writeFile(new URL(name,artifacts),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
  const refresh=async()=>{await click('#refresh');await until(()=>evaluate('!document.getElementById("refresh").disabled'));};
  await call('Runtime.enable');await call('Log.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:`http://127.0.0.1:${gateway.address().port}/`});
  await until(()=>evaluate('document.querySelectorAll(".port-card").length===3'));await evaluate('document.fonts.ready');
  assert.equal(await evaluate(`document.querySelector('.port-card[data-port="4173"] a').href`),'https://4173.dev.lab.bingo/');
  for(const [width,height] of [[1440,1080],[1366,768],[768,1024],[390,844],[320,740],[740,390]]){
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<=768});await pause(120);
    assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,`No overflow ${width}x${height}`);
    await capture(`dev-${width}x${height}.png`);
  }
  await evaluate(`document.getElementById('search').value='5173';document.getElementById('search').dispatchEvent(new Event('input'))`);assert.equal(await evaluate('document.querySelectorAll(".port-card").length'),1);
  await evaluate(`document.getElementById('search').value='';document.getElementById('search').dispatchEvent(new Event('input'))`);
  await click('.port-card[data-port="4173"] .star-button');await click('#filter-starred');assert.equal(await evaluate('document.querySelectorAll(".port-card").length'),1);
  await call('Page.reload');await until(()=>evaluate('document.querySelectorAll(".port-card").length===3'));assert.equal(await evaluate(`document.querySelector('.port-card[data-port="4173"] .star-button').getAttribute('aria-pressed')`),'true');
  await click('.project-button[aria-pressed="false"]');assert.equal(await evaluate('document.querySelectorAll(".port-card").length'),1);await click('#filter-all');await click('.project-button');
  await click('#theme');await capture('dev-dark.png');
  mode='offline';await refresh();assert.equal(await evaluate('document.getElementById("notice").hidden'),false);assert.equal(await evaluate('document.querySelector(".port-status").textContent'),'À vérifier');
  mode='login';await refresh();assert.equal(await evaluate('document.querySelectorAll(".port-card").length'),0);assert.equal(await evaluate('document.getElementById("login").hidden'),false);await capture('dev-session.png');
  mode='empty';await refresh();assert.equal(await evaluate('document.getElementById("empty-title").textContent'),'Aucun serveur web en cours');
  mode='ready';await refresh();assert.equal(await evaluate('document.querySelectorAll(".port-card").length'),3);
  assert.deepEqual(errors,[],'No runtime exceptions or CSP failures');
  console.log('Dashboard Chromium: 6 viewports, HTTP previews, search, project filter, favorites persistence, theme, auth, empty and stale states passed.');
}finally{socket?.close();browser.kill();gateway.closeAllConnections();gateway.close();coder.closeAllConnections();coder.close();await pause(250);await rm(directory,{recursive:true,force:true});}
