# Talos on Proxmox

This stack downloads the Talos `nocloud` ISO, builds Proxmox template 1234, and clones it to create the single-node management cluster `labmgmt`. Every Kubernetes VM network device is tagged with VLAN 10. The template has Proxmox `on_boot` enabled so CAPMOX clones inherit automatic startup after a Proxmox node reboot. Its Talos ISO is attached to `ide2`, leaving `ide0` available for CAPMOX's generated NoCloud seed; `scsi0` remains first in the boot order after Talos installs. The same `ide2` CD-ROM is declared explicitly on `labmgmt`, because an existing clone does not inherit hardware changes subsequently made to template 1234. The CAPI controllers on `labmgmt` reuse the same template and own the sole workload cluster `labprod`, whose manifest lives under `capi/clusters/`.

## Prerequisites

- VM disks use the existing Proxmox `local-lvm` thin pool (`pve/data`).
  The Proxmox administrator owns this host-level prerequisite; Terraform only
  allocates VM disks in it. Verify capacity with `pvesm status --storage local-lvm`
  and `lvs -o vg_name,lv_name,lv_size,data_percent,metadata_percent` as root.
  Reserve space for three 100 GiB VM disks and the 32 GiB template, plus other
  host workloads and thin-pool headroom. CAPMOX full clones inherit this storage.

- Proxmox VE with an API token.
- Proxmox VM IDs 1234 and 150 must be free. Terraform creates and owns both resources.
- The Proxmox resource pool `Kubernetes` must already exist. Terraform references it but does not create or own it.
- The token needs permission to audit the Proxmox node, use the `Kubernetes` pool, download ISO content, and manage VMs 1234 and 150 with their disks/network devices. In particular, creating the Talos ISO requires `Datastore.AllocateTemplate` on `/storage/local`.
- Terraform 1.10 or newer.
- TCP connectivity from the Terraform runner to every node on `50000` and to the Kubernetes endpoint on `6443`.
- The Proxmox VLAN router described below must exist before moving `labmgmt` to `192.168.10.150`.

## Configure Proxmox as the VLAN router

The Livebox remains the Internet router on `192.168.1.0/24`. Proxmox routes VLAN 10 (`192.168.10.0/24`) through `vmbr0.10`, whose gateway address is `192.168.10.1`, and masquerades outbound traffic through `vmbr0`. The playbook does not reconfigure the Livebox.

First review the defaults in `ansible/roles/proxmox_vlan_router/defaults/main.yml`. Then test connectivity and apply the dedicated playbook from the repository root:

```sh
ansible -i ansible/inventories/main/hosts proxmox -m ping
ansible-playbook -i ansible/inventories/main/hosts ansible/proxmox-router.yml --check --diff
ansible-playbook -i ansible/inventories/main/hosts ansible/proxmox-router.yml --diff
```

The playbook ensures `nftables` is installed without refreshing unrelated APT repositories, creates `vmbr0.10`, enables IPv4 forwarding, and installs a persistent NAT service. Proxmox is already the Tailscale subnet router for `192.168.1.0/24`; the playbook preserves that route and also advertises `192.168.10.0/24`.

The persistent `terraform/network` stack invokes this playbook and then enables both advertised routes through the official Tailscale Terraform provider. Tailscale requires routes to be advertised by the device and enabled through its API; `tailscale_device_subnet_routes` manages the enablement. Do not add `192.168.1.100` as a local Linux gateway when the workstation reaches that address through Tailscale.

Verify workstation connectivity after applying the network stack. The task
waits up to ten minutes for the `labmgmt` Talos API, allowing VM 150 to restart
after Terraform changes while still failing on a persistent routing or boot
problem:

```sh
task workstation:route
```

### Tailscale Terraform credential

In the Tailscale admin console, open **Trust credentials**, create an OAuth client, and grant only these scopes:

- `devices:core:read`
- `devices:routes`
- `dns`

The first scope lets Terraform resolve the `homelab` device, the second lets it enable or revoke its subnet routes, and the third manages the tailnet's global DNS configuration. Tailscale recommends OAuth trust credentials instead of user API keys for persistent automation. Copy the secret immediately because it is displayed only once.

Create the ignored credential file:

```sh
cp terraform/network/credentials.auto.tfvars.example terraform/network/credentials.auto.tfvars
chmod 600 terraform/network/credentials.auto.tfvars
$EDITOR terraform/network/credentials.auto.tfvars
```

It must contain:

```hcl
tailscale_oauth_client_id     = "replace-with-oauth-client-id"
tailscale_oauth_client_secret = "replace-with-oauth-client-secret"
```

`terraform/network/credentials.auto.tfvars` is excluded both by the stack `.gitignore` and the repository-wide `terraform/**/credentials*.tfvars` rule. Never commit the OAuth secret or place it on a command line.

### Taskfile workflow

With [Task](https://taskfile.dev/) installed, the repository-level `Taskfile.yml` exposes the same operations with guarded prompts:

```sh
task --list
task proxmox:vlan:check
task network:plan
task network:apply
task terraform:fmt
task setup:vlan
```

`task setup:vlan` initializes and applies the persistent network stack first. Terraform invokes the Proxmox Ansible role, enables the two Tailscale routes, then plans and applies the separate `labmgmt` stack. Before proceeding, it reads template 1234 through Proxmox and verifies the system disk, Talos ISO on `ide2`, boot order, and free `ide0` slot required by CAPMOX. It intentionally does not delete existing CAPI clusters. Review both saved plans carefully when VM 150 or template 1234 already exists.

The complete lifecycle is also exposed as guarded tasks:

```sh
task lifecycle:create
task lifecycle:recreate
```

`lifecycle:create` configures/reconciles the VLAN router and `labmgmt`, installs the pinned CAPI providers, creates `labprod`, waits for it, then installs its client configuration. It does not delete an existing cluster.

`lifecycle:recreate` is the complete clean-room rebuild. It first deletes the CAPI-owned `labprod` cluster, including VM 151, while `labmgmt` is still available. It then creates and applies a Terraform destruction plan for VM 150, template 1234, and the Terraform-managed Talos assets before running the complete creation lifecycle. The persistent network/Tailscale stack and ignored credential files are retained. Review both destruction and creation plans because both clusters are replaced.

### Recovery when the management and workload disks are lost

Use this disaster-recovery path only after explicit approval to replace VM IDs
150, 151 and template 1234 and abandon their current cluster data. It is
not a management migration: `clusterctl move` and CAPI deletion require the old
management API. If that API is recoverable, use normal CAPI cleanup instead.

1. Verify all three targets are stopped, the old storage is unavailable, and
   `local-lvm` has the capacity described above. Preserve other VMs and storage
   definitions. Keep the old disks offline even if their device returns: old
   clusters share IP addresses and identities with the replacement deployment.
2. As the Proxmox administrator, archive only those three files from
   `/etc/pve/qemu-server/` into a root-only directory under
   `/var/lib/labops-recovery/`, then remove their active definitions. An archive
   is sensitive generated recovery state, never a Git artifact. Record its
   directory in the intervention report. Check each existing definition is
   stopped and still references the failed storage before moving it. Missing
   definitions are already retired; do not archive a newly rebuilt VM on rerun.
   This releases the IDs without attempting to delete inaccessible disks.
   The guarded helper implements these checks (run from the repository):

   ```sh
   ssh bingo@192.168.1.100 'sudo bash -s -- 150,151,1234' < hacks/retire-lost-kube-vms.sh
   ```
3. Keep a mode-0600 backup of the existing Terraform state in protected local
   storage. Set `datastore` in `terraform.tfvars` to the healthy datastore.
   Terraform remains owner of VM 150 and template 1234; do not import 151/152.
4. Create a saved Terraform plan with explicit replacement of the management
   Talos secrets, configuration-apply, bootstrap and kubeconfig resources. This
   prevents old bootstrap state from being reused against empty disks. Review
   only resource addresses/actions, never plaintext plan JSON or outputs.
   Apply the reviewed plan; retain the existing ISO when it is available.

   From the repository root, keep all plan/log artifacts private and outside Git:

   ```sh
   umask 077; recovery_dir=$(mktemp -d /tmp/labops-kube-rebuild.XXXXXX); cp terraform/proxmox/terraform.tfstate "$recovery_dir/pre-rebuild.tfstate"
   terraform -chdir=terraform/proxmox plan -input=false -no-color -out="$recovery_dir/rebuild.tfplan" '-replace=talos_machine_secrets.cluster["labmgmt"]' '-replace=talos_machine_configuration_apply.node["talos-labmgmt-cp-01"]' '-replace=talos_machine_bootstrap.cluster["labmgmt"]' '-replace=talos_cluster_kubeconfig.cluster["labmgmt"]' > "$recovery_dir/plan.log" 2>&1
   terraform -chdir=terraform/proxmox show -json "$recovery_dir/rebuild.tfplan" | jq -r '.resource_changes[] | [.address, (.change.actions | join(","))] | @tsv'
   terraform -chdir=terraform/proxmox apply -input=false -no-color "$recovery_dir/rebuild.tfplan" > "$recovery_dir/apply.log" 2>&1
   ```

   Stop if any command fails. The plan should create only the missing management
   VM/template and replace the four Talos resources; it must not affect other
   host workloads. These local-state backup commands assume the current local
   backend; use backend-native protected snapshots if migrated to remote state.
   Temporary artifacts are not durable backups: the operator must retain needed
   state backups in encrypted storage before workstation cleanup or reboot.
5. Install management client access, initialize the pinned CAPI providers and
   apply the workload manifests as documented in the CAPI guide. After partial
   failure, use a fresh normal plan and resume reconciliation; do not repeatedly
   replace credentials or archive the newly created VMs.
6. Verify management and workload nodes are Ready, all four Proxmox disk
   references use `local-lvm`, and the thin pool has headroom. Rebuild application
   services and restore backups following the full rebuild runbook.

The host administrator recovers Proxmox from installation media and host
backups; VM contents require independent backups. API tokens are external
sensitive inputs recovered/rotated using the token procedures in this README
and the CAPI guide. Client configurations are regenerated, not restored from
chat or logs. Recreating disks does not restore databases or persistent volumes.

### Normal destruction with an available management cluster

The guarded destruction workflow preserves lifecycle ownership: it asks CAPI to delete `labprod` while its management cluster is still available, waits for cleanup, then creates and applies a saved Terraform destruction plan:

```sh
task lifecycle:destroy CONFIRM_DESTROY=labprod,labmgmt
```

The required `CONFIRM_DESTROY` value names both cluster targets exactly, in addition to the interactive prompts. Review `destroy.tfplan` when prompted. The Proxmox Terraform stack also owns VM 150, template 1234, the downloaded Talos ISO, generated Talos secrets and client configurations held in state; those managed assets are included in the destruction plan. The task does not remove the Proxmox VLAN interface, nftables routing, Tailscale route advertisement, or stale files already installed under `~/.kube` and `~/.talos`.

For an existing installation, do not change the management VM first. Use this order:

1. Apply the Proxmox router playbook, approve its Tailscale route, and verify workstation connectivity.
2. Run `terraform plan` and inspect whether VM 150 or template 1234 will be replaced.
3. If `labmgmt` already owns healthy workload clusters, move their CAPI objects to another management cluster before any proposed replacement. Do not replace `labmgmt` while it is their only lifecycle owner.
4. Apply Terraform, regenerate the local kubeconfig/Talos config, and verify `192.168.10.150`.
5. Apply the VLAN-aware workload manifests only after the management cluster is reachable.

If a failed `labprod` attempt allocates addresses from its old pool, delete that failed `Cluster` resource and wait for its Machine, IP claim and VM to disappear before recreating it from the VLAN-aware manifest. This is destructive and is only appropriate when the cluster contains no data to retain:

```sh
kubectl delete cluster labprod --namespace capi-workloads
kubectl wait --for=delete machine --all --namespace capi-workloads --timeout=10m
```

## Create the Terraform API token

Before the first `terraform apply`, connect to a Proxmox node and run these
commands as `root`:

```sh
pveum user add terraform@pve \
  --comment 'LabOps Terraform provider'

pveum user token add terraform@pve labops \
  --privsep 1 \
  --comment 'LabOps Terraform provider'
```

The second command displays the token secret only once. Copy it immediately to
the ignored `terraform/proxmox/credentials.auto.tfvars` file on the Terraform
workstation; do not put it in Git, shell history, documentation, or logs.

If the user already exists, omit `pveum user add`. If the token already exists,
do not remove it merely to rerun the procedure: Proxmox cannot display its
secret again, and removing it is a credential rotation.

Keep privilege separation enabled. Grant the required ACLs to both
`terraform@pve` and `terraform@pve!labops`; the token cannot inherit permissions
that its backing user does not have. Scope access to the actual Proxmox node,
`Kubernetes` pool, datastores, template, and VM IDs used by this stack. The
additional ISO-storage commands are documented below.

Do not add `labprod` to the Terraform `clusters` map: that would create competing lifecycle owners. For a future HA management cluster, add two control-plane nodes to `labmgmt`, set its `control_plane_vip`, and use that VIP as its endpoint.

## Deploy from scratch

Start from the repository root and verify every environment-specific value before creating infrastructure:

```sh
git clone <repository-url> labops
cd labops

# Review Proxmox node/storage, VM IDs, addresses, MAC addresses and gateway.
$EDITOR terraform/proxmox/terraform.tfvars

# Confirm that VM IDs 1234 and 150 are free on node homelab.
```

VM IDs 1234 and 150 and address `192.168.10.150` must be free. The address is injected through the Proxmox Cloud-Init drive; no DHCP reservation is required. Do not continue if `terraform plan` proposes deleting infrastructure you intend to retain.

Before applying, boot VM 150 and confirm from the Terraform runner that Talos maintenance mode is reachable:

```sh
nc -vz 192.168.10.150 50000
talosctl version --nodes 192.168.10.150 --insecure
```

If either command fails, check the Proxmox console and confirm that VM 150 has VLAN tag `10` and a Cloud-Init drive with `ipconfig0: ip=192.168.10.150/24,gw=192.168.10.1`.

Create the ignored credentials file from the tracked example and insert the
secret returned by `pveum`. Terraform automatically loads files ending in
`.auto.tfvars`:

```sh
cd terraform/proxmox
cp credentials.auto.tfvars.example credentials.auto.tfvars
$EDITOR credentials.auto.tfvars
terraform init
terraform validate
terraform plan
terraform apply
```

The file must contain exactly the credentials consumed by the provider:

```hcl
proxmox_api_url   = "https://proxmox.example:8006/"
proxmox_api_token = "terraform@pve!labops=replace-me"
```

Do not add `ssh_key`: Talos has no SSH service and the old Ubuntu template variable is unused. Environment variables remain a suitable CI alternative: `TF_VAR_proxmox_api_url` and `TF_VAR_proxmox_api_token`.

### Proxmox permissions for the ISO

Terraform asks Proxmox itself to download the Talos ISO into storage `local`. The API identity must therefore have `Datastore.AllocateTemplate` on `/storage/local`. For the example token `terraform@pve!labops`, run as `root` on a Proxmox node:

```sh
pveum acl modify /storage/local --users terraform@pve --roles PVEDatastoreAdmin
```

If the token was created with privilege separation (`privsep=1`, the default), grant the ACL to the token as well:

```sh
pveum acl modify /storage/local --tokens 'terraform@pve!labops' --roles PVEDatastoreAdmin
```

The token can never have more permissions than its backing user, so both ACLs are required for a privilege-separated token. Verify the effective permissions before retrying:

```sh
pveum user permissions terraform@pve /storage/local
pveum user token permissions terraform@pve labops /storage/local
```

Replace the user and token names with those from `proxmox_api_token`. In the web interface, the equivalent ACL is under **Datacenter > Permissions** with path `/storage/local` and role `PVEDatastoreAdmin`. Once the permission is visible, rerun `terraform apply`; Terraform will resume from the existing state.

The first apply downloads the pinned `nocloud` ISO, creates template 1234, clones it into VM 150, injects the initial network configuration, applies the Talos configuration, and bootstraps `labmgmt`. Then install Kubernetes and Talos access in their standard locations:

```sh
../../hacks/cluster-setup.sh --management-only
kubectl get nodes
talosctl health
```

Both configurations and all cluster secrets are stored in Terraform state. Use an encrypted remote backend with locking before treating this as a long-lived cluster. The generated `talosconfig` and `kubeconfig` files are ignored by Git.

Continue with the [CAPI guide](../../capi/README.md) to install the pinned providers on `labmgmt` and create `labprod` from template 1234.
