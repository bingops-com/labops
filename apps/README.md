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

Argo CD installs platform dependencies before workloads. Sealed Secrets uses
sync wave `-9`, Traefik and
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

Argo CD is private on both workload clusters. Tailscale split DNS resolves
`argocd.test.lab.bingo` through the labtest DNS service and resolves only
`argocd.lab.bingo` through a dedicated DNS service bound to the labprod VIP
`192.168.10.160` and returning `192.168.10.151`. Neither hostname is routed through Cloudflare Tunnel or
published by public DNS. Their Traefik ingresses allow only the local lab
networks and Tailscale. Labtest uses the local CA; labprod uses a publicly
trusted Let's Encrypt certificate obtained through Cloudflare DNS-01, without
sending application traffic through Cloudflare. Tailscale clients must have a
subnet route to `192.168.10.0/24` for the split nameservers and ingresses to be
reachable.

Production is published through the Cloudflare tunnel reconciled by the
`labprod` app-of-apps. Its cluster-specific `cloudflare-tunnel-secret`
SealedSecret is committed with the Cloudflare application and produces the
Secret in namespace `cloudflare`. Reseal it for the current `labprod`
controller whenever the tunnel credential or sealing key rotates. The
portfolio is public at `portfolio.lab.bingo`; `bingops.com` and
`www.bingops.com` route to the same service. Cloudflare DNS and tunnel routes
under `lab.bingo` are explicit: no production wildcard is used, and
`argocd.lab.bingo` remains private to LAN/Tailscale.

Production ingress TLS uses Let's Encrypt DNS-01. The expected Secret is named
`cloudflare-api-token` in namespace `cert-manager`, with key `api-token`. Create
a dedicated Cloudflare token with `Zone:DNS:Edit` and `Zone:Zone:Read`, limited
to `bingops.com` and `lab.bingo`, store it in the ignored credentials directory,
and seal it for `labprod` using the procedure below. Do not reuse the broader
Terraform infrastructure token.

Labtest uses the private `test.lab.bingo` DNS zone and a cert-manager-managed
local CA. Its root certificate and key are generated in-cluster in the
`labtest-root-ca` Secret. Clients must trust the root certificate explicitly;
back up the Secret in encrypted operator storage so rebuilt clusters can
preserve client trust. Restore that Secret into `cert-manager` before Argo CD
reconciles the labtest certificate resources. Rotate the CA by replacing the
Secret through the same protected recovery workflow, then redistribute its
public `ca.crt` to clients; never print or commit `tls.key`. Verify without
exposing key material by checking that the portfolio certificate chains to the
trusted CA and is valid for `portfolio.test.lab.bingo`.

On a Debian-derived client such as Kali, export only the public CA certificate,
inspect its fingerprint, then install it in the system trust store. The
JSONPath selects `ca.crt` explicitly; never export `tls.key`:

```sh
kubectl --context labtest --namespace cert-manager get secret labtest-root-ca -o jsonpath='{.data.ca\.crt}' | base64 --decode > /tmp/labtest-root-ca.crt
openssl x509 -in /tmp/labtest-root-ca.crt -noout -subject -issuer -fingerprint -sha256
sudo install -m 0644 /tmp/labtest-root-ca.crt /usr/local/share/ca-certificates/labtest-root-ca.crt
sudo update-ca-certificates
curl --fail --show-error --silent https://argocd.test.lab.bingo/ >/dev/null
curl --fail --show-error --silent https://portfolio.test.lab.bingo/ >/dev/null
```

Confirm the displayed fingerprint through the encrypted CA backup or another
trusted operator channel before installation. Repeat the export and trust-store
update after rotating or replacing `labtest-root-ca`.

## Branch promotion workflow

The `labtest` root and every Git-backed Application below it follow the
permanent `develop` branch. The `labprod` root and production Applications
follow only `master`. A feature is promoted first into `develop`, validated on
`labtest`, then promoted from `develop` into `master`. This keeps platform,
DNS, certificate and workload changes on the same tested revision.

A new application must provide
`apps/workloads/<app>/clusters/labtest` and
`apps/workloads/<app>/clusters/labprod`, using respectively
`<app>.test.lab.bingo` and `<app>.lab.bingo`. Production Cloudflare DNS and
tunnel routes are declared explicitly for each public application. The
portfolio additionally owns the aliases `bingops.com` and `www.bingops.com`.

The legacy `gitops-preview.sh` helper is not used for Applications already
owned by the `develop` root because two Argo CD Applications must never manage
the same namespace resources. It remains available only for an unregistered,
isolated workload that is not yet listed in the labtest kustomization.

The complete operator procedure and reusable manifest conventions are in
[`docs/gitops-applications.md`](../docs/gitops-applications.md). That runbook is
the source of truth for adding, testing, promoting, rolling back and removing
a workload.

## Sealed Secrets

Both clusters run the official Sealed Secrets chart with controller name
`sealed-secrets-controller` in `kube-system`. Seal every secret independently
for `labtest` and `labprod`: their private sealing keys are intentionally
different. Back up those controller keys outside Git before relying on sealed
credentials during cluster recreation.

Store the dedicated cert-manager token as
`terraform/cloudflare/credentials/cert-manager-api-token` with mode `0600`.
That directory is ignored. Generate the labprod manifest without printing the
token:

```sh
kubectl create secret generic cloudflare-api-token --namespace cert-manager --from-file=api-token=terraform/cloudflare/credentials/cert-manager-api-token --dry-run=client -o json | kubeseal --context labprod --controller-name sealed-secrets-controller --controller-namespace kube-system --scope strict --format yaml > apps/platform/certificates/cloudflare-api-token.yaml
```

Add `cloudflare-api-token.yaml` to
`apps/platform/certificates/kustomization.yaml`, validate it with `kubeseal
--validate`, then commit it. Repeat the sealing operation after either the
Cloudflare token or the labprod sealing key rotates; ciphertext from another
cluster cannot be reused.

## Bootstrap

Render and install the Argo CD overlay for the selected cluster, wait for Argo
CD, then install exactly one root application from `gitops/bootstrap/`. These
are the only imperative bootstrap operations. The root creates an
`argocd-<cluster>` Application which adopts and continuously reconciles the
matching Argo CD overlay, so later chart values and version changes are GitOps
managed. The labtest bootstrap follows `develop`; the labprod bootstrap follows
`master`. Never bootstrap a `labprod` root into `labtest`, or conversely.
