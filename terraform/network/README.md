# Persistent Proxmox and Tailscale network

This Terraform stack owns the network foundation that must outlive every Kubernetes cluster. It invokes the repository's idempotent Ansible role to configure `vmbr0.10`, IPv4 forwarding and nftables on Proxmox, then uses the official Tailscale provider to enable `192.168.1.0/24` and `192.168.10.0/24` on the `homelab` subnet router.

It intentionally has a separate state from `terraform/proxmox`: destroying `labmgmt` must not revoke the route used to reach Proxmox.

## Credentials

Create a Tailscale OAuth trust credential with `devices:core:read`, `devices:routes`, and `dns`, then store it only in the ignored local file:

```sh
cp terraform/network/credentials.auto.tfvars.example terraform/network/credentials.auto.tfvars
chmod 600 terraform/network/credentials.auto.tfvars
$EDITOR terraform/network/credentials.auto.tfvars
```

## Apply

From the repository root:

```sh
task network:plan
task network:apply
```

The plan runs no provisioner. Applying it may run the Proxmox Ansible playbook when its tracked role, inventory, or playbook hash has changed, and then enables the advertised Tailscale routes. Keep the saved state encrypted and locked because Terraform state contains infrastructure identifiers and the OAuth client is used during refresh/apply.

The stack also enables MagicDNS, configures Cloudflare (`1.1.1.1`) and Quad9 (`9.9.9.9`) as global resolvers, and overrides local DNS. This ensures the Proxmox subnet router can resolve public download endpoints even when Tailscale owns `/etc/resolv.conf`.
