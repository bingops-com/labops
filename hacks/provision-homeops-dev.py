#!/usr/bin/env python3
"""Stream operator client access to the retained workspace; never display it."""
import argparse
import base64
import json
from pathlib import Path
import subprocess


INSTALL = '''import base64,json,os,pathlib,tempfile,sys
payload=json.load(sys.stdin)
home=pathlib.Path("/home/coder")
prepared=[]
for relative,content in payload.items():
    parts=pathlib.PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise SystemExit("Refusing an unsafe destination")
    target=home/parts
    for ancestor in (target,*target.parents):
        if ancestor==home: break
        if ancestor.is_symlink():
            raise SystemExit("Refusing a symlinked credential destination")
    raw=isinstance(content,dict) and set(content)=={"_file_base64"}
    # Rotation updates managed identities but keeps a still-valid user choice.
    if target.exists() and relative in (".kube/homeops-config",".talos/homeops-config"):
        import yaml
        previous=yaml.safe_load(target.read_text())
        field="current-context" if relative.startswith(".kube/") else "context"
        contexts=content.get("contexts",{})
        available={entry["name"] for entry in contexts} if isinstance(contexts,list) else set(contexts)
        if previous.get(field) in available: content[field]=previous[field]
    data=base64.b64decode(content["_file_base64"],validate=True) if raw else (json.dumps(content)+"\\n").encode()
    if relative.startswith("projects/labops/") and not (home/"projects/labops/.git").exists():
        raise SystemExit("Clone LabOps before enrolling project configuration")
    if raw and target.exists() and target.read_bytes()!=data:
        raise SystemExit("Existing operator file differs; refusing to overwrite")
    prepared.append((relative,target,data))
for relative,target,data in prepared:
    missing=[]
    parent=target.parent
    while parent!=home and not parent.exists():
        missing.append(parent)
        parent=parent.parent
    for directory in reversed(missing): directory.mkdir(mode=0o700)
    if not relative.startswith("projects/"): target.parent.chmod(0o700)
    descriptor,name=tempfile.mkstemp(prefix=".homeops-",dir=target.parent)
    try:
        with os.fdopen(descriptor,"wb") as stream: stream.write(data)
        os.chmod(name,0o600)
        os.replace(name,target)
    finally:
        if os.path.exists(name): os.unlink(name)
    if relative in (".kube/homeops-config",".talos/homeops-config",".ssh/homeops-config"):
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


def operator_files(home, root=None, proxmox_key=None, cli_sessions=False, aws_config=False, terraform_state=False):
    """Select HomeOps inputs explicitly; never collect the entire operator home."""
    files = {}

    def add(relative, source):
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Operator input must be a regular source file")
        files[relative] = {"_file_base64": base64.b64encode(source.read_bytes()).decode()}

    if proxmox_key:
        add(".ssh/homeops-proxmox", proxmox_key)
        known_hosts = Path(__file__).resolve().parents[1] / "apps/workloads/coder/base/proxmox_known_hosts"
        matches = run(["ssh-keygen", "-F", "192.168.1.100", "-f", str(known_hosts)]).decode()
        lines = [line for line in matches.splitlines() if line and not line.startswith("#")]
        if not lines:
            raise RuntimeError("Verify the Proxmox host key on the source operator host first")
        files[".ssh/homeops-known_hosts"] = {"_file_base64": base64.b64encode(("\n".join(lines) + "\n").encode()).decode()}
        config = "Host proxmox homelab 192.168.1.100\n  HostName 192.168.1.100\n  User bingo\n  IdentityFile ~/.ssh/homeops-proxmox\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\n  UserKnownHostsFile ~/.ssh/homeops-known_hosts\n"
        files[".ssh/homeops-config"] = {"_file_base64": base64.b64encode(config.encode()).decode()}
    if cli_sessions:
        for relative in (".config/gh/hosts.yml", ".codex/auth.json"):
            source = home / relative
            if source.exists():
                add(relative, source)
    if aws_config:
        for relative in (".aws/config", ".aws/credentials"):
            source = home / relative
            if source.exists():
                add(relative, source)
    if root:
        for relative in ("capi/credentials.env", "apps/platform/authentik/credentials/bootstrap-password"):
            source = root / relative
            if source.is_file():
                add("projects/labops/" + relative, source)
        for stack in ("proxmox", "cloudflare", "network"):
            directory = root / "terraform" / stack
            candidates = sorted(directory.glob("*.tfvars"))
            legacy = directory / "credentials"
            if legacy.is_file():
                candidates.append(legacy)
            if terraform_state:
                candidates.extend(path for path in (directory / "terraform.tfstate", directory / "terraform.tfstate.backup") if path.exists())
            for source in candidates:
                add("projects/labops/" + source.relative_to(root).as_posix(), source)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talos-config", type=Path, help="Optional existing operator Talos config; only labmgmt/labprod are transferred")
    parser.add_argument("--proxmox-key", type=Path, help="Existing operator SSH key for bingo@192.168.1.100; other SSH keys are excluded")
    parser.add_argument("--cli-sessions", action="store_true", help="Enroll existing GitHub/Codex file-based sessions")
    parser.add_argument("--aws-config", action="store_true", help="Enroll the operator AWS config/credentials files; SSO caches are excluded")
    parser.add_argument("--homeops-root", type=Path, help="Existing LabOps checkout; select ignored input files for the three Terraform stacks")
    parser.add_argument("--include-terraform-state", action="store_true", help="Move a snapshot of local Terraform state after choosing Coder as primary")
    parser.add_argument("--confirm-coder-primary", action="store_true", help="Confirm that subsequent Terraform operations will run only from Coder")
    args = parser.parse_args()
    if args.include_terraform_state and not (args.homeops_root and args.confirm_coder_primary):
        parser.error("Terraform state enrollment requires --homeops-root and --confirm-coder-primary")
    payload = {".kube/homeops-config": kubeconfig(("labmgmt", "labprod"))}
    if args.talos_config:
        import yaml
        config = yaml.safe_load(args.talos_config.read_text())
        contexts = config.get("contexts", {})
        if not all(name in contexts for name in ("labmgmt", "labprod")):
            raise RuntimeError("Talos config must contain labmgmt and labprod")
        payload[".talos/homeops-config"] = {"context": "labprod", "contexts": {name: contexts[name] for name in ("labmgmt", "labprod")}}
    payload.update(operator_files(Path.home(), args.homeops_root, args.proxmox_key, args.cli_sessions, args.aws_config, args.include_terraform_state))
    run(["kubectl", "--context", "labprod", "-n", "coder-workspaces", "exec", "-i", "deployment/coder-bingops-lab", "--", "python3", "-c", INSTALL], json.dumps(payload).encode())
    print("Selected operator access installed privately (0600); no new cluster or role created")
    if args.include_terraform_state:
        print("Coder is now the primary Terraform runner; retain source state for recovery and do not run Terraform from this PC")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Provisioning failed; credentials were not displayed. Check source contexts and workspace readiness.") from None
