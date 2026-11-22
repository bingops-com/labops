# LabOps Portal

The portal is the private landing page of the lab: cluster, Argo CD, Gatus and
Prometheus status on one page, news and tools on another. It runs only on
`labprod` and is available at `https://lab.bingo` through the LAN and the
Tailscale split-DNS route. Traefik accepts only LAN and tailnet source ranges;
the hostname is not published through Cloudflare Tunnel.

## Ownership

- Source: separate `bingops-com/portal` repository (local checkout
  `/opt/homeops/portal`), which documents every widget and option.
- Image: `docker/portal` clones the `master` branch of the source; the image
  workflow publishes `ghcr.io/bingops-com/portal:sha-<labops commit>`. See
  [`docker/portal/README.md`](../../../docker/portal/README.md) for releases
  and external prerequisites.
- Layout: `base/portal.yaml` is the source of truth for pages and widgets. The
  portal re-reads the mounted file, so a config-only change needs no image
  release.
- Availability data: [`apps/workloads/gatus`](../gatus/README.md).
- DNS: `apps/platform/private-dns` answers the `lab.bingo` apex with the
  Traefik VIP; `terraform/network` owns the matching Tailscale split-DNS entry.

## Access and data

- The current portal has OIDC configured for editing, in addition to the
  Traefik LAN/tailnet allowlist. Source versions without OIDC enabled allow
  anyone reaching the portal to edit its layout; keep that distinction when
  rebuilding. Preserve its issuer/client/group/public URL and session PVC.
  `PORTAL_READONLY=true` disables editing.
- Kubernetes: the `portal` ServiceAccount is bound to the `portal-read`
  ClusterRole (get/list on nodes, namespaces, pods, events, apps workloads and
  Argo CD Applications). It cannot read Secrets or ConfigMaps. Argo CD status
  comes from the Application resources, so the portal holds no Argo CD token.
- In-cluster HTTP: Prometheus and Gatus, through the `PORTAL_VAR_*` variables
  of the Deployment. Public APIs: Open-Meteo, CoinGecko, RSS/Atom, YouTube
  feeds, Hacker News (Algolia), Reddit feeds.
- The default portal needs no provider credentials. A private value such as an iCal address
  must come from a Bitwarden `labprod` mapping exposed as a `PORTAL_VAR_*`
  environment variable and referenced as `${PORTAL_VAR_NAME}` in
  `base/portal.yaml`; such values are resolved in the pod and never sent to
  the browser.

## Gaming candidate

The separate source branch `feat/game-room-portal` implements the `gamerooms`
widget and typed Git operations. It requires OIDC with an explicit owner group,
reads only configured GameRooms and creates commits for state changes or PRs
for versions. Its GitHub App key must come from a Bitwarden-backed Secret,
not the browser or the portal-data PVC. A dedicated App installation is still
an external prerequisite; no such App or production rollout was created.

The candidate image source and test-only configuration/RBAC are owned by
[`the GaaS acceptance runbook`](../gaas/acceptance/README.md). Do not replace
the deployed portal with the older base Deployment from that worktree: retain
the current authentication, image pinning and browser layout. The source
repository's `docs/gaming.md` documents key permissions, rotation, recovery,
conflict handling and the current scope (existing GameRooms; creation by Git).

## State

The `portal-data` PVC (`local-path`) holds `layout.json`, the layout saved from
the browser, which overrides the pages of `base/portal.yaml`. It is the only
state outside Git and is not backed up: losing it reverts the portal to
`base/portal.yaml`. To keep a browser layout, use "Exporter en YAML" in the
editor and commit the result as `base/portal.yaml`.

## Verify without reading Secrets

```sh
kubectl kustomize apps/workloads/portal/clusters/labprod >/dev/null
kubectl --context labprod get application portal-labprod -n argocd-system
kubectl --context labprod get deployment,pod,pvc,ingress,certificate -n portal
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' https://lab.bingo/healthz
```

Replaces: the Cluster Portal prototype and the Glance dashboard. The pruned
`glance` namespace and the Tailscale `welcome.lab.bingo` split-DNS entry
disappear on the next reconcile and Terraform apply respectively.
