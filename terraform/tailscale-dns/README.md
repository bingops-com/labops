# Tailscale split DNS

This stack owns the private DNS routes consumed by Tailscale clients:

| DNS suffix | Nameserver | Owner |
| --- | --- | --- |
| `test.lab.bingo` | `192.168.1.152` | CoreDNS on `labtest` |
| `argocd.lab.bingo` | `192.168.1.151` | CoreDNS on `labprod` |

The `argocd.lab.bingo` route is intentionally an exact-name split route. It
must not replace DNS for the rest of `lab.bingo`. Neither Argo CD hostname is
served through Cloudflare Tunnel.

The OAuth client is an external prerequisite. It requires Tailscale DNS write
permission and must be stored only in an ignored variables file. Create or
rotate it in the Tailscale admin console, update the ignored input, and revoke
the previous client after a successful apply. The client secret cannot be
recovered from Git.

Do not set `tailscale_tailnet` to the public Cloudflare zone. A tailnet ID is a
Tailscale identifier, not a DNS domain owned in Cloudflare. By default the
provider derives the tailnet from the OAuth client, which is the preferred
configuration. Set `tailscale_tailnet` only when an explicit Tailnet ID is
required; copy that ID from the Tailscale admin console rather than guessing it.

Clients must be able to reach `192.168.1.0/24` through an approved Tailscale
subnet router. Validate without exposing credentials by resolving both names
while connected to Tailscale and confirming that HTTPS is unreachable after
disconnecting from both Tailscale and the local network.

Review changes before applying because Terraform contacts the live tailnet:

```sh
terraform init
terraform plan
terraform apply
```

The resources are declarative and repeated applies are idempotent. If a split
route is already absent, removing it from this stack requires only a reviewed
Terraform apply; do not make an ad-hoc dashboard change that leaves Terraform
state stale.
