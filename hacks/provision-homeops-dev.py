#!/usr/bin/env python3
"""Stream operator client access to the retained workspace; never display it."""
import argparse
import json
from pathlib import Path
import subprocess


INSTALL = '''import json,os,pathlib,tempfile,sys
payload=json.load(sys.stdin)
home=pathlib.Path("/home/coder")
for relative,content in payload.items():
    target=home/relative
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if target.parent.is_symlink() or target.is_symlink():
        raise SystemExit("Refusing a symlinked credential destination")
    target.parent.chmod(0o700)
    descriptor,name=tempfile.mkstemp(prefix=".homeops-",dir=target.parent)
    try:
        with os.fdopen(descriptor,"w") as stream:
            stream.write(json.dumps(content)+"\\n")
        os.chmod(name,0o600)
        os.replace(name,target)
    finally:
        if os.path.exists(name): os.unlink(name)
    default=target.parent/"config"
    if not os.path.lexists(default): default.symlink_to(target.name)
print("Operator client configuration installed privately; existing default files preserved")
'''


def run(arguments, input_data=None):
    result = subprocess.run(arguments, input=input_data, capture_output=True, timeout=90)
    if result.returncode:
        # Neither stderr nor stdout is safe to log for a credential operation.
        raise RuntimeError(f"Client configuration command failed (exit {result.returncode}); no credential output was displayed")
    return result.stdout


def kubeconfig(contexts):
    merged = {"apiVersion": "v1", "kind": "Config", "clusters": [], "users": [], "contexts": [], "current-context": "labprod"}
    for context in contexts:
        document = json.loads(run(["kubectl", "--context", context, "config", "view", "--minify", "--flatten", "--raw", "-o", "json"]))
        selected = document["contexts"][0]["context"]
        cluster = next(item["cluster"] for item in document["clusters"] if item["name"] == selected["cluster"])
        user = next(item["user"] for item in document["users"] if item["name"] == selected["user"])
        if any(key in user for key in ("exec", "auth-provider")):
            raise RuntimeError("Context requires a dynamic authentication plugin; configure it explicitly rather than copying an incomplete client")
        identity = "homeops-" + context
        merged["clusters"].append({"name": identity, "cluster": cluster})
        merged["users"].append({"name": identity, "user": user})
        merged["contexts"].append({"name": context, "context": {"cluster": identity, "user": identity, **({"namespace": selected["namespace"]} if "namespace" in selected else {})}})
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talos-config", type=Path, help="Optional existing operator Talos config; only labmgmt/labprod are transferred")
    args = parser.parse_args()
    payload = {".kube/homeops-config": kubeconfig(("labmgmt", "labprod"))}
    if args.talos_config:
        import yaml
        config = yaml.safe_load(args.talos_config.read_text())
        contexts = config.get("contexts", {})
        if not all(name in contexts for name in ("labmgmt", "labprod")):
            raise RuntimeError("Talos config must contain labmgmt and labprod")
        payload[".talos/homeops-config"] = {"context": "labprod", "contexts": {name: contexts[name] for name in ("labmgmt", "labprod")}}
    run(["kubectl", "--context", "labprod", "-n", "coder-workspaces", "exec", "-i", "deployment/coder-bingops-lab", "--", "python3", "-c", INSTALL], json.dumps(payload).encode())
    print("Transferred labmgmt/labprod operator access to retained home (0600); no new cluster or role created")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Provisioning failed; credentials were not displayed. Check source contexts and workspace readiness.") from None
