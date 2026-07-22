# GitOps applications

The active environments map directly to the CAPI workload clusters:

| Environment | Cluster | Purpose | Portfolio hostname |
| --- | --- | --- | --- |
| test | `labtest` | private validation | `portfolio.test.lab.bingo` |
| production | `labprod` | production workloads | `portfolio.lab.bingo` (also `bingops.com` and `www.bingops.com`) |

The repository is split by ownership:

- `argocd/`: one pinned Argo CD bootstrap overlay per cluster;
- `gitops/bootstrap/`: the single root `Application` installed after Argo CD;
- `gitops/clusters/`: app-of-apps definitions, projects, sync waves and policies;
- `platform/`: cluster services such as issuers and private DNS;
- `workloads/`: personal applications with shared bases and explicit cluster overlays.

Argo CD installs platform dependencies before workloads. Bitwarden Secrets
Manager uses sync wave `-9`, Traefik and
cert-manager use sync wave `-8`, the ACME issuer uses `-6`, and applications use
wave `0`. Traefik is pinned to chart `40.2.0`; the retired Ingress-NGINX project
is deliberately not used. Automated sync, pruning and self-healing are enabled
only after the root application has been installed intentionally.

## Security and DNS

The test portfolio ingress allows only the local lab networks
(`192.168.1.0/24` and `192.168.10.0/24`) and the Tailscale CGNAT range
(`100.64.0.0/10`). Test DNS
is not published through Cloudflare: a dedicated CoreDNS process resolves the
wildcard `*.test.lab.bingo` to the labtest node and listens on
the labtest control-plane VIP `192.168.10.170`, returns the Traefik node
address `192.168.10.152`, and `terraform/tailscale-dns`
sends only `test.lab.bingo` queries to it.

Argo CD uses Authentik OIDC on both workload clusters. Tailscale split DNS
resolves `argocd.test.lab.bingo` through the labtest DNS service and resolves only
`argocd.lab.bingo` through a dedicated DNS service bound to the labprod VIP
`192.168.10.160` and returning `192.168.10.151`. Neither hostname is routed
through Cloudflare Tunnel or published by public DNS. Their Traefik ingresses allow only the local lab
networks and Tailscale on test. Production has no IP allowlist and relies on
Authentik authentication, but its exact hostname remains reachable only through
LAN/Tailscale routing. Both clusters use publicly trusted Let's Encrypt
certificates obtained through Cloudflare DNS-01, without sending application
traffic through Cloudflare. Tailscale clients must have a
subnet route to `192.168.10.0/24` for the split nameservers and ingresses to be
reachable.

Production is published through the Cloudflare tunnel reconciled by the
`labprod` app-of-apps. Its cluster-specific `cloudflare-tunnel-secret`
BitwardenSecret mapping is committed with the Cloudflare application and
produces the Secret in namespace `cloudflare`. Rotate its value in the
Bitwarden `labprod` project. The
portfolio is public at `portfolio.lab.bingo`; `bingops.com` and
`www.bingops.com` route to the same service. Cloudflare DNS and tunnel routes
under `lab.bingo` are explicit: no production wildcard is used, and
`argocd.lab.bingo` remains private to LAN/Tailscale. Authentik itself is public
at `auth.lab.bingo` through the tunnel so both browser and server-side OIDC
flows can reach it. See [`docs/authentik.md`](../docs/authentik.md).

Ingress TLS uses Let's Encrypt DNS-01 on both clusters. The expected Secret is named
`cloudflare-api-token` in namespace `cert-manager`, with key `api-token`. Create
a dedicated Cloudflare token with `Zone:DNS:Edit` and `Zone:Zone:Read`, limited
to `bingops.com` and `lab.bingo`, store it in the ignored credentials directory,
and store each cluster's value in its matching Bitwarden project. Do not reuse the broader Terraform
infrastructure token. DNS for `*.test.lab.bingo` remains private; DNS-01 proves domain
control without publishing the private services or routing traffic through
Cloudflare.

Verify both private test endpoints with the normal system trust store; `-k` is
not an acceptable operational check:

```sh
curl --fail --show-error --silent https://argocd.test.lab.bingo/ >/dev/null
curl --fail --show-error --silent https://portfolio.test.lab.bingo/ >/dev/null
```

## Branch promotion workflow

The `labtest` and `labprod` roots and all Git-backed Applications follow
`master` as their stable state. A pushed feature branch is integrated
temporarily into `labtest` with `hacks/deploy.sh`, validated there, then merged
into `master`. This keeps platform, DNS, certificate and workload changes on
the same tested revision without a permanent integration branch.

A new application must provide
`apps/workloads/<app>/clusters/labtest` and
`apps/workloads/<app>/clusters/labprod`, using respectively
`<app>.test.lab.bingo` and `<app>.lab.bingo`. Production Cloudflare DNS and
tunnel routes are declared explicitly for each public application. The
portfolio additionally owns the aliases `bingops.com` and `www.bingops.com`.

For the inner development loop, `hacks/deploy.sh` temporarily overrides one
existing `<app>-labtest` Application, or every Git-backed test Application when
`--app` is omitted, to follow a pushed feature branch.
There is still exactly one Application and one owner for the workload. The
labtest root ignores only child Application `targetRevision` differences, so it
continues to self-heal every other field. Run `restore test` before final
validation to restore the declared `master` revision. The active override is
recorded as an annotation and is visible with the helper's `status` command.
The same helper can perform a deliberately confirmed production override for
one or all Git-backed Applications after showing the applicable diff;
`restore prod` returns it to `master`.
Existing clusters require a one-time reviewed reapply of
the matching root bootstrap after enabling this policy; reconstructed clusters
receive it during their normal bootstrap.

The complete operator procedure and reusable manifest conventions are in
[`docs/gitops-applications.md`](../docs/gitops-applications.md). That runbook is
the source of truth for adding, testing, promoting, rolling back and removing
a workload.

## Secret delivery

Both clusters use the Bitwarden Secrets Manager operator and dedicated
Bitwarden US projects. Their machine tokens are injected with
`hacks/bootstrap-bitwarden.sh`; Git contains only operator configuration and
secret UUID mappings. See
[`docs/infrastructure/bitwarden-secrets-manager.md`](../docs/infrastructure/bitwarden-secrets-manager.md).

## Bootstrap

Render and install the Argo CD overlay for the selected cluster, wait for Argo
CD, then install exactly one root application from `gitops/bootstrap/`. These
are the only imperative bootstrap operations. The root creates an
`argocd-<cluster>` Application which adopts and continuously reconciles the
matching Argo CD overlay, so later chart values and version changes are GitOps
managed. Both bootstraps follow `master`, while retaining distinct cluster
overlays. Never bootstrap a `labprod` root into `labtest`, or conversely.
