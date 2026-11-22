# Public edge gateway

This Terraform stack creates a replaceable Hetzner Cloud CX23 that is used only
as the public layer-4 entry point for services running on `labprod`. It stores no
application data. A retained primary IPv4 is attached to the VM, cloud-init
joins the existing Tailscale network, and nftables forwards declared TCP/UDP
ports through the existing `192.168.10.0/24` subnet route. DNS-only Cloudflare
records resolve service names directly to the retained IPv4.

The default configuration publishes `pz.bingops.com` and forwards Project
Zomboid UDP `16261` and `16262` to the Kubernetes NodePorts on
`192.168.10.151`. RCON is intentionally absent. Additional web or TCP/UDP
services are added through `public_dns_records` and the `forwards` map.

The default `cx23` is the smallest practical x86 instance for this role. At
the 2026-10-07 Hetzner pricing, the server and retained IPv4 cost about EUR
5.99/month before VAT; traffic over the included EU allowance is extra.

## External inputs and ownership

The stack owns the Hetzner server, its retained IPv4, cloud firewall, SSH key,
the DNS-only service records, the single-use Tailscale bootstrap key and the
generated nftables configuration. It does not own Kubernetes Services, the
Cloudflare zone, the Proxmox subnet router or the Tailscale policy file.

Create these prerequisites outside Git and keep them in the password manager:

- a Hetzner Cloud project API token with read/write access to that project;
- a Cloudflare API token with Zone Read and DNS Edit for `bingops.com`;
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
export CLOUDFLARE_API_TOKEN='<from-password-manager>'
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
terraform -chdir=terraform/edge-gateway plan -replace='tailscale_tailnet_key.edge_gateway[0]' -replace='hcloud_server.edge_gateway[0]' -out=edge-gateway.tfplan
```

## Adding services

Update the tracked, non-secret `routes.auto.tfvars` file. Each entry declares a
protocol, public port, private target and optional IPv4 source CIDRs. For
HTTP/HTTPS, target the host-network Traefik listener on
`192.168.10.151:80/443`. TLS termination and application routing remain in
Kubernetes.

Service names in `public_dns_records` are ordinary Cloudflare DNS-only A
records. Do not enable the Cloudflare HTTP proxy for game or other arbitrary
UDP traffic. Project Zomboid clients use `pz.bingops.com` with the default game
port `16261`.

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


## Gaming as a Service preparation

The lifecycle refactor is staged on `feat/gaas-lifecycle`; it has not been
applied to the existing gateway. `enabled` defaults to `true`. Set it to
`false` only in a reviewed plan to remove the VM and its consumed bootstrap
key while retaining the IPv4, DNS records, firewall and operator SSH key.
The retained IPv4 continues to incur its own charge. Resume with `enabled=true`;
Terraform creates a fresh single-use Tailscale key for the new VM.

`moved.tf` migrates the original singleton VM/key addresses to index `[0]`
without replacing them. Keep these moved blocks for retained states. A first
real plan must show these moves with no VM replacement before applying.
Never use `terraform destroy` for suspension: that would also remove the
retained address and DNS. Forward-table changes still replace the VM, so the
automatic worker rejects those plans until a separate route-update mechanism
has been implemented and tested. Other game adapters are follow-up work.

Run the provider-mocked lifecycle tests with no cloud credentials or real state:

```sh
terraform -chdir=terraform/edge-gateway init -backend=false -input=false -lockfile=readonly
terraform -chdir=terraform/edge-gateway test
```

### Production ownership and recovery

The production GameRoom system and the protected Kubernetes backend are owned
by [the production runbook](../../apps/workloads/gaas/production/README.md).
Its one-time `adopt-state.py` helper requires the original encrypted backup,
full file-restore comparison and an actual refreshed no-op plan. The backend is
`gaming-state`, suffix `edge-gateway`; test state remains separate in `gaas-state`.
The original local execution state is retired only after migrated lineage and
VM/IP IDs are verified. Public adoption outcomes are recorded in the production
receipt; Terraform state and diagnostics never belong in Git.

Local Task initialization requires an explicitly generated, ignored
`backend.tf.json`; it cannot silently initialize an empty local state. Restore
and validate the protected backend before enabling any worker after a rebuild.
The worker generates its own backend declaration with namespace-scoped in-cluster
authentication and Lease locking. Never run Terraform from a second local copy
of the retired state. For deliberate local maintenance, configure the same
Kubernetes namespace/suffix and current `labprod` client context before init.

The isolated live acceptance verified public UDP, shared consumers, safe last
suspension, retained-IP/world resume and GameRoom deletion/recreation. Its owning
report is in `bingops-com/pz-server/operations/gaas-acceptance-20261122.json`.
Other game adapters, hot route changes and actual second-build acceptance are
follow-up work; the production catalogue must contain full immutable artifacts.
