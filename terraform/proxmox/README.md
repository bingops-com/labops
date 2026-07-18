# Talos on Proxmox

This stack downloads the Talos `nocloud` ISO, builds Proxmox template 1234, and clones it to create the single-node management cluster `labmgmt`. The template has Proxmox `on_boot` enabled so CAPMOX clones inherit automatic startup after a Proxmox node reboot. The CAPI controllers on `labmgmt` reuse the same template and own the independent workload clusters `labprod` and `labtest`, whose manifests live under `capi/clusters/`.

## Prerequisites

- Proxmox VE with an API token.
- Proxmox VM IDs 1234 and 150 must be free. Terraform creates and owns both resources.
- The Proxmox resource pool `Kubernetes` must already exist. Terraform references it but does not create or own it.
- The token needs permission to audit the Proxmox node, use the `Kubernetes` pool, download ISO content, and manage VMs 1234 and 150 with their disks/network devices. In particular, creating the Talos ISO requires `Datastore.AllocateTemplate` on `/storage/local`.
- Terraform 1.10 or newer.
- TCP connectivity from the Terraform runner to every node on `50000` and to the Kubernetes endpoint on `6443`.

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

VM IDs 1234 and 150 and address `192.168.1.150` must be free. The address is injected through the Proxmox Cloud-Init drive; no DHCP reservation is required. Do not continue if `terraform plan` proposes deleting infrastructure you intend to retain.

Before applying, boot VM 150 and confirm from the Terraform runner that Talos maintenance mode is reachable:

```sh
nc -vz 192.168.1.150 50000
talosctl version --nodes 192.168.1.150 --insecure
```

If either command fails, check the Proxmox console and confirm that VM 150 has a Cloud-Init drive with `ipconfig0: ip=192.168.1.150/24,gw=192.168.1.1`.

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
