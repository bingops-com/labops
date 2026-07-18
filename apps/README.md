# GitOps applications

The active environments map directly to the CAPI workload clusters:

| Environment | Cluster | Purpose | Portfolio hostname |
| --- | --- | --- | --- |
| test | `labtest` | private validation | `portfolio.test.bingops.com` |
| production | `labprod` | production workloads | `portfolio.prod.bingops.com` |

The repository is split by ownership:

- `argocd/`: one pinned Argo CD bootstrap overlay per cluster;
- `gitops/bootstrap/`: the single root `Application` installed after Argo CD;
- `gitops/clusters/`: app-of-apps definitions, projects, sync waves and policies;
- `platform/`: cluster services such as issuers and private DNS;
- `workloads/`: personal applications with shared bases and explicit cluster overlays.

Argo CD installs platform dependencies before workloads. Sealed Secrets uses
sync wave `-9`, Traefik and
cert-manager use sync wave `-8`, the ACME issuer uses `-6`, and applications use
wave `0`. Traefik is pinned to chart `40.2.0`; the retired Ingress-NGINX project
is deliberately not used. Automated sync, pruning and self-healing are enabled
only after the root application has been installed intentionally.

## Security and DNS

The test portfolio ingress allows only the Kubernetes VLAN
(`192.168.10.0/24`) and the Tailscale CGNAT range (`100.64.0.0/10`). Test DNS
is not published through Cloudflare: a dedicated CoreDNS process resolves the
wildcard `*.test.bingops.com` to the labtest node and listens on
the `labtest` node address `192.168.10.152`, and `terraform/tailscale-dns`
sends only `test.bingops.com` queries to it.

Production is published through the Cloudflare tunnel reconciled by the
`labprod` app-of-apps. Before its first synchronization, create the expected
`cloudflare-tunnel-secret` Secret in namespace `cloudflare`; the legacy
cluster-bound SealedSecret is deliberately not referenced. The production
hostname and ingress are public. The Cloudflare wildcard
`*.prod.bingops.com` forwards to Traefik, which selects the application from
its hostname; no Cloudflare Access policy or source-IP allowlist is attached.

TLS uses Let's Encrypt DNS-01. Before synchronizing `certificates`, create a
Secret named `cloudflare-api-token` in namespace `cert-manager`, with key
`api-token`, using a Cloudflare token scoped to DNS edit on `bingops.com`. Keep
that Secret outside plaintext Git; seal or encrypt it independently for each
cluster because sealing keys are cluster-specific.

## Feature previews on labtest

The permanent `labtest` root follows `master` only for its platform services.
Application workloads are not part of that root. A feature branch is activated
explicitly with `hacks/gitops-preview.sh`; the resulting Argo CD Application
follows the pushed branch directly and is named `<app>-preview`. Updating the
same preview switches its revision. Removing it also removes its managed
resources through the Argo CD resources finalizer.

Only one feature branch per application is active at a time because the stable
test hostname is `<app>.test.bingops.com`. A new application must provide
`apps/workloads/<app>/clusters/labtest` and
`apps/workloads/<app>/clusters/labprod`, using respectively
`<app>.test.bingops.com` and `<app>.prod.bingops.com`.

From the repository root, after pushing the feature branch:

```sh
./hacks/gitops-preview.sh up portfolio feature/my-branch
./hacks/gitops-preview.sh down portfolio
```

Production Applications always follow `master`. Promotion therefore consists
of merging the tested feature branch into `master`; Argo CD never deploys a
feature revision to `labprod`.

## Sealed Secrets

Both clusters run the official Sealed Secrets chart with controller name
`sealed-secrets-controller` in `kube-system`. Seal every secret independently
for `labtest` and `labprod`: their private sealing keys are intentionally
different. Back up those controller keys outside Git before relying on sealed
credentials during cluster recreation.

## Bootstrap

Render and install the Argo CD overlay for the selected cluster, wait for Argo
CD, then install exactly one root application from `gitops/bootstrap/`. These
are the only imperative bootstrap operations; Argo CD owns everything below
the root application afterward. Never bootstrap a `labprod` root into
`labtest`, or conversely.
