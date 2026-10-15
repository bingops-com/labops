"""Read-only project image gallery. HTTP loopback, protected externally by Coder."""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
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


HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><link rel="icon" href="data:,"><title>Images du workspace · Lecture seule</title><style>
*{box-sizing:border-box}body{margin:0;background:#101a20;color:#dfebea;font:14px/1.5 system-ui}header{position:sticky;top:0;z-index:2;background:#111e25f5;backdrop-filter:blur(10px);border-bottom:1px solid #30434b;padding:18px 4%;display:flex;align-items:center;justify-content:space-between;gap:20px}header strong{font-weight:500}header span{font-size:11px;color:#97c4b7}a{color:#9cd5c7;text-decoration:none}main{padding:25px 4%}nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:20px}button{background:#1d303a;color:#d7e7e5;border:1px solid #3d5760;border-radius:5px;padding:8px 12px;cursor:pointer;font:inherit}button:hover{background:#29444c}.folders{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:28px}.folders button{font-size:12px;color:#b8cec8}#images{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:18px}.image{background:#17262e;border:1px solid #30464e;border-radius:7px;overflow:hidden;padding:0;text-align:left;min-width:0}.image img{display:block;width:100%;height:190px;object-fit:contain;image-rendering:pixelated;background:repeating-conic-gradient(#1b272d 0 25%,#202e34 0 50%) 0/18px 18px}.image span{display:block;padding:11px;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#status{color:#8eabb3;font-size:12px}dialog{padding:0;border:1px solid #486069;background:#0e181f;color:#deece7;border-radius:8px;max-width:95vw;max-height:94dvh}dialog::backdrop{background:#040a0fe8}dialog header{padding:12px 18px}dialog img{display:block;max-width:90vw;max-height:78dvh;object-fit:contain;image-rendering:pixelated}dialog footer{padding:14px 18px;font-size:12px;display:flex;justify-content:space-between;gap:25px}dialog button{padding:4px 10px}#name{max-width:75vw;overflow-wrap:anywhere}#error{color:#e8a68c}button:focus-visible,a:focus-visible{outline:2px solid #b7d7a1;outline-offset:4px}@media(max-width:500px){header{padding:14px 5%}header strong{font-size:12px}header span{font-size:9px}#images{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.image img{height:150px}.image span{font-size:10px}dialog footer{display:block}}
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

        def do_GET(self):
            parsed = urlsplit(self.path)
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
