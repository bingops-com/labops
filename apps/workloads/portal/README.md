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

## Layout

`base/portal.yaml` sorts widgets by the question a page answers, so a new
widget has an obvious home:

| Page | Question | Group |
| --- | --- | --- |
| Accueil | Is everything fine? Syntheses only. | Lab |
| Cluster | What is running? | Lab |
| Fiabilité | What could break? | Lab |
| Changements | What moved, what needs updating? | Lab |
| Veille | What is happening elsewhere? | Perso |
| Perso | My day. | Perso |

Wide columns hold what is read (lists, charts), narrow ones what is glanced at
(counters, states), most urgent first. A `section` widget titles and folds the
widgets below it when a page grows. A layout saved from the browser takes
precedence over this file until "Revenir au YAML" is used.

## Access and data

- Reading is open to the LAN and tailnet (Traefik allowlist). Editing the
  layout requires an Authentik login and membership of the `portal-editors`
  group: an editor can make the pod request HTTP addresses of their choice.
  The OIDC client `portal` is a public PKCE client declared in
  `apps/platform/authentik/blueprint.yaml`, so there is no client secret to
  store. Add editors to the group in Authentik or in the blueprint.
- Outbound requests: `PORTAL_INTERNAL_HOSTS=.svc.cluster.local` lets widgets
  reach in-cluster Services only; any other private address (LAN, node, pod IP)
  is refused, redirects included. Public addresses stay open. The GitHub
  widgets (releases, pull requests, version lag) call `api.github.com`
  anonymously (60 requests per hour and per source IP; about 25 are used), and
  the deadlines widget reads end-of-support dates from `endoflife.date`.
- Monitoring: `ServiceMonitor/portal` scrapes `/metrics`
  (`portal_fetch_total`, `portal_readout_state`).
- Kubernetes: the `portal` ServiceAccount is bound to the `portal-read`
  ClusterRole (get/list on nodes, namespaces, pods, events, apps workloads,
  CronJobs and Jobs, Argo CD Applications, cert-manager Certificates and CloudNativePG
  clusters and backups). It cannot read Secrets or ConfigMaps. Argo CD status
  comes from the Application resources, so the portal holds no Argo CD token.
- Browser side: link icons declared as `si:<name>` are loaded by the viewer's
  browser from the Simple Icons CDN (`cdn.simpleicons.org`); remove the `icon`
  keys in `base/portal.yaml` to avoid that third-party request.
- In-cluster HTTP: Prometheus and Gatus, through the `PORTAL_VAR_*` variables
  of the Deployment. Public APIs: Open-Meteo, CoinGecko, RSS/Atom, YouTube
  feeds, Hacker News (Algolia), Reddit feeds.
- The portal holds no credentials. A private value such as an iCal address
  must come from a Bitwarden `labprod` mapping exposed as a `PORTAL_VAR_*`
  environment variable and referenced as `${PORTAL_VAR_NAME}` in
  `base/portal.yaml`; such values are resolved in the pod and never sent to
  the browser.

## State

The `portal-data` PVC (`local-path`) holds `layout.json`, the layout saved from
the browser, which overrides the pages of `base/portal.yaml`, and
`session.key`, the generated key that signs editor sessions, and
`readouts.json`, the state of the header readouts and when each last changed,
and `incidents.json`, the incident log the portal keeps by itself (a degraded
readout opens an incident, its recovery closes it). It is the only
state outside Git and is not backed up: losing it reverts the portal to
`base/portal.yaml` and signs editors out. To keep a browser layout, use "Exporter en YAML" in the
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
