"""Run the real installer against disposable Coder/PostgreSQL containers."""

import base64
import importlib.util
import os
from pathlib import Path


spec = importlib.util.spec_from_file_location("bootstrap", "/scripts/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
bootstrap.BASE = "http://coder:8080"
# Host cleanup must work when the CI runner UID differs from the image UID.
os.umask(0)


def kubernetes(path):
    if path == "/api/v1/namespaces/coder-workspaces/serviceaccounts/coder-bootstrap":
        return {"metadata": {"uid": "acceptance-installation"}}
    if path == "/api/v1/namespaces/coder/secrets/coder-postgresql-app":
        return {"data": {"uri": base64.b64encode(os.environ["TEST_DATABASE_URI"].encode()).decode()}}
    raise AssertionError(f"Unexpected Kubernetes access: {path}")


bootstrap.kubernetes = kubernetes
phase = os.environ["TEST_PHASE"]
marker = Path("/data/.config/lab/bootstrap.json")
bootstrap.wait_for_server()
methods = bootstrap.API().call("/api/v2/users/authmethods")
assert methods["github"]["enabled"] is False, "GitHub login must be disabled"
assert methods["password"]["enabled"] is False, "Password login must remain disabled"
assert methods["oidc"]["enabled"] is True, "OIDC login must remain enabled"
if phase == "kubernetes_initial":
    bootstrap.main()
    assert marker.exists()
elif phase == "initial_failure":
    try:
        bootstrap.main()
    except RuntimeError:
        assert not marker.exists(), "A failed start was marked complete"
    else:
        raise AssertionError("The fixture must fail its initial workspace start")
elif phase == "initial":
    template = Path("/opt/lab-template/main.tf")
    definition = template.read_text()
    start = definition.index('resource "terraform_data" "initial_failure"')
    end = definition.index('output "workspace_name"', start)
    template.write_text(definition[:start] + definition[end:])
    bootstrap.main()
    assert marker.exists()
elif phase == "repeat":
    previous = marker.read_bytes()
    bootstrap.main()
    assert marker.read_bytes() == previous, "An unchanged setup rewrote its state"
elif phase == "update":
    previous = bootstrap.desired_state()["hash"]
    # A tool-settings-only edit must import a new active template too.
    with Path("/opt/lab-template/codex.toml").open("a") as template:
        template.write("\n# acceptance definition update\n")
    assert bootstrap.desired_state()["hash"] != previous, "A tool config edit did not change the desired template"
    bootstrap.main()
else:
    raise AssertionError("Unknown acceptance phase")
