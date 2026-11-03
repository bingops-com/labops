#!/usr/bin/env python3
"""Real two-application migration rehearsal, synthetic data on loopback only."""
import concurrent.futures
import csv
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parents[4]
migration = root / "apps/workloads/arcade/migration"
spec = importlib.util.spec_from_file_location("account_link", root / "hacks/link-game-accounts.py")
link = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(link)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Client:
    def __init__(self, origin):
        self.origin = origin
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, status=200):
        request = urllib.request.Request(self.origin + path, data=None if body is None else json.dumps(body).encode(), method=method, headers={"Content-Type": "application/json", "Origin": self.origin})
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            expected = (status,) if isinstance(status, int) else status
            check(response.status in expected, f"Unexpected {method} {path} HTTP status: {response.status}, expected {status}")
            return json.load(response)


def main():
    check(os.environ.get("PGHOST") in ("127.0.0.1", "localhost"), "PGHOST must explicitly be loopback")
    check(not os.environ.get("PGSERVICE"), "Use explicit local PGHOST/PGPORT/PGUSER, not a service")
    binaries = {game: Path(os.environ[f"ARCADE_{game.upper()}_BINARY"]).resolve() for game in ("games", "slots")}
    check(all(p.is_file() for p in binaries.values()), "Build both application binaries first")
    database = "arcade_e2e_" + secrets.token_hex(6)
    databases = [database]
    env = dict(os.environ, PGDATABASE=database)
    processes = []

    def sql(statement=None, file=None, succeeds=True):
        command = ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1"]
        command += ["-f", str(file)] if file else ["-c", statement]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        check((result.returncode == 0) == succeeds, "SQL rehearsal step had an unexpected result: " + (str(file.name) if file else "synthetic query") + (result.stderr[-1000:] if result.returncode else ""))
        return result.stdout.strip()

    def start(game, shared, tmp):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        address = f"http://127.0.0.1:{port}"
        user = urllib.parse.quote(env.get("PGUSER", os.environ.get("USER", "postgres")), safe="")
        dsn = f"postgresql://{user}@127.0.0.1:{env.get('PGPORT', '5432')}/{env['PGDATABASE']}?sslmode=disable&search_path={game}"
        config = dict(env)
        for key in list(config):
            if key.startswith(("GAMES_", "SLOTS_")):
                del config[key]
        config.update({f"{game.upper()}_DATABASE_URL": dsn, f"{game.upper()}_ADDR": f"127.0.0.1:{port}", f"{game.upper()}_SHARED_ACCOUNTS": str(shared).lower()})
        log = open(tmp / f"{game}-{shared}.log", "w")
        process = subprocess.Popen([str(binaries[game])], env=config, stdout=log, stderr=log)
        processes.append((process, log))
        for _ in range(100):
            check(process.poll() is None, f"The synthetic {game} server exited")
            try:
                with urllib.request.urlopen(address + "/healthz", timeout=1) as response:
                    if response.status == 200:
                        return address
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        raise AssertionError(f"The synthetic {game} server did not become ready")

    def stop():
        for process, log in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            log.close()
        processes.clear()

    subprocess.run(["createdb", database], check=True, stdout=subprocess.DEVNULL)
    try:
        with tempfile.TemporaryDirectory(prefix="arcade-rehearsal-") as directory:
            tmp = Path(directory)
            sql("CREATE SCHEMA games; CREATE SCHEMA slots;")
            origins = {game: start(game, False, tmp) for game in binaries}
            for game, origin in origins.items():
                client = Client(origin)
                for name in ("SharedPlayer", "TiePlayer", "GamesOnly" if game == "games" else "SlotsOnly"):
                    client.call("POST", "/api/register", {"name": name, "password": game + " synthetic password"})
            sql("DELETE FROM games.sessions; DELETE FROM slots.sessions; DELETE FROM games.recovery_codes; UPDATE games.users SET id='00000000000000000000000000000001',created_at=20 WHERE name_key='sharedplayer'; UPDATE slots.users SET id='ffffffffffffffffffffffffffffffff',created_at=10 WHERE name_key='sharedplayer'; UPDATE games.users SET id='00000000000000000000000000000002',created_at=30 WHERE name_key='tieplayer'; UPDATE slots.users SET id='fffffffffffffffffffffffffffffffe',created_at=30 WHERE name_key='tieplayer';")
            sql("UPDATE games.users SET credits = 123 WHERE name_key = 'sharedplayer'; INSERT INTO games.game_stats SELECT id, 'ono', 3, 1 FROM games.users WHERE name_key = 'sharedplayer'; UPDATE slots.users SET stake = 543210, wallet = jsonb_set(wallet, '{stake}', '543210') WHERE name_key = 'sharedplayer'; INSERT INTO slots.game_stats (user_id, game, rounds, wagered, won, best_mult, best_payout) SELECT id, 'dice', 2, 100, 200, 2, 200 FROM slots.users WHERE name_key = 'sharedplayer';")
            stop()
            # Exercise the real import helper on disposable restored sources,
            # including its schema renaming and retry protection.
            services = []
            for game in binaries:
                clone = f"arcade_{game}_restore_{database.removeprefix('arcade_e2e_')}"
                subprocess.run(["createdb", clone], check=True)
                databases.append(clone)
                dump = tmp / f"{game}.dump"
                subprocess.run(["pg_dump", "--format=custom", "--schema", game, "--file", str(dump)], env=env, check=True)
                subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", clone, str(dump)], env=env, check=True)
                clone_env = dict(env, PGDATABASE=clone)
                subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"DROP SCHEMA public; ALTER SCHEMA {game} RENAME TO public"], env=clone_env, check=True, stdout=subprocess.DEVNULL)
                services.append((game, clone))
            services.append(("target", database))
            service_file = tmp / "pg_service.conf"
            service_file.write_text("\n".join(f"[{name}]\nhost=127.0.0.1\nport={env.get('PGPORT', '5432')}\nuser={env.get('PGUSER', os.environ.get('USER', 'postgres'))}\ndbname={db}\n" for name, db in services))
            service_file.chmod(0o600)
            sql("DROP SCHEMA games, slots CASCADE")
            stage_env = dict(env, PGSERVICEFILE=str(service_file), ARCADE_GAMES_RESTORE_SERVICE="games", ARCADE_SLOTS_RESTORE_SERVICE="slots", ARCADE_TARGET_SERVICE="target")
            staged = subprocess.run(["bash", str(migration / "stage-copies.sh")], env=stage_env, capture_output=True, text=True)
            check(staged.returncode == 0, "Import helper failed on restored synthetic copies: " + staged.stderr[-500:])
            retried = subprocess.run(["bash", str(migration / "stage-copies.sh")], env=stage_env, capture_output=True, text=True)
            check(retried.returncode != 0, "Import helper overwrote existing staged schemas")
            sql(file=migration / "prepare.sql")
            sql(file=migration / "preserve-collisions.sql")
            sql(file=migration / "preserve-collisions.sql")
            sql("CREATE SCHEMA cka; CREATE TABLE cka.progress(owner text PRIMARY KEY,account_id text REFERENCES identity.users(id) ON DELETE CASCADE,state jsonb NOT NULL,revision integer NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),CHECK(account_id IS NULL OR owner='account:'||account_id)); INSERT INTO cka.progress(owner,account_id,state,revision) SELECT 'account:'||id,id,CASE WHEN origin='games' THEN '{\"done\":[\"service\"],\"journal\":\"later note\",\"experience\":[{\"key\":\"sim:first-pod:0\",\"xp\":60,\"date\":1}]}'::jsonb ELSE '{\"done\":[\"rbac\"],\"journal\":\"first note\",\"experience\":[{\"key\":\"sim:first-pod:0\",\"xp\":120,\"date\":2}]}'::jsonb END,1 FROM identity.users WHERE lower(name)='sharedplayer'; INSERT INTO games.rooms(code,state,updated_at) VALUES('fixture','{\"members\":[{\"userId\":\"00000000000000000000000000000001\"}],\"text\":\"prefix00000000000000000000000000000001\"}',1);")
            sql(file=migration / "unify-accounts.sql")
            sql(file=migration / "unify-accounts.sql")
            check(sql("SELECT COUNT(*) FROM identity.users") == "4", "Canonical identity cardinality failed")
            check(sql("SELECT COUNT(*) FROM identity.account_links") == "6", "Source identity map was lost")
            check(sql("SELECT id FROM identity.users WHERE name_key='sharedplayer'") == "ffffffffffffffffffffffffffffffff", "First creation did not take priority over ID")
            check(sql("SELECT id FROM identity.users WHERE name_key='tieplayer'") == "00000000000000000000000000000002", "Smallest ID did not break equal creation timestamps")
            check(sql("SELECT COUNT(*) FROM games.users") == "4" and sql("SELECT COUNT(*) FROM slots.users") == "4", "Applications have different account directories")
            check(sql("SELECT credits::text||'|'||stake::text FROM identity.users WHERE name_key='sharedplayer'") == "123|543210", "Service balances were not preserved")
            check(sql("SELECT COUNT(*) FROM slots.game_stats s JOIN games.game_stats g USING(user_id)") == "1", "Game histories were not joined to one account")
            check(sql("SELECT COUNT(*) FROM identity.sessions") == "0", "Pre-merge sessions survived")
            check(sql("SELECT state->>'journal' FROM cka.progress") == "first note", "Winning account progress did not take precedence")
            check(sql("SELECT state->'done' @> '[\"service\",\"rbac\"]'::jsonb FROM cka.progress") == "t", "Progress was lost")
            check(sql("SELECT state#>>'{experience,0,xp}' FROM cka.progress") == "120", "XP was duplicated or lost")
            check(sql("SELECT count(*) FROM identity.account_merge_archive WHERE kind='progress'") == "2", "Original progress snapshots were not retained")
            check(sql("SELECT state#>>'{members,0,userId}' FROM games.rooms WHERE code='fixture'") == "ffffffffffffffffffffffffffffffff", "Room user reference was not remapped")
            check(sql("SELECT state->>'text' FROM games.rooms WHERE code='fixture'") == "prefix00000000000000000000000000000001", "JSON content was rewritten by substring")
            sql("CREATE SCHEMA future; CREATE VIEW future.users AS SELECT * FROM identity.users; INSERT INTO identity.account_links VALUES('future-app','legacy-id','ffffffffffffffffffffffffffffffff');")
            check(sql("SELECT count(*) FROM future.users") == "4", "A future consumer sees a different directory")
            sql("DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='cka_app') THEN CREATE ROLE cka_app;END IF;END $$;")
            sql(file=migration / 'account-contract.sql')
            check(sql("SET ROLE cka_app; SELECT identity.resolve_sso('"+'a'*64+"','SharedPlayer')").endswith('ffffffffffffffffffffffffffffffff'), 'SSO did not resolve the canonical common account')
            check(sql("SET ROLE cka_app; SELECT identity.public_profile('SharedPlayer')") == 'SET', 'Profile was public by default')
            check(sql("SET ROLE cka_app; SELECT identity.account_profile('ffffffffffffffffffffffffffffffff')->>'name'").endswith('SharedPlayer'), 'Private profile RPC failed')
            profile={'displayName':'Example learner','bio':'CKA practice','location':'Paris','website':'https://example.invalid','contactEmail':'private@example.invalid','avatarColor':'mint','publicProfile':True,'showBadges':True,'theme':'dark','reducedMotion':True,'dailyGoal':4}
            payload=json.dumps(profile).replace("'","''")
            sql("SET ROLE cka_app; SELECT identity.save_profile('ffffffffffffffffffffffffffffffff',1,'"+payload+"')")
            public=json.loads(sql("SET ROLE cka_app; SELECT identity.public_profile('SharedPlayer')").splitlines()[-1])
            check(public['displayName']=='Example learner' and 'contactEmail' not in public and 'password' not in public,'Public profile exposed private fields')
            sql("SET ROLE cka_app; SELECT identity.save_profile('ffffffffffffffffffffffffffffffff',1,'"+payload+"')",succeeds=False)
            sql('SET ROLE cka_app; SELECT * FROM identity.account_merge_archive',succeeds=False)
            sql('SET ROLE cka_app; UPDATE identity.users SET credits=999',succeeds=False)
            origins = {game: start(game, True, tmp) for game in binaries}
            shared_clients = {game: Client(origin) for game, origin in origins.items()}
            for game,client in shared_clients.items():
                client.call("POST", "/api/login", {"name":"SharedPlayer","password":"slots synthetic password"})
                client.call("POST", "/api/login", {"name":"TiePlayer","password":"games synthetic password"})
                Client(origins[game]).call("POST", "/api/login", {"name":"SharedPlayer","password":"games synthetic password"},status=401)
            shared_clients['slots'].call('POST','/api/login',{'name':'SharedPlayer','password':'slots synthetic password'})
            for source, other in (("games", "slots"), ("slots", "games")):
                Client(origins[other]).call("POST", "/api/login", {"name": source.capitalize() + "Only", "password": source + " synthetic password"})
            check(shared_clients["slots"].call("GET", "/api/me")["user"]["balance"] == 543210, "Slots wallet did not survive login")
            for source, other in (("games", "slots"), ("slots", "games")):
                name = "From" + source.capitalize()
                Client(origins[source]).call("POST", "/api/register", {"name": name, "password": "new common password"})
                Client(origins[other]).call("POST", "/api/login", {"name": name, "password": "new common password"})
                Client(origins[other]).call("POST", "/api/register", {"name": name.swapcase(), "password": "other password"}, status=409)
            def register(game):
                response = Client(origins[game]).call("POST", "/api/register", {"name": "RacingName", "password": "concurrent password"}, status=(200, 409))
                return "user" in response
            with concurrent.futures.ThreadPoolExecutor() as pool:
                check(sum(pool.map(register, ("games", "slots"))) == 1, "Concurrent registration did not have exactly one winner")
            check(sql("SELECT COUNT(*) FROM identity.users WHERE name_key = 'racingname'") == "1", "Duplicate common account created")
            for client in shared_clients.values():
                client.call("POST", "/api/login", {"name":"GamesOnly","password":"games synthetic password"})
            shared_clients["games"].call("POST", "/api/account/password", {"old": "games synthetic password", "new": "changed common password"})
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "GamesOnly", "password": "changed common password"})
            codes = shared_clients["games"].call("POST", "/api/account/recovery-codes", {"password": "changed common password"})["recoveryCodes"]
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "GamesOnly", "password": "changed common password"})
            # Request fields follow the recovery API; no code is logged or saved.
            Client(origins["games"]).call("POST", "/api/reset", {"name": "GamesOnly", "code": codes[0], "password": "recovered common password"})
            Client(origins["games"]).call("POST", "/api/reset", {"name": "GamesOnly", "code": codes[0], "password": "another common password"}, status=400)
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "GamesOnly", "password": "recovered common password"})
            stop()
            backup = tmp / "synthetic.dump"
            subprocess.run(["pg_dump", "--format=custom", "--file", str(backup)], env=env, check=True)
            restored = database + "_restored"
            subprocess.run(["createdb", restored], check=True)
            databases.append(restored)
            env["PGDATABASE"] = restored
            subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", restored, str(backup)], env=env, check=True)
            sql(file=migration / "unify-accounts.sql")
            for game in binaries:
                client = Client(start(game, True, tmp))
                client.call("POST", "/api/login", {"name": "GamesOnly", "password": "recovered common password"})
            check(sql("SELECT (SELECT credits FROM identity.users WHERE name_key='sharedplayer'),(SELECT stake FROM identity.users WHERE name_key='sharedplayer')") == "123|543210", "Restore lost game balances")
            print("PASS: earliest-account policy, ID tie-break, shared directory, balances/histories, registration races, password/recovery revocation and dump/restore")
    finally:
        stop()
        for disposable in reversed(databases):
            subprocess.run(["dropdb", "--if-exists", disposable], env=os.environ, check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
