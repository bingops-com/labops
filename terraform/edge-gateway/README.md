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

### State migration prerequisite

The only current execution state remains the protected local file in the
original `labops/terraform/edge-gateway` directory. No state was copied into
this worktree. Do not run a real plan/apply from an empty state here: that
would attempt to create another gateway rather than adopt the current one.

The proposed worker uses a Kubernetes backend in a dedicated `gaas-state`
namespace and its Lease lock. `backend.tf.example` is an inactive example,
not an activated backend. Before enabling workers, an operator must:

1. Recover the existing Hetzner, Cloudflare and edge-specific Tailscale OAuth
   credentials from the password manager, and map only these inputs through
   Bitwarden Secrets Manager to the worker environment. The network/DNS OAuth
   client is not interchangeable with the edge auth-key client.
2. Provide the original SSH public key as a non-secret configuration input;
   a different key changes bootstrap inputs and may cause replacement.
3. Create narrowly scoped state Secret/Lease RBAC, a protected encrypted
   backup for the backend state, and validate that backup's restoration.
4. Back up the current local state privately, stop other Terraform writers,
   and perform one explicitly reviewed backend migration using that state.
   Preserve its lineage and resource IDs. Never print state or commit it.
5. Verify the remote state retains VM ID `169230729` and IPv4 resource ID
   `154062800`, and verify a non-destructive plan before enabling jobs.
6. Mark the old local state as retired in the private operator inventory so
   it cannot become a second writer. Retain the protected recovery copy.

The namespace, RBAC, backup and migration are not installed by this change.
Until those prerequisites and credentials are confirmed, production lifecycle
execution remains disabled. Restore the backend before reconciling gateway
resources after a complete lab rebuild. The current local state continues to
use its existing retained-home recovery policy while migration is pending.

The game planner/guarded worker lives in the `pz-server` repository under
`gaas/`. The Kubernetes runtime adapter, polling controller, reproducible game
release artefacts and end-to-end cloud acceptance remain unfinished; the
Terraform tests simulate create/suspend/resume and do not prove Internet
routing, Tailscale enrollment or Project Zomboid client connectivity.
