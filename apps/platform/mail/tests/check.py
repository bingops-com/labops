#!/usr/bin/env python3
"""Exercise real Postfix locally; an internal Docker network prevents delivery."""
import hashlib
import json
import pathlib
import secrets
import ssl
import subprocess
import sys
import tempfile
import time
import uuid

if len(sys.argv) != 2:
    sys.exit("usage: check.py LOCAL_IMAGE")
image = sys.argv[1]
root = pathlib.Path(__file__).resolve().parents[4]
overlay = root / "apps/platform/mail/labprod"
name = "postfix-check-" + uuid.uuid4().hex[:12]
network, volume = name + "-net", name + "-queue"
password = secrets.token_urlsafe(32)


def run(*args, report_error=True, **kwargs):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()
    except subprocess.CalledProcessError as error:
        if report_error:
            print((error.stdout + error.stderr).replace(password, "[synthetic credential]"), file=sys.stderr)
        raise


def docker(*args, **kwargs):
    return run("docker", *args, **kwargs)


def openssl(*args):
    run("openssl", *args)


with tempfile.TemporaryDirectory(prefix="postfix-check-") as temp:
    scratch = pathlib.Path(temp)
    tls, dkim = scratch / "tls", scratch / "dkim"
    tls.mkdir()
    dkim.mkdir(mode=0o755)
    certificate, key = tls / "tls.crt", tls / "tls.key"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=smtp.games.lab.bingo",
            "-addext", "subjectAltName=DNS:smtp.games.lab.bingo")
    dkim_key = dkim / "games.lab.bingo.private"
    openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(dkim_key))
    # Synthetic key only; let the container's service UID read the bind mount.
    dkim_key.chmod(0o444)
    settings = {}
    for line in (overlay / "runtime.yaml").read_text().split("data:\n", 1)[1].splitlines():
        if line.startswith("  ") and not line.lstrip().startswith("#"):
            field, value = line.strip().split(":", 1)
            settings[field] = value.strip().strip("\"'")
    settings["SMTPD_SASL_USERS"] = "games@games.lab.bingo:" + password
    # No external DNS or delivery: authentication is still enforced by relay restrictions.
    settings["POSTFIX_smtpd_recipient_restrictions"] = "permit_sasl_authenticated,reject"
    settings["POSTFIX_defer_transports"] = "smtp"
    env_file = scratch / "smtp.env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in settings.items()) + "\n")
    env_file.chmod(0o600)

    def create():
        args = ["run", "-d", "--name", name, "--network", network,
                "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
        for capability in ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID", "SYS_CHROOT"]:
            args += ["--cap-add", capability]
        args += ["--env-file", str(env_file), "--entrypoint", "/bin/bash",
                 "--mount", f"type=bind,src={tls},dst=/etc/postfix/tls,readonly",
                 "--mount", f"type=bind,src={dkim},dst=/etc/opendkim/keys,readonly",
                 "--mount", f"type=bind,src={overlay / 'run.sh'},dst=/opt/labops/run.sh,readonly",
                 "--mount", f"type=volume,src={volume},dst=/var/spool/postfix",
                 image, "/opt/labops/run.sh"]
        docker(*args)
        return json.loads(docker("inspect", name))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]

    def ready(port):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = subprocess.run(["docker", "exec", name, "/scripts/healthcheck.sh"], capture_output=True, timeout=8)
            if result.returncode == 0:
                return
            time.sleep(1)
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        print((logs.stdout + logs.stderr)[-6000:].replace(password, "[synthetic credential]"))
        raise RuntimeError("Postfix did not become ready")

    def client(port, mode):
        client_script = overlay.parent / "tests/client.py"
        return docker("run", "--rm", "--network", network, "--env-file", str(env_file),
                      "--env", "SMTP_TEST_ADDRESS=" + port, "--env", "SMTP_TEST_MODE=" + mode,
                      "--mount", f"type=bind,src={certificate},dst=/test/ca.crt,readonly",
                      "--mount", f"type=bind,src={client_script},dst=/test/client.py,readonly",
                      "--entrypoint", "python3", image, "/test/client.py", report_error=mode != "fingerprint")

    def queued():
        return [json.loads(line) for line in docker("exec", name, "postqueue", "-j").splitlines() if line]

    try:
        docker("network", "create", "--internal", network)
        docker("volume", "create", volume)
        port = create()
        ready(port)
        print(client(port, "submit"), flush=True)
        queue = queued()
        assert len(queue) == 1, "authenticated message not queued"
        queue_id = queue[0]["queue_id"]
        message = docker("exec", name, "postcat", "-q", queue_id)
        assert "DKIM-Signature:" in message and "d=games.lab.bingo" in message, "DKIM signature missing"
        assert "s=games1" in message, "incorrect DKIM selector"
        print("PASS: authenticated message queued and signed with DKIM", flush=True)

        replacement = tls / "replacement.crt"
        openssl("req", "-x509", "-key", str(key), "-days", "2", "-out", str(replacement),
                "-subj", "/CN=smtp.games.lab.bingo", "-addext", "subjectAltName=DNS:smtp.games.lab.bingo")
        replacement.replace(certificate)
        expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest()
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            try:
                if client(port, "fingerprint") == expected:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(1)
        else:
            raise AssertionError("renewed certificate not loaded")
        print("PASS: renewed TLS certificate reloaded automatically", flush=True)
        docker("stop", "--time", "15", name)
        docker("rm", name)
        port = create()
        ready(port)
        assert queue_id in [item["queue_id"] for item in queued()], "queued mail lost after replacement"
        print("PASS: queue survives container replacement; no external mail delivered", flush=True)
    finally:
        for args in [("rm", "-f", name), ("volume", "rm", volume), ("network", "rm", network)]:
            subprocess.run(["docker", *args], capture_output=True, check=False)
