// Short port aliases retain Coder's owner-private application authentication.
// Never log URLs: Coder's login callback carries a temporary credential in its query.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const suffix = '.dev.lab.bingo';
export function routeHost(host = '') {
  const match = /^(\d+)(--main--lab--bingops)?\.dev\.lab\.bingo$/.exec(host.toLowerCase());
  if (!match || !/^[1-9]\d*$/.test(match[1])) return null;
  const port = Number(match[1]);
  if (port < 1024 || port > 65535) return null;
  return { short: `${port}${suffix}`, canonical: `${port}--main--lab--bingops${suffix}` };
}

function requestHeaders(req, route, upgrade) {
  const headers = { ...req.headers, host: route.canonical, 'x-forwarded-host': route.canonical, 'x-forwarded-proto': 'https' };
  // Coder's origin check parses the canonical app hostname. Map only this app's
  // same-origin alias, leaving other origins for Coder to validate normally.
  if (headers.origin === `https://${route.short}`) headers.origin = `https://${route.canonical}`;
  if (!upgrade) { delete headers.connection; delete headers.upgrade; }
  return headers;
}

export function responseHeaders(headers, route) {
  const result = { ...headers };
  if (result.location) {
    try {
      const url = new URL(result.location, `https://${route.canonical}`);
      if (url.hostname === route.canonical) { url.hostname = route.short; result.location = url.href; }
      // Authentication URLs and their encoded redirect_uri remain intact. Coder
      // validates the canonical callback, sets its wildcard cookie, then redirects
      // to the short hostname via the response rewrite above.
    } catch { /* Preserve an unusual application Location header. */ }
  }
  if (result['access-control-allow-origin'] === `https://${route.canonical}`) result['access-control-allow-origin'] = `https://${route.short}`;
  if (result['set-cookie']) result['set-cookie'] = result['set-cookie'].map(cookie => cookie.replace(/(domain=)([^;]+)/ig, (all, key, domain) => domain.replace(/^\./, '').toLowerCase() === route.canonical ? `${key}${route.short}` : all));
  return result;
}

export function createGateway({ upstream = 'http://coder.coder.svc.cluster.local', portal = new URL('./index.html', import.meta.url) } = {}) {
  const destination = new URL(upstream);
  const server = http.createServer(async (req, res) => {
    if (req.url === '/healthz') { res.writeHead(200); res.end('ok'); return; }
    const dashboard = req.headers.host === 'dev.lab.bingo';
    const inventory = dashboard && req.url.split('?')[0] === '/api/workspace';
    if (dashboard && !['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
    if (dashboard && !inventory) {
      const assets = {
        '/': [portal, 'text/html; charset=utf-8'],
        '/dev.css': [new URL('./dev.css', portal), 'text/css; charset=utf-8'],
        '/dev.js': [new URL('./dev.js', portal), 'text/javascript; charset=utf-8'],
        '/fonts/display.woff2': [new URL('./display.woff2', portal), 'font/woff2'],
        '/fonts/display-ext.woff2': [new URL('./display-ext.woff2', portal), 'font/woff2'],
        '/fonts/text.woff2': [new URL('./text.woff2', portal), 'font/woff2'],
        '/fonts/text-ext.woff2': [new URL('./text-ext.woff2', portal), 'font/woff2'],
      };
      const asset = assets[req.url.split('?')[0]];
      if (!asset) { res.writeHead(404); res.end(); return; }
      try {
        const body = await readFile(asset[0]);
        res.writeHead(200, { 'content-type': asset[1], 'cache-control': 'no-cache', 'x-content-type-options': 'nosniff', 'content-security-policy': "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" });
        res.end(req.method === 'HEAD' ? undefined : body);
      } catch { res.writeHead(503); res.end('Portal unavailable'); }
      return;
    }
    const route = routeHost(inventory ? '4175.dev.lab.bingo' : req.headers.host);
    if (!route) { res.writeHead(404); res.end('Unknown development address'); return; }
    const path = inventory ? '/api/dev/status' : req.url;
    const proxy = http.request({ hostname: destination.hostname, port: destination.port || 80, method: req.method, path, headers: requestHeaders(req, route, false) }, response => {
      if (inventory && response.statusCode !== 200) {
        const login = [301, 302, 303, 307, 308, 401, 403].includes(response.statusCode);
        res.writeHead(login ? 401 : 503, { 'content-type': 'application/json', 'cache-control': 'no-store' });
        res.end(JSON.stringify({ error: login ? 'authentication_required' : 'workspace_unavailable', login_url: 'https://4175.dev.lab.bingo/_dev/return' }));
        response.resume(); return;
      }
      if (inventory && !response.headers['content-type']?.includes('application/json')) {
        res.writeHead(503, { 'content-type': 'application/json', 'cache-control': 'no-store' });
        res.end('{"error":"agent_update_required"}'); response.resume(); return;
      }
      res.writeHead(response.statusCode, responseHeaders(response.headers, route));
      response.on('error', () => res.destroy()); response.pipe(res);
    });
    proxy.on('error', () => { if (!res.headersSent) { res.writeHead(502); res.end('Coder unavailable'); } else res.destroy(); });
    req.on('aborted', () => proxy.destroy()); res.on('close', () => proxy.destroy());
    req.pipe(proxy);
  });
  server.on('upgrade', (req, socket, head) => {
    const route = routeHost(req.headers.host);
    if (!route) { socket.end('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n'); return; }
    const proxy = http.request({ hostname: destination.hostname, port: destination.port || 80, path: req.url, headers: requestHeaders(req, route, true) });
    proxy.on('upgrade', (response, remote, remoteHead) => {
      const headers = responseHeaders(response.headers, route);
      socket.write(`HTTP/1.1 101 Switching Protocols\r\n${Object.entries(headers).flatMap(([key, value]) => (Array.isArray(value) ? value : [value]).map(item => `${key}: ${item}\r\n`)).join('')}\r\n`);
      if (head.length) remote.write(head); if (remoteHead.length) socket.write(remoteHead);
      remote.on('error', () => socket.destroy()); socket.on('error', () => remote.destroy());
      remote.on('close', () => socket.destroy()); socket.on('close', () => remote.destroy());
      socket.on('end', () => remote.end()); remote.on('end', () => socket.end());
      remote.pipe(socket); socket.pipe(remote);
    });
    proxy.on('response', response => {
      // Preserve Coder's unauthenticated refusal rather than upgrading the socket.
      socket.end(`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\nConnection: close\r\n\r\n`); response.resume();
    });
    proxy.on('error', () => socket.destroy()); socket.on('error', () => proxy.destroy()); proxy.end();
  });
  return server;
}
export const isEntrypoint = (entry, moduleUrl = import.meta.url) => !!entry && moduleUrl === pathToFileURL(realpathSync(entry)).href;
if (isEntrypoint(process.argv[1])) createGateway().listen(8080, '0.0.0.0');
