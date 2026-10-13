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
        check((result.returncode == 0) == succeeds, "SQL rehearsal step had an unexpected result: " + (str(file.name) if file else "synthetic query"))
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
                for name in ("SharedPlayer", "GamesOnly" if game == "games" else "SlotsOnly"):
                    client.call("POST", "/api/register", {"name": name, "password": game + " synthetic password"})
            sql("UPDATE games.users SET credits = 123 WHERE name_key = 'sharedplayer'; INSERT INTO games.game_stats SELECT id, 'ono', 3, 1 FROM games.users WHERE name_key = 'sharedplayer'; UPDATE slots.users SET stake = 543210, wallet = jsonb_set(wallet, '{stake}', '543210') WHERE name_key = 'sharedplayer'; INSERT INTO slots.game_stats (user_id, game, rounds, wagered, won, best_mult, best_payout) SELECT id, 'dice', 2, 100, 200, 2, 200 FROM slots.users WHERE name_key = 'sharedplayer';")
            try:
                link.authenticate(origins["slots"], "SharedPlayer", "incorrect synthetic password", "slots_session", fixture=True)
                raise AssertionError("Wrong Slots password created a proof")
            except ValueError:
                pass
            hashes = [link.authenticate(origins[g], "SharedPlayer", g + " synthetic password", g + "_session", fixture=True) for g in ("games", "slots")]
            proof = tmp / "proof.csv"
            link.save_proof(proof, "SharedPlayer", *hashes)
            check(proof.stat().st_mode & 0o777 == 0o600, "Proof file is not private")
            try:
                link.save_proof(proof, "SharedPlayer", *hashes)
                raise AssertionError("Existing proof was overwritten")
            except FileExistsError:
                pass
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
            check("2|2|1|1" in sql(file=migration / "preflight.sql"), "Collision preflight is incorrect")
            sql(file=migration / "merge.sql", succeeds=False)
            check(sql("SELECT to_regnamespace('identity') IS NULL") == "t", "Rejected merge left a partial schema")
            with proof.open() as source:
                subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", "\\copy migration.links FROM STDIN WITH (FORMAT csv)"], env=env, stdin=source, check=True, stdout=subprocess.DEVNULL)
            # Password changes revoke old proofs through their revoked sessions.
            sql("UPDATE slots.sessions SET expires_at = 0 WHERE token_hash IN (SELECT slots_token_hash FROM migration.links)")
            sql(file=migration / "merge.sql", succeeds=False)
            sql("UPDATE slots.sessions SET expires_at = (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT + 3600000 WHERE token_hash IN (SELECT slots_token_hash FROM migration.links)")
            check("2|2|1|0" in sql(file=migration / "preflight.sql"), "Verified proof was not accepted")
            sql(file=migration / "merge.sql")
            sql(file=migration / "merge.sql")
            check(sql("SELECT COUNT(*) FROM identity.users") == "3", "Account conservation failed")
            check(sql("SELECT credits, stake, wallet->>'stake' FROM identity.users WHERE name_key = 'sharedplayer'") == "123|543210|543210", "A balance was changed during merge")
            check(sql("SELECT COUNT(*) FROM slots.game_stats s JOIN games.game_stats g USING(user_id) WHERE s.game = 'dice' AND g.game = 'ono' AND s.rounds = 2 AND g.played = 3") == "1", "Stats or account references were lost")
            check(sql("SELECT COUNT(*) FROM identity.account_links") == "4", "Source ID provenance was lost")
            check(sql("SELECT COUNT(*) FROM identity.sessions") == "0", "Old sessions survived cutover")
            origins = {game: start(game, True, tmp) for game in binaries}
            shared_clients = {game: Client(origin) for game, origin in origins.items()}
            for client in shared_clients.values():
                client.call("POST", "/api/login", {"name": "SharedPlayer", "password": "games synthetic password"})
            for source, other in (("games", "slots"), ("slots", "games")):
                Client(origins[other]).call("POST", "/api/login", {"name": source.capitalize() + "Only", "password": source + " synthetic password"})
            Client(origins["slots"]).call("POST", "/api/login", {"name": "SharedPlayer", "password": "slots synthetic password"}, status=401)
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
            shared_clients["games"].call("POST", "/api/account/password", {"old": "games synthetic password", "new": "changed common password"})
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "SharedPlayer", "password": "changed common password"})
            codes = shared_clients["games"].call("POST", "/api/account/recovery-codes", {"password": "changed common password"})["recoveryCodes"]
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "SharedPlayer", "password": "changed common password"})
            # Request fields follow the recovery API; no code is logged or saved.
            Client(origins["games"]).call("POST", "/api/reset", {"name": "SharedPlayer", "code": codes[0], "password": "recovered common password"})
            Client(origins["games"]).call("POST", "/api/reset", {"name": "SharedPlayer", "code": codes[0], "password": "another common password"}, status=400)
            shared_clients["slots"].call("GET", "/api/me", status=401)
            shared_clients["slots"].call("POST", "/api/login", {"name": "SharedPlayer", "password": "recovered common password"})
            stop()
            backup = tmp / "synthetic.dump"
            subprocess.run(["pg_dump", "--format=custom", "--file", str(backup)], env=env, check=True)
            restored = database + "_restored"
            subprocess.run(["createdb", restored], check=True)
            databases.append(restored)
            env["PGDATABASE"] = restored
            subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", restored, str(backup)], env=env, check=True)
            sql(file=migration / "merge.sql")  # Must be a no-op after a restore, too.
            for game in binaries:
                client = Client(start(game, True, tmp))
                client.call("POST", "/api/login", {"name": "SharedPlayer", "password": "recovered common password"})
            check(sql("SELECT credits, stake FROM identity.users WHERE name_key = 'sharedplayer'") == "123|543210", "Restore lost game balances")
            print("PASS: double-password proofs, atomic rejection, conservation, idempotence, both app logins, registration races, wallet/stats, global session revocation and isolated dump/restore")
    finally:
        stop()
        for disposable in reversed(databases):
            subprocess.run(["dropdb", "--if-exists", disposable], env=os.environ, check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
