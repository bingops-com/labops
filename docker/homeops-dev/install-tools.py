"""Install only verified, pinned upstream binaries; never extract entire archives."""
import hashlib
import io
import json
from pathlib import Path
import platform
import tarfile
import time
import urllib.request
import zipfile

if platform.machine() not in ("x86_64", "amd64"):
    raise SystemExit("homeops-dev currently supports Linux/amd64")

for tool in json.loads(Path("/opt/homeops-dev/tools.lock.json").read_text()):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(tool["url"], timeout=120) as response:
                data = response.read()
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)
    if hashlib.sha256(data).hexdigest() != tool["sha256"]:
        raise RuntimeError("Upstream checksum mismatch: " + tool["name"])
    if tool["archive"] == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = archive.read(tool["member"])
    elif tool["archive"] == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = archive.getmember(tool["member"])
            if not member.isfile():
                raise RuntimeError("Expected a regular binary")
            data = archive.extractfile(member).read()
    destination = Path("/usr/local/bin") / tool["name"]
    destination.write_bytes(data)
    destination.chmod(0o755)
    print("Installed " + tool["name"] + " " + tool["version"], flush=True)
