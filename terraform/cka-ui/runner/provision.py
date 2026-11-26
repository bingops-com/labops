"""Fixed-scope lifecycle executor, loaded only with --enable-actions.

Every subprocess uses argv, never shell=True. User console input is stdin to
bash INSIDE an attributed VM over pinned SSH; it is never a host command.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import urllib.request

VM_NAMES = {700: "cka-gateway", 710: "cka-cp-1", 711: "cka-cp-2", 712: "cka-cp-3", 720: "cka-worker-1", 721: "cka-worker-2", 722: "cka-worker-3"}
OPERATOR = ["ssh", "-i", os.environ.get("CKA_PROXMOX_SSH_KEY",str(Path.home()/".ssh/homeops-proxmox")), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile="+os.environ.get("CKA_PROXMOX_KNOWN_HOSTS",str(Path.home()/".ssh/known_hosts")), os.environ.get("CKA_PROXMOX_SSH_TARGET","bingo@192.168.1.100")]


class Executor:
    def __init__(self, root, runtime, credentials, ca):
        self.root, self.runtime = Path(root), Path(runtime)
        self.credentials, self.ca = Path(credentials), Path(ca)
        self.labops = self.root.parents[1]
        self.content = Path(os.environ.get("CKA_LABS_CONTENT",str(self.labops.parent/"cka/content/labs.json")))
        self.env = {**os.environ, "SSL_CERT_FILE": str(self.ca), "TF_IN_AUTOMATION": "1"}

    def run(self, argv, *, stdin=None, timeout=60, cwd=None):
        result = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout, cwd=cwd, env=self.env)
        if result.returncode:
            # Private diagnostics only. Do not expose exception text, arguments,
            # API response, Terraform output or join tokens to web clients.
            with (self.runtime/"executor-errors.log").open("ab") as log:
                log.write(("\nCommand category: "+Path(argv[0]).name+"\n").encode())
                log.write(("Return code: "+str(result.returncode)+"\n").encode())
                log.write(result.stdout[-32768:])
                log.write(result.stderr[-32768:])
            raise RuntimeError("L’opération du contrôleur a échoué.")
        return result.stdout

    def directory(self, lab):
        if not re.fullmatch(r"[a-f0-9-]{36}", lab["id"]):
            raise RuntimeError("Identité de lab invalide.")
        path = self.runtime/lab["id"]
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    def assert_vm(self, lab, vmid):
        # Verify live identity through the trusted operator path before any
        # guest-agent call, including host-key enrollment.
        if vmid not in lab["vmids"] or vmid not in VM_NAMES:
            raise RuntimeError("VM non autorisée.")
        raw = self.run(OPERATOR+[f"sudo qm config {vmid}"], timeout=20).decode()
        if f"name: {VM_NAMES[vmid]}\n" not in raw or f"CKA-UI {lab['id']};" not in raw or "cka-ui" not in raw:
            raise RuntimeError("L’identité Proxmox ne correspond pas au lab.")

    def pin(self, lab, vmid, alias):
        self.assert_vm(lab, vmid)
        deadline = time.monotonic()+900
        while time.monotonic()<deadline:
            try:
                output = self.run(OPERATOR+[f"sudo qm guest exec {vmid} -- /usr/bin/cat /etc/ssh/ssh_host_ed25519_key.pub"], timeout=25)
                result = json.loads(output)
                key = result.get("out-data", "").strip()
                if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\n]*)?", key):
                    raise RuntimeError("Clé publique absente.")
                with (self.directory(lab)/"known_hosts").open("a") as known:
                    known.write(alias+" "+" ".join(key.split()[:2])+"\n")
                return
            except Exception:
                time.sleep(5)
        raise RuntimeError("L’agent invité n’est pas disponible.")

    def ssh(self, lab, target, script, *, timeout=60, root=True):
        if target not in [n["name"] for n in lab["nodes"]]+["cka-gateway"]:
            raise RuntimeError("Cible SSH non autorisée.")
        return self.run(["ssh", "-F", str(self.directory(lab)/"ssh_config"), target, "sudo bash -s" if root else "bash -s"], stdin=script.encode(), timeout=timeout)

    def vars(self, lab, start):
        path = self.directory(lab)
        value = {"lab": {"id": lab["id"], "start_nodes": start, "gateway_public_key": (path/"gateway_key.pub").read_text().strip(), "node_public_key": (path/"node_key.pub").read_text().strip(), "nodes": {n["name"]: {"vmid": n["vmid"], "ip": n["ip"], "role": n["role"]} for n in lab["nodes"]}}}
        target = path/"lab.auto.tfvars.json"
        target.write_text(json.dumps(value))
        os.chmod(target, 0o600)
        return target

    def terraform(self, action, lab, stage, *, start=False):
        path = self.directory(lab)
        variables = self.vars(lab, start)
        plan = path/("destroy.tfplan" if action=="destroy" else "create.tfplan")
        args = ["terraform", f"-chdir={self.root}"]
        stage("Vérification du plan Terraform privé")
        targets = ["-destroy", "-target=proxmox_virtual_environment_vm.guest", "-target=proxmox_virtual_environment_file.cloud_init", "-target=proxmox_virtual_environment_file.network"] if action=="destroy" else []
        self.run(args+["plan", "-input=false", "-no-color", f"-var-file={self.credentials}", f"-var-file={variables}", f"-out={plan}"]+targets, timeout=600)
        change = json.loads(self.run(args+["show", "-json", str(plan)], timeout=60))
        for item in change.get("resource_changes", []):
            actions = item["change"]["actions"]
            if actions==["no-op"]:
                continue
            if item["type"]=="proxmox_virtual_environment_vm":
                vm = item["change"].get("before") or item["change"].get("after")
                if vm.get("vm_id") not in lab["vmids"] or vm.get("name")!=VM_NAMES[vm["vm_id"]]:
                    raise RuntimeError("Le plan cible une VM inattendue.")
            if action!="destroy" and "delete" in actions:
                raise RuntimeError("La création ne doit supprimer aucune ressource.")
            if action=="destroy" and (actions!=["delete"] or item["type"] not in {"proxmox_virtual_environment_vm", "proxmox_virtual_environment_file"}):
                raise RuntimeError("La suppression doit rester limitée aux VM et snippets de la session.")
            if action=="destroy" and item["type"]=="proxmox_virtual_environment_file":
                before=item["change"].get("before") or {}
                if lab["id"] not in before.get("id",""):
                    raise RuntimeError("Le snippet ne correspond pas à la session confirmée.")
            if item["type"] not in {"proxmox_virtual_environment_vm", "proxmox_virtual_environment_file", "proxmox_virtual_environment_pool", "proxmox_download_file", "proxmox_storage_directory"}:
                raise RuntimeError("Type de ressource inattendu.")
        stage("Destruction des ressources du lab" if action=="destroy" else "Provisionnement des VM du lab")
        self.run(args+["apply", "-input=false", "-no-color", str(plan)], timeout=1200)

    def legacy_destroy(self, lab, stage):
        from control import LEGACY
        if lab["id"]!="legacy-cka" or any(v not in LEGACY for v in lab["vmids"]):
            raise RuntimeError("Destruction historique non autorisée.")
        root = self.labops/"terraform/cka"
        plan = self.runtime/"legacy-destroy.tfplan"
        args = ["terraform", f"-chdir={root}"]
        targets = ['-target=proxmox_virtual_environment_vm.node["'+LEGACY[v]+'"]' for v in lab["vmids"]]
        stage("Vérification du plan limité aux VM historiques confirmées")
        self.run(args+["plan", "-destroy", "-input=false", "-no-color", f"-var-file={self.credentials}", f"-out={plan}"]+targets, timeout=600)
        change = json.loads(self.run(args+["show", "-json", str(plan)]))
        actual = set()
        for item in change.get("resource_changes", []):
            actions = item["change"]["actions"]
            if actions==["no-op"]:
                continue
            before = item["change"].get("before") or {}
            if item["type"]!="proxmox_virtual_environment_vm" or actions!=["delete"] or before.get("vm_id") not in lab["vmids"] or before.get("name")!=LEGACY[before["vm_id"]]:
                raise RuntimeError("Le plan dépasse les VM historiques confirmées.")
            actual.add(before["vm_id"])
        if actual!=set(lab["vmids"]):
            raise RuntimeError("L’état Terraform ne possède pas exactement les VM attendues.")
        stage("Suppression des VM historiques et de leurs disques")
        self.run(args+["apply", "-input=false", "-no-color", str(plan)], timeout=600)

    def keys_and_config(self, lab):
        path = self.directory(lab)
        for name in ("gateway_key", "node_key"):
            if not (path/name).exists():
                self.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path/name)])
        config = "Host *\n  User ubuntu\n  BatchMode yes\n  IdentitiesOnly yes\n  ForwardAgent no\n  StrictHostKeyChecking yes\n  ConnectTimeout 10\n  ServerAliveInterval 10\n  ServerAliveCountMax 2\n  UserKnownHostsFile "+str(path/"known_hosts")+"\n"
        config += "Host cka-gateway\n  HostName 192.168.10.22\n  HostKeyAlias "+lab["id"]+"-gateway\n  IdentityFile "+str(path/"gateway_key")+"\n"
        for node in lab["nodes"]:
            config += "Host "+node["name"]+"\n  HostName "+node["ip"]+"\n  HostKeyAlias "+lab["id"]+"-"+node["name"]+"\n  IdentityFile "+str(path/"node_key")+"\n  ProxyJump cka-gateway\n"
        (path/"ssh_config").write_text(config)
        os.chmod(path/"ssh_config", 0o600)

    def create(self, lab, stage):
        self.keys_and_config(lab)
        stage("Installation du bridge privé et de la protection de l’hôte")
        self.run(OPERATOR+["sudo bash -s"], stdin=(self.root/"runner/host-network.sh").read_bytes(), timeout=60)
        self.terraform("create", lab, stage, start=False)
        stage("Vérification de l’identité et du démarrage de la passerelle")
        self.pin(lab, 700, lab["id"]+"-gateway")
        self.ssh(lab, "cka-gateway", "cloud-init status --wait\nnft list table inet cka_gateway >/dev/null\nsystemctl is-active haproxy\n", timeout=900)
        self.terraform("create", lab, stage, start=True)
        for node in lab["nodes"]:
            stage("Vérification du démarrage de "+node["name"])
            self.pin(lab, node["vmid"], lab["id"]+"-"+node["name"])
            self.ssh(lab, node["name"], "cloud-init status --wait\n", timeout=900)
        stage("Tests de refus réseau depuis les VM d’exercice")
        self.isolation(lab)
        if lab["profile"]=="ready":
            self.bootstrap(lab, stage)
        self.validate_cluster(lab,stage)
        self.initialize_exercise(lab,stage)
        stage("Vérifications finales du lab")

    def validate_cluster(self, lab, stage):
        first=next(n for n in lab["nodes"] if n["role"]=="control-plane")
        workers=[n for n in lab["nodes"] if n["role"]=="worker"]
        stage("Vérification fonctionnelle du cluster avant l’exercice")
        objects=[{"apiVersion":"v1","kind":"Namespace","metadata":{"name":"cka-platform-check"}}]
        for node in workers:
            for kind,image in (("web","nginx:1.28"),("client","busybox:1.37")):
                container={"name":kind,"image":image}
                if kind=="client":container["command"]=["sh","-c","while true; do sleep 3600; done"]
                objects.append({"apiVersion":"v1","kind":"Pod","metadata":{"name":kind+"-"+node["name"],"namespace":"cka-platform-check","labels":{"app":"platform-"+kind}},"spec":{"nodeName":node["name"],"containers":[container]}})
        objects.append({"apiVersion":"v1","kind":"Service","metadata":{"name":"web","namespace":"cka-platform-check"},"spec":{"selector":{"app":"platform-web"},"ports":[{"port":80,"targetPort":80}]}})
        script="set -eu\nexport KUBECONFIG=/etc/kubernetes/admin.conf\nkubectl wait --for=condition=Ready nodes --all --timeout=300s\nkubectl -n kube-system rollout status daemonset/calico-node --timeout=300s\nkubectl -n kube-system rollout status deployment/coredns --timeout=180s\nkubectl apply -f - <<'CKA_HEALTH'\n"+json.dumps({"apiVersion":"v1","kind":"List","items":objects})+"\nCKA_HEALTH\nkubectl -n cka-platform-check wait --for=condition=Ready pods --all --timeout=180s\n"
        for node in workers:
            prefix="kubectl -n cka-platform-check exec client-"+node["name"]+" -- "
            script+=prefix+"nslookup kubernetes.default >/dev/null\n"+prefix+"wget -T 5 -qO- http://web >/dev/null\n"
            for destination in workers:
                script+="address=$(kubectl -n cka-platform-check get pod web-"+destination["name"]+" -o jsonpath='{.status.podIP}')\n"+prefix+"wget -T 5 -qO- \"http://$address\" >/dev/null\n"
        self.ssh(lab,first["name"],script,timeout=900)

    def initialize_exercise(self, lab, stage):
        path=self.directory(lab)
        started=path/"scenario-started"
        ready=path/"scenario-ready"
        if ready.exists():
            if ready.read_text()!=lab["scenario"]:
                raise RuntimeError("Le scénario préparé ne correspond pas à la session.")
            return
        if started.exists():
            raise RuntimeError("Préparation partielle du scénario : intervention opérateur requise.")
        started.write_text(lab["scenario"])
        self.prepare(lab,stage)
        initial=self.verify(lab,stage)
        if initial["passed"]:
            raise RuntimeError("Le scénario ne présente pas l’état initial attendu.")
        ready.write_text(lab["scenario"])

    def start_assigned(self, lab, vmid):
        self.assert_vm(lab,vmid)
        state=self.run(OPERATOR+[f"sudo qm status {vmid}"],timeout=20).decode().strip()
        if state=="status: stopped":
            self.run(OPERATOR+[f"sudo qm start {vmid}"],timeout=90)
        elif state!="status: running":
            raise RuntimeError("État de VM incompatible avec une reprise sans remplacement.")

    def resume(self, lab, stage):
        # No Terraform call, reboot, VM replacement or cluster reset on retry.
        for vmid in lab["vmids"]:
            self.assert_vm(lab,vmid)
        stage("Reprise des vérifications de l’environnement")
        self.run(OPERATOR+["sudo bash -s"],stdin=(self.root/"runner/host-network.sh").read_bytes(),timeout=60)
        self.start_assigned(lab,700)
        self.pin(lab,700,lab["id"]+"-gateway")
        self.ssh(lab,"cka-gateway","set -eu\ncloud-init status --wait\nnft list table inet cka_gateway >/dev/null\nsystemctl is-active haproxy\n",timeout=600)
        for node in lab["nodes"]:
            self.start_assigned(lab,node["vmid"])
        for node in lab["nodes"]:
            self.pin(lab,node["vmid"],lab["id"]+"-"+node["name"])
            self.ssh(lab,node["name"],"cloud-init status --wait\n",timeout=600)
        self.isolation(lab)
        first=next(n for n in lab["nodes"] if n["role"]=="control-plane")
        state=self.ssh(lab,first["name"],"if test -f /etc/kubernetes/admin.conf; then echo initialized; else echo bare; fi\n").decode().strip()
        if state=="bare":
            self.bootstrap(lab,stage)
        else:
            for node in lab["nodes"]:
                self.ssh(lab,node["name"],(self.root/"templates/ensure-tools.sh").read_text(),timeout=180)
            # A partially joined cluster is kept reserved, never reset.
            expected=len(lab["nodes"])
            self.ssh(lab,first["name"],"set -eu\nexport KUBECONFIG=/etc/kubernetes/admin.conf\nkubectl get nodes -o json | python3 -c 'import json,sys; assert len(json.load(sys.stdin)[\"items\"])=="+str(expected)+"'\nkubectl wait --for=condition=Ready nodes --all --timeout=300s\n",timeout=360)
        self.validate_cluster(lab,stage)
        self.initialize_exercise(lab,stage)

    def isolation(self, lab):
        # Test both normal routing and a direct, on-link attack towards the
        # hypervisor IP. The learner may change routes and be root.
        host_mac = self.run(OPERATOR+["cat /sys/class/net/vmbr90/address"]).decode().strip()
        if not re.fullmatch(r"[0-9a-f:]{17}", host_mac):
            raise RuntimeError("MAC du bridge invalide.")
        script = """set -eu
for target in 192.168.1.100 192.168.10.1 192.168.10.150 192.168.10.151 192.168.10.160 169.254.169.254; do
 for port in 22 443 6443 8006; do
  if timeout 2 nc -z -w1 "$target" "$port"; then exit 21; fi
 done
done
if timeout 2 nc -z -w1 172.30.90.1 22; then exit 22; fi
ip route replace 192.168.1.100/32 dev eth0
ip neigh replace 192.168.1.100 lladdr HOST_MAC dev eth0 nud permanent
trap 'ip route del 192.168.1.100/32 dev eth0; ip neigh del 192.168.1.100 dev eth0' EXIT
for port in 22 8006; do
 if timeout 2 nc -z -w1 192.168.1.100 "$port"; then exit 23; fi
done
code=$(curl --silent --show-error --max-time 20 --output /dev/null --write-out "%{http_code}" https://registry.k8s.io/v2/)
case "$code" in 200|301|302|307|308|401) ;; *) exit 24;; esac
""".replace("HOST_MAC", host_mac)
        for node in lab["nodes"]:
            self.ssh(lab, node["name"], script, timeout=150)

    def bootstrap(self, lab, stage):
        import secrets
        for node in lab["nodes"]:
            stage("Installation de containerd et kubeadm sur "+node["name"])
            installed=self.ssh(lab,node["name"],'if test -f /etc/crictl.yaml && command -v crictl >/dev/null && test "$(kubeadm version -o short 2>/dev/null)" = v1.37.2 && systemctl is-active --quiet containerd; then echo ready; else echo install; fi\n').decode().strip()
            if installed!="ready":
                self.ssh(lab, node["name"], (self.root/"templates/node-base.sh").read_text(), timeout=900)
        first = next(n for n in lab["nodes"] if n["role"]=="control-plane")
        certificate_key = secrets.token_hex(32)
        config = f"""apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
certificateKey: {certificate_key}
localAPIEndpoint:
  advertiseAddress: {first['ip']}
nodeRegistration:
  name: {first['name']}
  criSocket: unix:///run/containerd/containerd.sock
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: v1.37.2
controlPlaneEndpoint: "172.30.90.1:6443"
networking:
  podSubnet: 10.240.0.0/16
  serviceSubnet: 10.112.0.0/12
apiServer:
  certSANs: ["172.30.90.1", "127.0.0.1"]
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
"""
        stage("Initialisation du premier control plane")
        self.ssh(lab, first["name"], "set -eu\numask 077\ncat >/root/cka-init.yaml <<'CKA_CONFIG'\n"+config+"CKA_CONFIG\nkubeadm init --config /root/cka-init.yaml --upload-certs >/root/cka-init.log 2>&1\ninstall -d -m700 -o ubuntu -g ubuntu /home/ubuntu/.kube\ninstall -m600 -o ubuntu -g ubuntu /etc/kubernetes/admin.conf /home/ubuntu/.kube/config\n", timeout=900)
        stage("Installation du réseau Calico avec NetworkPolicies")
        self.ssh(lab, first["name"], (self.root/"templates/install-calico.sh").read_text(), timeout=600)
        output = self.ssh(lab, first["name"], "kubeadm token create --ttl=30m --print-join-command\n").decode().strip()
        join = shlex.split(output)
        if len(join)!=7 or join[:3]!=["kubeadm", "join", "172.30.90.1:6443"] or join[3]!="--token" or not re.fullmatch(r"[a-z0-9]{6}\.[a-z0-9]{16}", join[4]) or join[5]!="--discovery-token-ca-cert-hash" or not re.fullmatch(r"sha256:[a-f0-9]{64}", join[6]):
            raise RuntimeError("Commande de jonction invalide.")
        for node in lab["nodes"]:
            if node==first:
                continue
            stage("Jonction de "+node["name"])
            command = output+" --node-name "+node["name"]
            if node["role"]=="control-plane":
                command += " --control-plane --certificate-key "+certificate_key+" --apiserver-advertise-address "+node["ip"]
            self.ssh(lab, node["name"], "set -eu\n"+command+" >/root/cka-join.log 2>&1\n"+("install -d -m700 -o ubuntu -g ubuntu /home/ubuntu/.kube\ninstall -m600 -o ubuntu -g ubuntu /etc/kubernetes/admin.conf /home/ubuntu/.kube/config\n" if node["role"]=="control-plane" else ""), timeout=900)
        stage("Attente des nœuds et du réseau Kubernetes")
        self.ssh(lab, first["name"], "export KUBECONFIG=/etc/kubernetes/admin.conf\nkubectl wait --for=condition=Ready nodes --all --timeout=600s\nkubectl -n kube-system rollout status daemonset/calico-node --timeout=600s\nkubectl -n kube-system rollout status deployment/coredns --timeout=300s\n", timeout=1000)

    def prepare(self, lab, stage):
        first = next(n for n in lab["nodes"] if n["role"]=="control-plane")
        worker = next(n for n in lab["nodes"] if n["role"]=="worker")
        scenario = lab["scenario"]
        stage("Préparation privée de l’exercice")
        if scenario=="kubelet":
            self.ssh(lab, worker["name"], "systemctl stop kubelet\n")
            script = """export KUBECONFIG=/etc/kubernetes/admin.conf
for i in $(seq 1 90); do
  state=$(kubectl get node NODE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
  test "$state" != True && exit 0
  sleep 2
done
exit 1
""".replace("NODE",worker["name"])
            self.ssh(lab, first["name"], script, timeout=210)
        elif scenario=="ha-controlplane":
            target = next(n for n in lab["nodes"] if n["name"]=="cka-cp-3")
            self.ssh(lab, target["name"], """set -eu
cp /etc/kubernetes/manifests/kube-apiserver.yaml /var/tmp/cka-kube-apiserver.yaml
sed -i 's#image: .*kube-apiserver:.*#image: registry.k8s.io/kube-apiserver:cka-invalid#' /etc/kubernetes/manifests/kube-apiserver.yaml
""")
            self.ssh(lab, first["name"], """export KUBECONFIG=/etc/kubernetes/admin.conf
for i in $(seq 1 60); do
  if ! kubectl --server=https://172.30.90.12:6443 --request-timeout=3s get --raw=/readyz >/dev/null 2>&1; then exit 0; fi
  sleep 2
done
exit 1
""",timeout=180)
        elif scenario=="drain":
            self.ssh(lab, first["name"], (self.root/"templates/prepare-drain.sh").read_text(),timeout=300)
        elif scenario=="controlplane":
            self.ssh(lab, first["name"], """set -eu
cp /etc/kubernetes/manifests/kube-scheduler.yaml /var/tmp/cka-kube-scheduler.yaml
sed -i 's#image: .*kube-scheduler:.*#image: registry.k8s.io/kube-scheduler:cka-invalid#' /etc/kubernetes/manifests/kube-scheduler.yaml
sleep 30
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl create namespace cka-proof
kubectl -n cka-proof create deployment proof --image=busybox:1.37 -- sleep 28800
""")
        else:
            definitions = json.loads(self.content.read_text())
            setup = next(l["setup"] for l in definitions if l["id"]==scenario)
            if not setup:
                raise RuntimeError("Préparation absente.")
            extra = ""
            namespace = {"service":"cka-service","probes":"cka-probes"}.get(scenario)
            if namespace:
                extra += "kubectl -n "+namespace+" run probe --image=busybox:1.37 --restart=Never -- sleep 28800\nkubectl -n "+namespace+" wait --for=condition=Ready pod/probe --timeout=180s\n"
            if scenario=="policy":
                extra += "kubectl -n cka-policy rollout status deployment/web --timeout=180s\nkubectl -n cka-policy wait --for=condition=Ready pod/good pod/bad --timeout=180s\n"
            self.ssh(lab, first["name"], "set -eu\nexport KUBECONFIG=/etc/kubernetes/admin.conf\n"+setup+"\n"+extra,timeout=400)

    def verify(self, lab, stage):
        first = next(n for n in lab["nodes"] if n["role"]=="control-plane")
        stage("Lecture de l’état réel du cluster")
        # The checker itself is a fixed script, never a submitted user command.
        script = (self.root/"templates/check-scenario.py").read_text()
        command = "export KUBECONFIG=/etc/kubernetes/admin.conf\npython3 - "+shlex.quote(lab["scenario"])+" <<'CKA_CHECKER'\n"+script+"\nCKA_CHECKER\n"
        return json.loads(self.ssh(lab, first["name"], command, timeout=45))

    def console(self, lab, node, command):
        self.assert_vm(lab, next(n["vmid"] for n in lab["nodes"] if n["name"]==node))
        try:
            result = subprocess.run(["ssh", "-F", str(self.directory(lab)/"ssh_config"), node, "bash -s"], input=command.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25, env=self.env)
            return {"exitCode": result.returncode, "output": result.stdout[-65536:].decode(errors="replace"), "truncated": len(result.stdout)>65536}
        except subprocess.TimeoutExpired:
            return {"exitCode": 124, "output": "Durée maximale de 25 secondes atteinte. Utilise des commandes non interactives.", "truncated": False}

    def __call__(self, action, lab, stage):
        if action=="create":
            return self.create(lab, stage)
        if action=="retry":
            return self.resume(lab,stage)
        if action=="destroy":
            if lab["id"]=="legacy-cka":
                return self.legacy_destroy(lab, stage)
            self.terraform("destroy", lab, stage, start=True)
            # Ephemeral SSH identities are no longer useful after confirmed
            # deletion. Keep private state/journals for recovery, remove keys.
            for name in ("gateway_key", "node_key"):
                (self.directory(lab)/name).unlink(missing_ok=True)
            return
        if action=="prepare":
            return self.prepare(lab, stage)
        if action=="verify":
            return self.verify(lab, stage)
        raise RuntimeError("Action inconnue.")
