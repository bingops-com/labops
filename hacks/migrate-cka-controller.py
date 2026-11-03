"""One-time, fail-closed Coder -> production state adoption. No state is printed."""
import base64,hashlib,json,os,sqlite3,subprocess,time
from pathlib import Path
os.umask(0o077)
source=Path(os.environ.get("CKA_RETIRED_ROOT","/home/coder/projects/labops/terraform/cka-ui"))
def kubectl(args,body=None):
    result=subprocess.run(["kubectl","--context","labprod"]+args,input=body,capture_output=True)
    if result.returncode:raise SystemExit("Kubernetes operation failed; state was not displayed.")
    return result.stdout
pods=json.loads(kubectl(["-n","cka","get","pods","-l","app=cka","-o","json"]))["items"]
pods=[p for p in pods if not p["metadata"].get("deletionTimestamp")]
if len(pods)!=1:raise SystemExit("Exactly one CKA pod must exist.")
pod=pods[0]["metadata"]["name"]
db=sqlite3.connect(source/".runtime/control.sqlite")
assert db.execute("select lab from state where id=1").fetchone()[0] is None,"Active lab; transfer refused"
assert db.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]==0,"Active jobs; transfer refused"
state=json.loads((source/"terraform.tfstate").read_text())
assert not any(r["type"]=="proxmox_virtual_environment_vm" and r["instances"] for r in state.get("resources",[])),"Guest VM state still present"
# Fence any future local restart before stopping the current idle process.
controller=source/"runner/control.py"
code=controller.read_text()
guard='    if (ROOT / ".runtime/ownership-moved").exists():\n        raise SystemExit("State ownership moved to production; this controller is retired.")\n'
if guard not in code:controller.write_text(code.replace('def main():\n','def main():\n'+guard))
marker=source/".runtime/ownership-moved"
if marker.exists():raise SystemExit("Already fenced; inspect production before any further migration.")
marker.write_text("Production cka/cka-controller owns state; do not start this retired controller.\n")
stopped=subprocess.run(["screen","-S","cka-lab-controller","-X","quit"],capture_output=True)
time.sleep(1)
for process in Path("/proc").iterdir():
    if not process.name.isdigit():continue
    try:args=(process/"cmdline").read_bytes().split(b"\0")
    except (OSError,PermissionError):continue
    if args and b"python" in Path(os.fsdecode(args[0])).name.encode() and any(os.fsencode(str(controller))==a for a in args):
        raise SystemExit("Old controller remains alive; migration refused.")
# Recheck after fencing and take SQLite online backup.
assert db.execute("select lab from state where id=1").fetchone()[0] is None
assert db.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]==0
snapshot=source/".runtime/retired-production-snapshot"
snapshot.mkdir(mode=0o700,exist_ok=False)
backup=sqlite3.connect(snapshot/"control.sqlite")
db.backup(backup);backup.close();db.close()
(snapshot/"terraform.tfstate").write_bytes((source/"terraform.tfstate").read_bytes())
payload={name:base64.b64encode((snapshot/name).read_bytes()).decode() for name in ("control.sqlite","terraform.tfstate")}
receiver=r'''
import base64,hashlib,json,os,sqlite3,sys
from pathlib import Path
os.umask(0o077)
data=Path("/data")
assert not (data/"migration-complete").exists(),"Already adopted"
assert not (data/"terraform.tfstate").exists(),"Target state not empty"
runtime=data/"runtime"
runtime.mkdir(mode=0o700,exist_ok=True)
assert not (runtime/"control.sqlite").exists(),"Target database not empty"
payload=json.load(sys.stdin)
assert set(payload)=={"control.sqlite","terraform.tfstate"}
for name,dest in [("control.sqlite",runtime/"control.sqlite"),("terraform.tfstate",data/"terraform.tfstate")]:
    raw=base64.b64decode(payload[name],validate=True)
    dest.write_bytes(raw)
    assert hashlib.sha256(dest.read_bytes()).digest()==hashlib.sha256(raw).digest()
state=json.loads((data/"terraform.tfstate").read_text())
db=sqlite3.connect(runtime/"control.sqlite")
assert db.execute("select lab from state where id=1").fetchone()[0] is None
assert db.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]==0
db.close()
(data/"migration-complete").write_text("Adopted existing state from fenced retained-home controller.\n")
print("Adopted existing Terraform and SQLite state; old controller fenced.")
'''
print(kubectl(["-n","cka","exec","-i",pod,"-c","controller","--","python3","-c",receiver],json.dumps(payload).encode()).decode().strip())
