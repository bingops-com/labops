# Public edge gateway

This Terraform stack creates a replaceable Hetzner Cloud CX23 that is used only
as the public layer-4 entry point for services running on `labprod`. It stores no
application data. A retained primary IPv4 is attached to the VM, cloud-init
joins the existing Tailscale network, and nftables forwards declared TCP/UDP
ports through the existing `192.168.10.0/24` subnet route.

The default forwarding table publishes Project Zomboid UDP `16261` and `16262`
to the Kubernetes NodePorts on `192.168.10.151`. RCON is intentionally absent.
Additional web or TCP/UDP services are added only through the `forwards` map.

The default `cx23` is the smallest practical x86 instance for this role. At
the 2026-10-07 Hetzner pricing, the server and retained IPv4 cost about EUR
5.99/month before VAT; traffic over the included EU allowance is extra.

## External inputs and ownership

The stack owns the Hetzner server, its retained IPv4, cloud firewall, SSH key,
the single-use Tailscale bootstrap key and the generated nftables configuration.
It does not own Kubernetes Services, DNS records, the Proxmox subnet router or
the Tailscale policy file.

Create these prerequisites outside Git and keep them in the password manager:

- a Hetzner Cloud project API token with read/write access to that project;
- a dedicated Tailscale OAuth client allowed to create auth keys carrying
  `tag:edge-gateway`;
- an operator SSH public key at the configured local path.

The OAuth client must have the `auth_keys` scope, and the existing Tailscale
policy must make `tag:edge-gateway` an allowed tag. The gateway must be allowed
to reach `192.168.10.151` through the subnet route already advertised by
`homelab`, and a separate Tailscale SSH rule must permit the intended operators
to administer the tagged gateway. Do not grant the gateway access to unrelated
tailnet destinations.

Provide credentials through environment variables; do not put them in a
Terraform variable file:

```sh
export HCLOUD_TOKEN='<from-password-manager>'
export TAILSCALE_OAUTH_CLIENT_ID='<from-password-manager>'
export TAILSCALE_OAUTH_CLIENT_SECRET='<from-password-manager>'
export TAILSCALE_TAILNET='-'
```

Copy only the non-secret local settings file:

```sh
cp terraform/edge-gateway/credentials.auto.tfvars.example terraform/edge-gateway/credentials.auto.tfvars
chmod 600 terraform/edge-gateway/credentials.auto.tfvars
```

Terraform state is sensitive because the provider records the short-lived,
single-use Tailscale bootstrap key. Keep the local state mode `0600`, back it up
only to protected storage and never print or commit it. The key expires after
one hour and is unusable after the VM consumes it.

## Workflow

Initialize, format, validate and create a saved plan:

```sh
task edge:init
task edge:fmt
task edge:validate
task edge:plan
```

Review the saved plan without exporting it as JSON, then apply it:

```sh
task edge:apply
```

A forwarding-table change replaces the stateless server because cloud-init is
immutable, while retaining the public IPv4. The saved-plan workflow is the
destruction guard: always inspect the replacement before applying it. Expect a
short forwarding interruption while the retained address moves to the new VM.

If a manual server replacement is required without changing its bootstrap
inputs, rotate the already-consumed single-use key in the same reviewed plan:

```sh
terraform -chdir=terraform/edge-gateway plan -replace=tailscale_tailnet_key.edge_gateway -replace=hcloud_server.edge_gateway -out=edge-gateway.tfplan
```

## Adding services

Update the tracked, non-secret `routes.auto.tfvars` file. Each entry declares a
protocol, public port, private target and optional IPv4 source CIDRs. For
HTTP/HTTPS, target the host-network Traefik listener on
`192.168.10.151:80/443`. TLS termination and application routing remain in
Kubernetes.

The gateway uses source NAT so return traffic follows the Tailscale tunnel.
Applications therefore do not see the original client address; with the
default Tailscale subnet-router SNAT they normally see the homelab router's LAN
address. This is an explicit availability/simplicity tradeoff. Tailscale's own
netfilter management is disabled on this dedicated host because nftables owns
its complete firewall policy.

## Safe verification

Do not display cloud-init data, Terraform state or auth keys. Verify only
non-sensitive state:

```sh
terraform -chdir=terraform/edge-gateway output public_ipv4
tailscale status --json | jq -r '.Peer[] | select(.HostName == "labops-edge-01") | [.HostName, .Online] | @tsv'
ssh root@labops-edge-01 'systemctl is-active tailscaled nftables && sudo nft list table inet edge_gateway'
```

From an external client, test only the ports intentionally present in
`public_forwards`. Project Zomboid must reach public UDP `16261` and `16262`;
TCP `27015` must remain closed.

## Recovery

The gateway has no data to restore. Recreate it from this stack and the external
credentials above. The retained primary IPv4 keeps public endpoints stable.
If the IPv4 itself is lost, apply the stack to allocate a replacement and update
the owning public DNS or connection documentation before reopening traffic.
