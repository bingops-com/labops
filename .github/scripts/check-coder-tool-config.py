"""Check effective tool settings and execute a synthetic Codex command without a model."""

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


def check_codex():
    server = subprocess.Popen(
        ["codex", "app-server", "--stdio", "--strict-config"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=0, start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(server.stdout, selectors.EVENT_READ)
    pending = b""

    def request(identifier, method, params):
        nonlocal pending
        server.stdin.write((json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode())
        server.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                response = json.loads(line)
                if response.get("id") == identifier:
                    assert "error" not in response, f"Codex RPC failed: {method}"
                    return response["result"]
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(server.stdout.fileno(), 65536)
            if not chunk:
                raise AssertionError("Codex app-server exited before replying")
            pending += chunk
        raise AssertionError(f"Codex RPC timed out: {method}")

    try:
        request(1, "initialize", {"clientInfo": {"name": "homeops-acceptance", "version": "1"}, "capabilities": {"experimentalApi": True}})
        config = request(2, "config/read", {"includeLayers": False})["config"]
        assert config.get("sandbox_mode") == "danger-full-access", "Effective Codex mode is not full access"
        assert config.get("approval_policy") == "never", "Effective Codex approval policy differs"
        assert config.get("check_for_update_on_startup") is False, "Codex updates are not image-managed"
        # No sandboxPolicy override: exercise the loaded defaults, not a test-only bypass.
        result = request(3, "command/exec", {"command": ["/usr/bin/printf", "HOMEOPS_CONFIG_OK"], "timeoutMs": 5000})
        assert result["exitCode"] == 0 and result["stdout"] == "HOMEOPS_CONFIG_OK", "Codex command execution failed"
    finally:
        selector.close()
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        server.stdin.close()
        server.stdout.close()


if __name__ == "__main__":
    settings = json.loads(Path("/etc/claude-code/managed-settings.json").read_text())
    assert settings["env"]["DISABLE_AUTOUPDATER"] == "1"
    assert Path("/etc/tmux.conf").is_file()
    check_codex()
    print("GitOps tool settings and Codex execution verified without account or model requests.")
