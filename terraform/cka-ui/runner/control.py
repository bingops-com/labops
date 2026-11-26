#!/usr/bin/env python3
"""Owner-private CKA controller. HTTP over a mode-0600 Unix socket only.

The web application never reads Proxmox credentials and cannot supply a host,
VMID, Terraform argument, executable, or filesystem path.
"""
import argparse
import concurrent.futures
import contextlib
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import sqlite3
import ssl
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
LABOPS = ROOT.parents[1]
LEGACY = {620: "k8s-master", 621: "k8s-worker-1"}
RESERVED = {700, 710, 711, 712, 720, 721, 722}
SCENARIOS = json.loads((ROOT / "scenarios.json").read_text())["scenarios"]


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Proxmox:
    def __init__(self, credentials, ca):
        self.credentials = Path(credentials)
        self.ca = Path(ca)

    def get(self, path):
        text = self.credentials.read_text()
        def field(name):
            match = re.search(r'^\s*' + name + r'\s*=\s*("(?:[^"\\]|\\.)*")', text, re.M)
            if not match:
                raise RuntimeError("Configuration API absente.")
            return json.loads(match.group(1))
        base = field("proxmox_api_url").rstrip("/")
        if not base.endswith("/api2/json"):
            base += "/api2/json"
        ctx = ssl.create_default_context(cafile=str(self.ca))
        # PVE 8 CA lacks a keyUsage extension required by Python 3.13 strict
        # mode. Certificate-chain verification and hostname checking stay ON.
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        request = urllib.request.Request(base + path, headers={"Authorization": "PVEAPIToken=" + field("proxmox_api_token")})
        with urllib.request.urlopen(request, context=ctx, timeout=15) as response:
            return json.load(response)["data"]

    def inventory(self):
        return [{k: item.get(k) for k in ("vmid", "name", "status", "pool", "node", "maxmem")} for item in self.get("/cluster/resources?type=vm")]

    def capacity(self):
        node = next(n for n in self.get("/nodes") if n["node"] == "homelab")
        return {"memoryFreeMiB": max(0, (node["maxmem"] - node["mem"]) // 1048576), "cpuCount": node["maxcpu"]}


def topology(control_planes, workers, profile="ready"):
    if type(control_planes) is not int or control_planes not in (1, 3) or type(workers) is not int or not 1 <= workers <= 3 or profile not in ("ready", "bare"):
        raise Problem(400, "Choisis 1 ou 3 control planes, 1 à 3 workers et un profil valide.")
    nodes = [{"name": "cka-cp-" + str(i + 1), "role": "control-plane", "vmid": 710 + i, "ip": "172.30.90." + str(10 + i)} for i in range(control_planes)]
    nodes += [{"name": "cka-worker-" + str(i + 1), "role": "worker", "vmid": 720 + i, "ip": "172.30.90." + str(20 + i)} for i in range(workers)]
    return {"controlPlanes": control_planes, "workers": workers, "profile": profile, "nodes": nodes, "vmids": [700] + [n["vmid"] for n in nodes], "memoryMiB": 1024 + control_planes * 3072 + workers * 2048}


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "control.sqlite"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), lab TEXT)")
            db.execute("INSERT OR IGNORE INTO state VALUES (1,NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, action TEXT, lab TEXT, payload TEXT, status TEXT, stage TEXT, created REAL)")
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self):
        with self.connect() as db:
            raw = db.execute("SELECT lab FROM state WHERE id=1").fetchone()[0]
            job = db.execute("SELECT id,action,status,stage,created FROM jobs ORDER BY created DESC LIMIT 1").fetchone()
        return json.loads(raw) if raw else None, dict(job) if job else None

    def stage(self, job_id, stage):
        with self.connect() as db:
            db.execute("UPDATE jobs SET stage=? WHERE id=?", (stage, job_id))

    def recover(self):
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]:
                db.execute("UPDATE jobs SET status='interrupted',stage='Opération interrompue : le lab reste réservé. Vérifie son état ou détruis-le avant de recréer.' WHERE status='running'")
                raw = db.execute("SELECT lab FROM state WHERE id=1").fetchone()[0]
                if raw:
                    lab = json.loads(raw)
                    lab["status"] = "error"
                    db.execute("UPDATE state SET lab=? WHERE id=1", (json.dumps(lab),))


class Controller:
    def __init__(self, store, provider, executor=None):
        self.store, self.provider, self.executor = store, provider, executor
        self.gate = threading.RLock()
        self.console_gate = threading.BoundedSemaphore(1)

    def discover(self, inventory):
        legacy = [v for v in inventory if v["vmid"] in LEGACY]
        if legacy:
            if any(v["name"] != LEGACY[v["vmid"]] for v in legacy):
                raise Problem(409, "Une identité de VM historique a changé. Vérification opérateur requise.")
            return {"id": "legacy-cka", "status": "legacy", "name": "Lab CKA existant", "vmids": sorted(v["vmid"] for v in legacy), "nodes": [{"vmid": v["vmid"], "name": v["name"], "role": "control-plane" if v["vmid"] == 620 else "worker"} for v in legacy], "scenario": None, "managed": False}
        return None

    @staticmethod
    def actor(value):
        if not isinstance(value,str) or not re.fullmatch(r"[a-f0-9]{64}",value):
            raise Problem(401,"Une identité SSO vérifiée est nécessaire.")
        return value

    def status(self, actor=None):
        actor=self.actor(actor)
        with self.gate:
            inventory = self.provider.inventory()
            lab, job = self.store.read()
            existing = self.discover(inventory)
            orphaned = [v for v in inventory if v["vmid"] in RESERVED and (not lab or v["vmid"] not in lab["vmids"])]
            owned = bool(lab and lab.get("owner")==actor)
            visible_lab = dict(lab) if owned else None
            if visible_lab: visible_lab.pop("owner",None)
            if visible_lab and visible_lab.get("scenario") in SCENARIOS:
                visible_lab["question"] = {"id": visible_lab["scenario"], **SCENARIOS[visible_lab["scenario"]]}
            if job and not owned and lab:
                job = None
            if job:
                job = dict(job)
                job["stage"] = {"create": "Création automatique de l’environnement", "retry": "Reprise automatique de l’environnement", "destroy": "Suppression du lab confirmé", "verify": "Évaluation de la tentative"}.get(job["action"], "Opération du lab")
                if job["status"] == "complete": job["stage"] = "Opération terminée"
                if job["status"] in ("error", "interrupted"): job["stage"] = "Intervention opérateur nécessaire ; le lab reste réservé."
            return {"connected": True, "lab": visible_lab, "otherLab": None, "job": job, "blocked": bool(lab or existing or orphaned), "orphans": [{"vmid": v["vmid"], "name": v["name"]} for v in orphaned] if owned else [], "capacity": self.provider.capacity(), "scenarios": [{"id": k, **v} for k, v in SCENARIOS.items()], "creationEnabled": self.executor is not None, "singleLab": True}

    def submit(self, body, actor=None):
        actor=self.actor(actor)
        if self.executor is None:
            raise Problem(503, "Le service d’exécution n’est pas activé.")
        if not isinstance(body, dict) or set(body) - {"action", "labId", "scenario", "confirmation"}:
            raise Problem(400, "Requête invalide.")
        action = body.get("action")
        if action not in ("create", "destroy", "verify", "retry"):
            raise Problem(400, "Action inconnue.")
        with self.gate, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
                raise Problem(409, "Une opération est déjà en cours. Attends sa fin.")
            raw = db.execute("SELECT lab FROM state WHERE id=1").fetchone()[0]
            lab = json.loads(raw) if raw else None
            inventory = self.provider.inventory()
            existing = self.discover(inventory)
            if action == "create":
                if lab or existing or any(v["vmid"] in RESERVED for v in inventory):
                    raise Problem(409, "Un lab existe déjà. Détruis-le entièrement avant toute nouvelle création.")
                scenario = SCENARIOS.get(body.get("scenario"))
                if not scenario:
                    raise Problem(400, "Choisis un exercice disponible ; sa topologie est définie par le scénario.")
                plan = topology(scenario["controlPlanes"], scenario["workers"], "ready")
                if plan["memoryMiB"] + 8192 > self.provider.capacity()["memoryFreeMiB"]:
                    raise Problem(409, "La mémoire disponible ne permet pas cette topologie avec la marge réservée à l’hôte.")
                lab = {"id": str(uuid.uuid4()), "name": "Mon lab Proxmox", "status": "creating", "managed": True, "owner": actor, "created": time.time(), "scenario": body["scenario"], "validation": None, "finished": False, **plan}
            else:
                lab = lab or existing
                if lab and lab.get("owner")!=actor:
                    raise Problem(403,"Cette session appartient à un autre utilisateur.")
                if not lab or body.get("labId") != lab["id"]:
                    raise Problem(409, "Le lab demandé n’est plus le lab actif. Actualise son état.")
                if action == "destroy":
                    required = "DETRUIRE " + ",".join(map(str, sorted(lab["vmids"])))
                    if body.get("confirmation") != required:
                        raise Problem(400, "Confirme explicitement les VM et la perte de leurs disques : " + required)
                    lab["status"] = "destroying"
                elif action == "retry":
                    previous = db.execute("SELECT action,status FROM jobs ORDER BY created DESC LIMIT 1").fetchone()
                    if not lab.get("managed") or lab["status"] != "error" or lab.get("finished") or not previous or previous["action"] not in ("create", "retry") or previous["status"] not in ("error", "interrupted"):
                        raise Problem(409, "Seule une création interrompue peut être reprise sans remplacement.")
                    requirement = SCENARIOS.get(lab.get("scenario"))
                    if not requirement or any(lab[key]!=requirement[key] for key in ("controlPlanes","workers")):
                        raise Problem(409, "Les prérequis du scénario ont changé ; reprise refusée.")
                    lab["status"] = "creating"
                else:
                    if not lab.get("managed") or lab["status"] != "ready" or lab.get("profile") != "ready":
                        raise Problem(409, "Cette action nécessite un cluster géré et prêt.")
                    if not lab.get("scenario") or lab.get("finished"):
                        raise Problem(409, "Aucune tentative active à évaluer.")
                    lab["status"] = "evaluating"

            job_id = str(uuid.uuid4())
            db.execute("UPDATE state SET lab=? WHERE id=1", (json.dumps(lab),))
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?)", (job_id, action, lab["id"], json.dumps(lab), "queued", "Opération en attente", time.time()))
            return {"jobId": job_id, "labId": lab["id"]}

    def execute_one(self):
        with self.gate, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return False
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
        lab = json.loads(row["payload"])
        try:
            result = self.executor(row["action"], lab, lambda text: self.store.stage(row["id"], text))
            if row["action"] == "destroy":
                if any(v["vmid"] in lab["vmids"] for v in self.provider.inventory()):
                    raise RuntimeError("Des VM existent encore.")
                lab = None
            else:
                lab["status"] = "ready"
                if row["action"] in ("create","retry"):
                    lab["readyAt"] = time.time()
                if row["action"] == "verify":
                    lab["validation"] = result
                    lab["finished"] = True
            with self.gate, self.store.connect() as db:
                db.execute("UPDATE state SET lab=? WHERE id=1", (json.dumps(lab) if lab else None,))
                db.execute("UPDATE jobs SET status='complete',stage='Opération terminée' WHERE id=?", (row["id"],))
        except Exception:
            lab["status"] = "error"
            with self.gate, self.store.connect() as db:
                db.execute("UPDATE state SET lab=? WHERE id=1", (json.dumps(lab),))
                db.execute("UPDATE jobs SET status='error',stage='L’opération a échoué. Le lab reste réservé ; consulte le journal privé du contrôleur avant toute reprise.' WHERE id=?", (row["id"],))
        return True

    def console(self, body, actor=None):
        actor=self.actor(actor)
        if not isinstance(body, dict) or set(body) != {"labId", "node", "command"}:
            raise Problem(400, "Commande invalide.")
        with self.gate:
            lab, job = self.store.read()
            if lab and lab.get("owner")!=actor:
                raise Problem(403,"Cette session appartient à un autre utilisateur.")
            if not lab or lab["id"] != body["labId"] or lab["status"] != "ready" or not lab.get("managed"):
                raise Problem(409, "Le lab n’est pas prêt pour une connexion.")
            if job and job["status"] in ("running", "queued"):
                raise Problem(409, "Une opération est en cours.")
            if body["node"] not in [n["name"] for n in lab["nodes"]] or not isinstance(body["command"], str) or not 0 < len(body["command"].encode()) <= 4096 or "\0" in body["command"]:
                raise Problem(400, "Cible ou commande invalide.")
            if not self.console_gate.acquire(blocking=False):
                raise Problem(409, "Une commande est déjà en cours.")
        try:
            return self.executor.console(lab, body["node"], body["command"])
        finally:
            self.console_gate.release()


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve(controller, socket_path):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Request bodies, commands and private output are never logged.

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def dispatch(self):
            try:
                if self.command == "GET" and self.path == "/healthz":
                    value, code = {"ok":True}, 200
                elif self.command == "GET" and self.path == "/status":
                    value, code = controller.status(self.headers.get("X-CKA-Actor")), 200
                elif self.command == "POST" and self.path in ("/actions", "/console"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8192:
                        raise Problem(413, "Requête trop volumineuse.")
                    body = json.loads(self.rfile.read(length))
                    value, code = (controller.submit(body,self.headers.get("X-CKA-Actor")), 202) if self.path == "/actions" else (controller.console(body,self.headers.get("X-CKA-Actor")), 200)
                else:
                    raise Problem(404, "Route introuvable.")
            except Problem as error:
                value, code = {"error": str(error)}, error.status
            except (ValueError, TypeError):
                value, code = {"error": "Requête invalide."}, 400
            except Exception:
                value, code = {"error": "Le contrôleur ne peut pas vérifier Proxmox. Aucune création n’est autorisée tant que cet état est inconnu."}, 503
            payload = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # A live controller owns this socket; never remove it to start a second one.
    if path.exists():
        import socket
        probe = socket.socket(socket.AF_UNIX)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            path.unlink()
        else:
            raise RuntimeError("Un contrôleur écoute déjà sur ce socket.")
        finally:
            probe.close()
    with UnixServer(str(path), Handler) as server:
        os.chmod(path, 0o600)
        server.serve_forever()


def main():
    if (ROOT / ".runtime/ownership-moved").exists():
        raise SystemExit("State ownership moved to production; this controller is retired.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default=str(ROOT / ".runtime/control.sock"))
    parser.add_argument("--runtime", default=str(ROOT / ".runtime"))
    parser.add_argument("--credentials", default=str(LABOPS / "terraform/proxmox/credentials.auto.tfvars"))
    parser.add_argument("--ca", default=str(ROOT / ".runtime/proxmox-ca.pem"))
    parser.add_argument("--enable-actions", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    store = Store(args.runtime)
    executor = None
    if args.enable_actions:
        from provision import Executor
        executor = Executor(ROOT, args.runtime, args.credentials, args.ca)
    controller = Controller(store, Proxmox(args.credentials, args.ca), executor)
    # Acquire an OS process lock before recovering jobs. A second process must
    # not mark the first process's running job interrupted.
    import fcntl
    with (Path(args.runtime) / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store.recover()
        def work():
            while True:
                controller.execute_one()
                time.sleep(1)
        if executor:
            threading.Thread(target=work, daemon=True).start()
        serve(controller, args.socket)


if __name__ == "__main__":
    main()
