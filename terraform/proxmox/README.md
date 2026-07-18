# Talos on Proxmox

This stack downloads the Talos `nocloud` ISO, builds Proxmox template 1234, and clones it to create the single-node management cluster `labmgmt`. Every Kubernetes VM network device is tagged with VLAN 10. The template has Proxmox `on_boot` enabled so CAPMOX clones inherit automatic startup after a Proxmox node reboot. Its Talos ISO is attached to `ide2`, leaving `ide0` available for CAPMOX's generated NoCloud seed; `scsi0` remains first in the boot order after Talos installs. The same `ide2` CD-ROM is declared explicitly on `labmgmt`, because an existing clone does not inherit hardware changes subsequently made to template 1234. The CAPI controllers on `labmgmt` reuse the same template and own the independent workload clusters `labprod` and `labtest`, whose manifests live under `capi/clusters/`.

## Prerequisites

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

`lifecycle:create` configures/reconciles the VLAN router and `labmgmt`, installs the pinned CAPI providers, creates `labprod` and `labtest`, waits for both clusters, then installs their client configurations. It does not delete existing clusters.

`lifecycle:recreate` is the complete clean-room rebuild. It first deletes the CAPI-owned `labprod` and `labtest` clusters, including VMs 151 and 152, while `labmgmt` is still available. It then creates and applies a Terraform destruction plan for VM 150, template 1234, and the Terraform-managed Talos assets before running the complete creation lifecycle. The persistent network/Tailscale stack and ignored credential files are retained. Review both destruction and creation plans because all three clusters are replaced.

### Complete destruction

The guarded destruction workflow preserves lifecycle ownership: it asks CAPI to delete `labprod` and `labtest` while their management cluster is still available, waits for their cleanup, then creates and applies a saved Terraform destruction plan:

```sh
task lifecycle:destroy CONFIRM_DESTROY=labprod,labtest,labmgmt
```

The required `CONFIRM_DESTROY` value names all three cluster targets exactly, in addition to the interactive prompts. Review `destroy.tfplan` when prompted. The Proxmox Terraform stack also owns VM 150, template 1234, the downloaded Talos ISO, generated Talos secrets and client configurations held in state; those managed assets are included in the destruction plan. The task does not remove the Proxmox VLAN interface, nftables routing, Tailscale route advertisement, or stale files already installed under `~/.kube` and `~/.talos`.

For an existing installation, do not change the management VM first. Use this order:

1. Apply the Proxmox router playbook, approve its Tailscale route, and verify workstation connectivity.
2. Run `terraform plan` and inspect whether VM 150 or template 1234 will be replaced.
3. If `labmgmt` already owns healthy workload clusters, move their CAPI objects to another management cluster before any proposed replacement. Do not replace `labmgmt` while it is their only lifecycle owner.
4. Apply Terraform, regenerate the local kubeconfig/Talos config, and verify `192.168.10.150`.
5. Apply the VLAN-aware workload manifests only after the management cluster is reachable.

The currently failed `labprod` and `labtest` attempts allocate addresses from their old pools. Delete those failed `Cluster` resources and wait for their Machines, IP claims, and VMs to disappear before recreating them from the VLAN-aware manifests. This is destructive and is only appropriate when those clusters contain no data to retain:

```sh
kubectl delete cluster labprod labtest --namespace capi-workloads
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

Do not add `labprod` or `labtest` to the Terraform `clusters` map: that would create competing lifecycle owners. For a future HA management cluster, add two control-plane nodes to `labmgmt`, set its `control_plane_vip`, and use that VIP as its endpoint.

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

Continue with the [CAPI guide](../../capi/README.md) to install the pinned providers on `labmgmt` and create `labprod` and `labtest` from template 1234.
