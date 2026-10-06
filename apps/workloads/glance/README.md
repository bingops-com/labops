# Glance dashboard

Glance runs only on `labprod` and is available privately at
`https://home.lab.bingo` through the LAN and Tailscale split-DNS route. Traefik
accepts only LAN and tailnet source ranges; the hostname is not published by
Cloudflare Tunnel.

The tracked ConfigMap owns the dashboard layout. It intentionally uses only
public feeds and internal health endpoints. The Ops page reads node CPU, memory,
`/var` filesystem, Ready-node and Running-pod metrics from the in-cluster
Prometheus HTTP API; Glance has no Kubernetes API token or RBAC permissions. A
future private calendar feed or API token must be stored in the Bitwarden
`labprod` project, mapped with a BitwardenSecret and injected through an
environment variable; never commit its value or URL.

Render and verify without reading Secrets:

```sh
kubectl kustomize apps/workloads/glance/clusters/labprod >/dev/null
kubectl --context labprod get application glance-labprod -n argocd-system
kubectl --context labprod get deployment,pod,ingress,certificate -n glance
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' https://home.lab.bingo
```

The compact Ops widget is an operational summary. Grafana remains authoritative
for metric history, per-node detail and alert investigation.
