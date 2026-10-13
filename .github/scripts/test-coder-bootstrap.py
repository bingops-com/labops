"""Run the real installer against disposable Coder/PostgreSQL containers."""

import base64
import importlib.util
import os
from pathlib import Path


spec = importlib.util.spec_from_file_location("bootstrap", "/scripts/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
bootstrap.BASE = "http://coder:8080"


def kubernetes(path):
    if path == "/api/v1/namespaces/coder-workspaces/serviceaccounts/coder-bootstrap":
        return {"metadata": {"uid": "acceptance-installation"}}
    if path == "/api/v1/namespaces/coder/secrets/coder-postgresql-app":
        return {"data": {"uri": base64.b64encode(os.environ["TEST_DATABASE_URI"].encode()).decode()}}
    raise AssertionError(f"Unexpected Kubernetes access: {path}")


bootstrap.kubernetes = kubernetes
phase = os.environ["TEST_PHASE"]
marker = Path("/data/.config/lab/bootstrap.json")
if phase == "initial":
    bootstrap.main()
    assert marker.exists()
elif phase == "repeat":
    previous = marker.read_bytes()
    bootstrap.main()
    assert marker.read_bytes() == previous, "An unchanged setup rewrote its state"
elif phase == "update":
    with Path("/opt/lab-template/main.tf").open("a") as template:
        template.write("\n# acceptance definition update\n")
    bootstrap.main()
else:
    raise AssertionError("Unknown acceptance phase")
