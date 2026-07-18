# Cluster API on `labmgmt`

Terraform builds Talos `nocloud` template 1234, creates `labmgmt` from it, and injects the initial IP through Cloud-Init. Cluster API running on `labmgmt` reuses the same template to own the lifecycle of `labprod` and `labtest`.

The workload manifests intentionally use the stable Talos CAPI APIs and CAPMOX's served `v1alpha1` compatibility API. CAPMOX v0.9 also serves `v1alpha2`, but its native CAPI v1beta2 path currently requires pre-release Talos CAPI providers. This keeps the production path on stable provider releases.

## 1. Create management infrastructure

Review template ID 1234, VM ID 150, addresses, storage, and the Proxmox node name before applying. Both IDs must be free because Terraform creates and owns them:

```sh
cd terraform/proxmox
cp credentials.auto.tfvars.example credentials.auto.tfvars # first run only
$EDITOR credentials.auto.tfvars
terraform plan
terraform apply
cd ../..
./hacks/cluster-setup.sh --management-only
```

Terraform assigns `192.168.1.150/24` to `labmgmt` through the Proxmox Cloud-Init drive; no DHCP reservation is required.

## 2. Install CAPI providers

After `labmgmt` is ready, connect to a Proxmox node and create the dedicated
CAPI identity as `root`:

```sh
pveum user add capmox@pve \
  --comment 'LabOps Cluster API provider'

pveum user token add capmox@pve capi \
  --privsep 1 \
  --comment 'LabOps Cluster API provider'
```

The token command displays the secret only once. Copy it immediately to the
ignored workstation file described below; do not put it in Git, shell history,
documentation, or logs. If `capmox@pve` already exists, omit the user creation
command. Do not remove an existing token unless credential rotation is intended.

Grant the user and the privilege-separated token only the Proxmox roles and
paths required by CAPMOX for the target pool, template, storage, and nodes. Both
need the ACLs: a privilege-separated token cannot use permissions its backing
user does not have. Create a dedicated role on the Proxmox node:

```sh
pveum role add LabOpsCAPMox --privs \
  'Datastore.Allocate Datastore.AllocateSpace Datastore.Audit Pool.Allocate Sys.Audit Sys.Console Sys.Modify VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.Migrate VM.Monitor VM.PowerMgmt SDN.Use'
```

If the role already exists, replace `role add` with `role modify`. Assign it to
both identities with propagation:

```sh
pveum acl modify / \
  --users capmox@pve \
  --roles LabOpsCAPMox \
  --propagate 1

pveum acl modify / \
  --tokens 'capmox@pve!capi' \
  --roles LabOpsCAPMox \
  --propagate 1
```

Verify effective permissions before continuing. Both commands must now display
permissions under `/`:

```sh
pveum user permissions capmox@pve /
pveum user token permissions capmox@pve capi
```

Do not disable privilege separation merely to work around a missing ACL.

Template 1234 keeps the Talos boot ISO on `ide2`; CAPMOX reserves `ide0` for
each workload machine's generated NoCloud seed. The automated lifecycle runs
`task proxmox:template:verify` after Terraform and refuses to create workloads
if the ISO, boot order, system disk, or free `ide0` slot is missing.

On the workstation, create the ignored credentials file from the tracked
example and insert the token secret returned by Proxmox:

```sh
cp capi/credentials.env.example capi/credentials.env
chmod 600 capi/credentials.env
$EDITOR capi/credentials.env
```

The file uses the same pattern as Terraform's ignored
`credentials.auto.tfvars`: only the example is committed. From the repository
root on the workstation, load it into the environment and install the pinned
providers on the current Kubernetes context:

```sh
set -a
. ./capi/credentials.env
set +a

export CLUSTERCTL_CONFIG="$PWD/capi/clusterctl.yaml"

kubectl config current-context

clusterctl init \
  --core cluster-api:v1.12.9 \
  --bootstrap talos:v0.6.12 \
  --control-plane talos:v0.5.13 \
  --infrastructure proxmox:v0.9.0 \
  --ipam in-cluster:v1.1.0

kubectl wait \
  --for=condition=Available \
  --timeout=5m \
  deployment --all -A
```

Confirm that `kubectl config current-context` is `labmgmt` before running
`clusterctl init`. These commands change the current cluster. When finished,
remove the credentials from the current shell without deleting the ignored
file:

```sh
unset PROXMOX_URL PROXMOX_TOKEN PROXMOX_SECRET CLUSTERCTL_CONFIG
```

## 3. Create workload clusters

Each cluster uses a dedicated node address and a separate Kubernetes API VIP.
`labprod` uses node `192.168.10.151` and VIP `192.168.10.160`; `labtest` uses
node `192.168.10.152` and VIP `192.168.10.170`. CAPMOX rejects a
`controlPlaneEndpoint` contained in its node-address pool, so these addresses
cannot be merged. All four addresses must be unused and excluded from DHCP.
The Talos machine configuration declares each node address and default route
explicitly, avoiding reliance on NoCloud network-data while CAPMOX still owns
address allocation and VM lifecycle. It selects the VM's only hardware network
device by PCI bus path instead of assuming it is named `eth0`; Talos predictable
interface names can otherwise leave the active VirtIO device running DHCP.
Then apply:

```sh
kubectl apply -f capi/namespace.yaml
kubectl apply -f capi/clusters/labprod.yaml
kubectl apply -f capi/clusters/labtest.yaml
clusterctl describe cluster labprod --namespace capi-workloads
clusterctl describe cluster labtest --namespace capi-workloads
```

Retrieve access after both control planes report ready:

```sh
clusterctl get kubeconfig labprod --namespace capi-workloads > kubeconfig-labprod
clusterctl get kubeconfig labtest --namespace capi-workloads > kubeconfig-labtest
KUBECONFIG="$PWD/kubeconfig-labprod" kubectl get nodes
KUBECONFIG="$PWD/kubeconfig-labtest" kubectl get nodes
```

Alternatively, install all available cluster configurations and configure Bash automatically with the documented helper:

```sh
./hacks/cluster-setup.sh
kubectl config get-contexts
talosctl config contexts
```

See [`hacks/README.md`](../hacks/README.md) for flags and management-only usage.

Never delete `labmgmt` while it owns workload clusters. A future management-cluster replacement must use `clusterctl move` first.
