"""Read-only project image gallery. HTTP loopback, protected externally by Coder."""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import http.client
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
import time
import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp"}
EXCLUDED = {"node_modules", "credentials", "secrets", "__pycache__", "venv", "env", "vendor", "backups"}
MAX_IMAGE_BYTES = 32 * 1024 * 1024


def resolve_path(root, relative):
    """Reject traversal, hidden paths and all symlinks, even within the root."""
    candidate = Path(relative)
    if candidate.is_absolute() or any(p in {"..", "."} or p.startswith(".") or p.lower() in EXCLUDED for p in candidate.parts):
        raise PermissionError("Path denied")
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise PermissionError("Symlinks denied")
    current = current.resolve(strict=True)
    current.relative_to(root)
    return current


# Discovery reads socket ownership and project directory names only. Never read
# cmdline, environ, config files, Git credentials or the contents of projects.
def project_processes(root, proc=Path("/proc")):
    sockets = {}
    for entry in list(proc.iterdir())[:4096]:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            cwd = (entry / "cwd").resolve(strict=True)
            relative = cwd.relative_to(root)
            if not relative.parts or any(p.startswith(".") or p.lower() in EXCLUDED for p in relative.parts):
                continue
            project = relative.parts[0]
            if (root / project).is_symlink():
                continue
            command = (entry / "exe").resolve(strict=True).name
            process_name = (entry / "comm").read_text().strip() if (entry / "comm").exists() else command
            if process_name.startswith(("codex", "claude")) or command in {"coder", "sshd", "screen", "tmux", "postgres", "redis-server", "chromium", "chrome_crashpad_handler"} or command.startswith(("codex", "claude")):
                continue
            runtime = "Node.js" if command in {"node", "nodejs"} else "Python" if command.startswith("python") else "Go" if command == "go" else "Serveur"
            for descriptor in list((entry / "fd").iterdir())[:2048]:
                try:
                    target = os.readlink(descriptor)
                    if target.startswith("socket:["):
                        sockets[target[8:-1]] = {"project": project, "runtime": runtime}
                except OSError:
                    continue
        except (OSError, ValueError):
            continue
    return sockets


def listening_project_ports(root, proc=Path("/proc")):
    owners = project_processes(root, proc)
    found = {}
    for name in ("tcp", "tcp6"):
        try:
            lines = (proc / "net" / name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A" or fields[9] not in owners:
                continue
            address, raw_port = fields[1].rsplit(":", 1)
            if address not in {"00000000", "0100007F", "0" * 32, "00000000000000000000000001000000"}:
                continue
            port = int(raw_port, 16)
            if 1024 <= port <= 65535 and port not in {2222, 4175}:
                found[port] = {"port": port, **owners[fields[9]]}
    return list(found.values())


def probe_web_port(record):
    for host in ("127.0.0.1", "::1"):
        connection = http.client.HTTPConnection(host, record["port"], timeout=0.35)
        try:
            connection.request("HEAD", "/", headers={"Host": "localhost", "Connection": "close"})
            response = connection.getresponse()
            return {**record, "status": "warning" if response.status >= 500 else "ready", "http_status": response.status, "url": f"https://{record['port']}.dev.lab.bingo/"}
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    return None


def workspace_inventory(root):
    candidates = listening_project_ports(root)
    with ThreadPoolExecutor(max_workers=8) as executor:
        ports = [result for result in executor.map(probe_web_port, candidates[:64]) if result]
    projects = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if not entry.is_symlink() and not entry.name.startswith(".") and entry.name.lower() not in EXCLUDED and entry.is_dir():
            projects.append({"name": entry.name, "ports": sorted(p["port"] for p in ports if p["project"] == entry.name)})
    return {"workspace": {"owner": "bingops", "name": "lab", "agent": "main"}, "checked_at": datetime.now(timezone.utc).isoformat(), "ports": sorted(ports, key=lambda p: (p["project"], p["port"])), "projects": projects[:100], "limited": len(candidates) > 64 or len(projects) > 100}


HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><link rel="icon" href="data:,"><title>Images du workspace · Lecture seule</title><style>
*{box-sizing:border-box}body{margin:0;background:#101a20;color:#dfebea;font:14px/1.5 system-ui}header{position:sticky;top:0;z-index:2;background:#111e25f5;backdrop-filter:blur(10px);border-bottom:1px solid #30434b;padding:18px 4%;display:flex;align-items:center;justify-content:space-between;gap:20px}header strong{font-weight:500}header span{font-size:11px;color:#97c4b7}a{color:#9cd5c7;text-decoration:none}main{padding:25px 4%}nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:20px}button{background:#1d303a;color:#d7e7e5;border:1px solid #3d5760;border-radius:5px;padding:8px 12px;cursor:pointer;font:inherit}button:hover{background:#29444c}.folders{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:28px}.folders button{font-size:12px;color:#b8cec8}#images{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:18px}.image{background:#17262e;border:1px solid #30464e;border-radius:7px;overflow:hidden;padding:0;text-align:left;min-width:0}.image img{display:block;width:100%;height:190px;object-fit:contain;image-rendering:pixelated;background:repeating-conic-gradient(#1b272d 0 25%,#202e34 0 50%) 0/18px 18px}.image span{display:block;padding:11px;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#status{color:#8eabb3;font-size:12px}dialog{padding:0;border:1px solid #486069;background:#0e181f;color:#deece7;border-radius:8px;max-width:95vw;max-height:94dvh}dialog::backdrop{background:#040a0fe8}dialog header{padding:12px 18px}dialog img{display:block;max-width:90vw;max-height:78dvh;object-fit:contain;image-rendering:pixelated}dialog footer{padding:14px 18px;font-size:12px;display:flex;justify-content:space-between;gap:25px}dialog button{padding:4px 10px}#name{max-width:75vw;overflow-wrap:anywhere}#error{color:#e8a68c}button:focus-visible,a:focus-visible{outline:2px solid #b7d7a1;outline-offset:4px}@media(max-width:500px){header{padding:14px 5%}header strong{font-size:12px}header span{font-size:9px}#images{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.image img{height:150px}.image span{font-size:10px}dialog footer{display:block}}
/* Palette commune Portal / Slots / Games. */
:root{color-scheme:light;--ground:#f3f6fc;--surface:#fff;--ink:#111b38;--soft:#626d87;--line:#dce3f0;--tint:#eaf0fe;--link:#1443d6}body{background:var(--ground);color:var(--ink);font-family:system-ui,sans-serif}body>header{background:#1443d6;color:white;border:0;min-height:72px}header strong{font-weight:700}header span{color:#d1dcff}body>header a{color:#d1dcff}a{color:var(--link)}button{background:var(--surface);color:var(--ink);border-color:var(--line);border-radius:9px;min-height:44px}button:hover{background:var(--tint)}.image{background:var(--surface);border-color:var(--line);border-radius:12px}.image img{background:repeating-conic-gradient(#e8edfa 0 25%,#f5f7fc 0 50%) 0/18px 18px}.image span{font-weight:550}#status{color:var(--soft)}dialog{background:var(--surface);color:var(--ink);border-color:var(--line);border-radius:14px;box-shadow:0 20px 80px #08154755}dialog header{background:var(--surface);border-color:var(--line)}dialog footer{color:var(--soft)}nav button{font-size:12px}.folders button{color:var(--soft)}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--ground:#060f2b;--surface:#0c1a45;--ink:#eaefff;--soft:#a3b3df;--line:#20327a;--tint:#16296a;--link:#9db6ff}.image img{background:repeating-conic-gradient(#13234e 0 25%,#1b2b58 0 50%) 0/18px 18px}}
</style></head><body><header><strong>▧ Images du workspace</strong><span>LECTURE SEULE · PROJETS</span><a href="https://dev.lab.bingo/">Dev ↗</a></header><main><nav id="breadcrumbs"></nav><div id="folders" class="folders"></div><p id="status" role="status"></p><p id="error" role="alert"></p><section id="images" aria-label="Images du dossier"></section></main><dialog id="viewer"><header><strong id="name"></strong><button id="close" aria-label="Fermer">×</button></header><img id="large" alt=""><footer><span>Fichier original · aucun changement possible</span><a id="original" target="_blank" rel="noopener">Ouvrir l’original ↗</a></footer></dialog><script>
const $=id=>document.getElementById(id);let controller;
function button(text,action){const b=document.createElement('button');b.textContent=text;b.onclick=action;return b}
function go(path){location.hash=encodeURIComponent(path)}
function raw(path){return '/raw?path='+encodeURIComponent(path)}
async function load(){controller?.abort();controller=new AbortController();const path=decodeURIComponent(location.hash.slice(1));$('error').textContent='';$('status').textContent='Chargement…';try{const response=await fetch('/api/list?path='+encodeURIComponent(path),{signal:controller.signal});if(!response.ok)throw Error('Ce dossier est inaccessible.');const data=await response.json();$('breadcrumbs').replaceChildren(button('Projets',()=>go('')));const parts=path.split('/').filter(Boolean);parts.forEach((part,i)=>{$('breadcrumbs').append(' / ',button(part,()=>go(parts.slice(0,i+1).join('/'))))});$('folders').replaceChildren(...data.directories.map(d=>button('▱ '+d.name,()=>go(d.path))));$('images').replaceChildren(...data.images.map(image=>{const b=button('',()=>{const img=$('large');img.src=raw(image.path);img.alt=image.name;$('name').textContent=image.name;$('original').href=raw(image.path);$('viewer').showModal()});b.className='image';const img=document.createElement('img');img.src=raw(image.path);img.alt=image.name;img.loading='lazy';const name=document.createElement('span');name.textContent=image.name;b.append(img,name);return b}));$('status').textContent=data.images.length+' image(s) · '+data.directories.length+' dossier(s)'+(data.truncated?' · affichage limité aux 1 000 premières entrées':'');}catch(error){if(error.name!=='AbortError'){$('status').textContent='';$('error').textContent=error.message}}}
$('close').onclick=()=>$('viewer').close();$('viewer').onclick=e=>{if(e.target===$('viewer'))$('viewer').close()};window.addEventListener('hashchange',load);load();
</script></body></html>'''


def make_handler(root):
    root = root.resolve(strict=True)
    inventory_lock = Lock()
    inventory_cache = {"at": 0, "data": None}

    class GalleryHandler(BaseHTTPRequestHandler):
        def respond(self, status, body=b"", content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, format, *args):
            # Callback query strings and private project names stay out of logs.
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/_dev/return":
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "https://dev.lab.bingo/")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if parsed.path == "/api/dev/status":
                with inventory_lock:
                    if inventory_cache["data"] is None or time.monotonic() - inventory_cache["at"] > 5:
                        try:
                            inventory_cache["data"] = workspace_inventory(root)
                            inventory_cache["at"] = time.monotonic()
                        except OSError:
                            return self.respond(HTTPStatus.SERVICE_UNAVAILABLE, b'{"error":"discovery_unavailable"}', "application/json")
                    payload = inventory_cache["data"]
                return self.respond(HTTPStatus.OK, json.dumps(payload).encode(), "application/json")
            if parsed.path == "/":
                return self.respond(HTTPStatus.OK, HTML.encode(), "text/html; charset=utf-8")
            if parsed.path not in {"/api/list", "/raw"}:
                return self.respond(HTTPStatus.NOT_FOUND)
            try:
                relative = parse_qs(parsed.query).get("path", [""])[0]
                target = resolve_path(root, relative)
                if parsed.path == "/api/list":
                    if not target.is_dir():
                        return self.respond(HTTPStatus.NOT_FOUND)
                    directories, images = [], []
                    entries = sorted(target.iterdir(), key=lambda p: p.name.casefold())
                    for item in entries[:1000]:
                        if item.is_symlink() or item.name.startswith(".") or item.name.lower() in EXCLUDED:
                            continue
                        record = {"name": item.name, "path": str(item.relative_to(root))}
                        if item.is_dir():
                            directories.append(record)
                        elif item.is_file() and item.suffix.lower() in EXTENSIONS and item.stat().st_size <= MAX_IMAGE_BYTES:
                            images.append(record)
                    data = {"directories": directories, "images": images, "truncated": len(entries) > 1000}
                    return self.respond(HTTPStatus.OK, json.dumps(data).encode(), "application/json")
                if not target.is_file() or target.suffix.lower() not in EXTENSIONS:
                    return self.respond(HTTPStatus.FORBIDDEN)
                descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    if os.fstat(stream.fileno()).st_size > MAX_IMAGE_BYTES:
                        return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    body = stream.read(MAX_IMAGE_BYTES + 1)
                    if len(body) > MAX_IMAGE_BYTES:
                        return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return self.respond(HTTPStatus.OK, body, mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            except (PermissionError, ValueError):
                return self.respond(HTTPStatus.FORBIDDEN)
            except (FileNotFoundError, NotADirectoryError):
                return self.respond(HTTPStatus.NOT_FOUND)
            except OSError:
                return self.respond(HTTPStatus.FORBIDDEN)

        do_HEAD = do_GET

        def reject_write(self):
            self.respond(HTTPStatus.METHOD_NOT_ALLOWED, b"Read-only gallery")

        do_POST = do_PUT = do_PATCH = do_DELETE = reject_write

    return GalleryHandler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/coder/projects"))
    parser.add_argument("--port", type=int, default=4175)
    args = parser.parse_args()
    # Only Coder's local agent can reach this listener through the application proxy.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.root))
    print(f"Read-only image gallery: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
