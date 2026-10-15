import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { createGateway, routeHost, responseHeaders, isEntrypoint } from '../../apps/workloads/coder/base/dev-proxy.mjs';
const canonical = '4173--main--lab--bingops.dev.lab.bingo';
const short = '4173.dev.lab.bingo';

test('only nonprivileged ports on the declared workspace are accepted', () => {
  assert.equal(routeHost(short).canonical, canonical);
  assert.equal(routeHost(canonical).short, short);
  for (const host of ['22.dev.lab.bingo', '65536.dev.lab.bingo', '04173.dev.lab.bingo', '4173.evil.test', '4173--other--lab--bingops.dev.lab.bingo', 'coder.lab.bingo']) assert.equal(routeHost(host), null);
});
test('canonical auth callback keeps wildcard cookie and returns to short URL', () => {
  const route = routeHost(short);
  const auth = 'https://coder.lab.bingo/api/v2/applications/auth-redirect?redirect_uri=' + encodeURIComponent(`https://${canonical}/?callback=example`);
  assert.equal(responseHeaders({ location: auth }, route).location, auth);
  assert.equal(responseHeaders({ location: '/game?q=1' }, route).location, `https://${short}/game?q=1`);
  const cookies = ['session=example; Domain=.dev.lab.bingo; Secure; HttpOnly', `app=example; Domain=${canonical}; Secure`];
  const result = responseHeaders({ 'set-cookie': cookies }, route)['set-cookie'];
  assert.equal(result[0], cookies[0]); assert.match(result[1], /Domain=4173.dev.lab.bingo;/);
});
test('HTTP forwards methods, paths, body, cookies and origin through Coder', async t => {
  let received;
  const coder = http.createServer(async (req, res) => { let body = ''; for await (const part of req) body += part; received = {headers:req.headers,url:req.url,method:req.method,body}; res.writeHead(200, {'access-control-allow-origin':`https://${canonical}`}); res.end('via authenticated proxy'); });
  coder.listen(0, '127.0.0.1'); await once(coder,'listening');
  const gateway = createGateway({ upstream:`http://127.0.0.1:${coder.address().port}` }); gateway.listen(0,'127.0.0.1'); await once(gateway,'listening');
  t.after(()=>{gateway.closeAllConnections(); gateway.close();coder.closeAllConnections();coder.close();});
  const request = (headers, method='GET', body='') => new Promise((resolve,reject)=>{const r=http.request({hostname:'127.0.0.1',port:gateway.address().port,path:'/game?q=1',headers,method},res=>{let text='';res.on('data',p=>text+=p);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,text}));});r.on('error',reject);r.end(body);});
  const result = await request({host:short,origin:`https://${short}`,cookie:'session=example'},'POST','payload');
  assert.equal(result.status,200); assert.equal(received.headers.host,canonical);assert.equal(received.headers.origin,`https://${canonical}`);assert.equal(received.headers.cookie,'session=example');assert.equal(received.body,'payload');assert.equal(received.method,'POST');assert.equal(received.url,'/game?q=1');
  assert.equal(result.headers['access-control-allow-origin'],`https://${short}`);
  await request({host:short,origin:'https://untrusted.example'});assert.equal(received.headers.origin,'https://untrusted.example');
  assert.equal((await request({host:'22.dev.lab.bingo'})).status,404);
});
test('WebSocket upgrades retain the Coder hop and stream both directions', async t => {
  const coder = http.createServer(); coder.on('upgrade',(req,socket)=>{assert.equal(req.headers.host,canonical);socket.write('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');socket.on('data',part=>socket.write(part));socket.on('end',()=>socket.end());});
  coder.listen(0,'127.0.0.1');await once(coder,'listening');
  const gateway=createGateway({upstream:`http://127.0.0.1:${coder.address().port}`});gateway.listen(0,'127.0.0.1');await once(gateway,'listening');
  t.after(()=>{gateway.close();coder.close();});
  await new Promise((resolve,reject)=>{const req=http.request({hostname:'127.0.0.1',port:gateway.address().port,path:'/socket',headers:{host:short,connection:'Upgrade',upgrade:'websocket'}});req.on('upgrade',(res,socket)=>{socket.on('error',reject);socket.once('data',data=>{assert.equal(data.toString(),'ping');socket.destroy();resolve();});socket.write('ping');});req.on('error',reject);req.end();});
});

test('ConfigMap symlink entrypoint starts the executable module', async t => {
  const directory = await mkdtemp(`${tmpdir()}/coder-dev-entry-`);
  t.after(() => rm(directory, {recursive:true,force:true}));
  const source = new URL('../../apps/workloads/coder/base/dev-proxy.mjs', import.meta.url);
  const link = `${directory}/dev-proxy.mjs`;
  await symlink(fileURLToPath(source), link);
  assert.equal(isEntrypoint(link, source.href), true);
  assert.equal(isEntrypoint(undefined, source.href), false);
});

test('dashboard discovery requires Coder authentication and never forwards arbitrary paths', async t => {
  let observed, authorized=false;
  const coder=http.createServer((req,res)=>{
    observed={host:req.headers.host,path:req.url,cookie:req.headers.cookie};
    if(!authorized){res.writeHead(303,{location:'https://coder.lab.bingo/api/v2/applications/auth-redirect?private=example'});res.end();}
    else {res.writeHead(200,{'content-type':'application/json'});res.end('{"ports":[],"projects":[]}');}
  });coder.listen(0,'127.0.0.1');await once(coder,'listening');
  const gateway=createGateway({upstream:`http://127.0.0.1:${coder.address().port}`});gateway.listen(0,'127.0.0.1');await once(gateway,'listening');
  t.after(()=>{gateway.closeAllConnections();gateway.close();coder.closeAllConnections();coder.close();});
  const request=(path,method='GET')=>new Promise((resolve,reject)=>{const req=http.request({hostname:'127.0.0.1',port:gateway.address().port,path,method,headers:{host:'dev.lab.bingo',cookie:'session=example'}},res=>{let body='';res.on('data',part=>body+=part);res.on('end',()=>resolve({status:res.statusCode,body,location:res.headers.location}));});req.on('error',reject);req.end();});
  const login=await request('/api/workspace');assert.equal(login.status,401);assert.equal(login.location,undefined);assert.equal(JSON.parse(login.body).login_url,'https://4175.dev.lab.bingo/_dev/return');assert.equal(login.body.includes('private=example'),false);
  authorized=true;assert.equal((await request('/api/workspace?path=/raw')).status,200);assert.equal(observed.path,'/api/dev/status');assert.equal(observed.host,'4175--main--lab--bingops.dev.lab.bingo');assert.equal(observed.cookie,'session=example');
  assert.equal((await request('/api/workspace','POST')).status,405);assert.equal((await request('/api/arbitrary')).status,404);
});
