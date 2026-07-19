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
  'Datastore.AllocateSpace Datastore.AllocateTemplate Datastore.Audit Pool.Allocate Sys.Audit Sys.Console VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.Migrate VM.Monitor VM.PowerMgmt SDN.Use'
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
pveum user token permissions capmox@pve capi /
```

Do not disable privilege separation merely to work around a missing ACL.

On the workstation, create the ignored credentials file from the tracked
example and insert the token secret returned by Proxmox:

```sh
cp capi/credentials.env.example capi/credentials.env
chmod 600 capi/credentials.env
$EDITOR capi/credentials.env
```

The file uses the same pattern as Terraform's ignored
`credentials.auto.tfvars`: only the example is committed. From the repository
root on the workstation, run the guarded initialization helper:

```sh
kubectl config current-context
./hacks/capi-init.sh
```

The helper requires the current context to be exactly `labmgmt`, checks that
the credentials file has mode `0600` or `0400`, displays only the endpoint and
token ID, and asks before running the pinned `clusterctl init`. It never prints
the token secret. It then waits up to five minutes for all deployments to
become available.

```sh
./hacks/capi-init.sh --help
```

Use `--yes` only for intentional unattended execution. `--context NAME` allows
a different management-context name but still enforces an exact match. These
commands change the selected Kubernetes cluster.

## 3. Create workload clusters

Ensure the following dedicated VM IDs and addresses are free before applying.
The node addresses must be excluded from DHCP:

| Cluster | Proxmox VM ID | Node address | Control-plane VIP | Proxmox pool |
| --- | ---: | --- | --- | --- |
| `labprod` | `151` | `192.168.10.151` | `192.168.10.160` | `Kubernetes` |
| `labtest` | `152` | `192.168.10.152` | `192.168.10.170` | `Kubernetes` |

Each cluster currently has one control-plane replica and exactly one available
node address. The manifests constrain CAPMOX with a single-value `vmIDRange`
(`151-151` and `152-152`); `virtualMachineID` is controller-managed and must not
be used to request an ID. Add another unique VM ID range and address allocation
before increasing the replica count. Then apply:

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
