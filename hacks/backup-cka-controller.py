"""Private, consistency-checked CKA state snapshot into the backed-up retained home."""
import base64,hashlib,json,os,subprocess,time
from pathlib import Path
os.umask(0o077)
remote=r'''
import base64,hashlib,json,os,re,sqlite3,tempfile
from pathlib import Path
os.umask(0o077)
root=Path("/data")
db=sqlite3.connect(root/"runtime/control.sqlite")
def stamp():
    assert db.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]==0,"Wait for the lifecycle operation to finish"
    return db.execute("select count(*) from jobs").fetchone()[0]
before=stamp()
state=(root/"terraform.tfstate").read_bytes()
with tempfile.TemporaryDirectory() as temp:
    dest=sqlite3.connect(Path(temp)/"control.sqlite")
    db.backup(dest);dest.close()
    snapshot=sqlite3.connect(Path(temp)/"control.sqlite")
    raw=snapshot.execute("select lab from state where id=1").fetchone()[0]
    lab=json.loads(raw) if raw else None
    snapshot.close()
    files={"terraform.tfstate":state,"runtime/control.sqlite":(Path(temp)/"control.sqlite").read_bytes()}
    if lab:
        identity=lab["id"]
        assert re.fullmatch(r"[a-f0-9-]{36}",identity)
        for name in ("gateway_key","gateway_key.pub","node_key","node_key.pub","known_hosts","ssh_config","scenario-started","scenario-ready","lab.auto.tfvars.json"):
            source=root/"runtime"/identity/name
            if source.exists():files["runtime/"+identity+"/"+name]=source.read_bytes()
    assert before==stamp() and state==(root/"terraform.tfstate").read_bytes(),"State changed during snapshot; retry"
    print(json.dumps({"version":1,"files":{name:base64.b64encode(value).decode() for name,value in files.items()},"checksums":{name:hashlib.sha256(value).hexdigest() for name,value in files.items()}}))
'''
result=subprocess.run(["kubectl","--context","labprod","-n","cka","exec","deployment/cka","-c","controller","--","python3","-c",remote],capture_output=True)
if result.returncode:raise SystemExit("Snapshot refused; wait for the lab lifecycle to become idle and retry. No state was displayed.")
payload=json.loads(result.stdout)
for name,value in payload["files"].items():
    assert hashlib.sha256(base64.b64decode(value,validate=True)).hexdigest()==payload["checksums"][name]
target=Path(os.environ.get("CKA_BACKUP_DIRECTORY","/home/coder/projects/labops/terraform/cka-ui/.runtime/production-backups"))
target.mkdir(mode=0o700,parents=True,exist_ok=True)
path=target/(time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+".json")
with path.open("x") as output:json.dump(payload,output)
os.chmod(path,0o600)
print("Private CKA snapshot verified and saved in retained-home backup scope; values withheld.")
