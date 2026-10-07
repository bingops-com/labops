# Gatus

Gatus probes the lab endpoints and feeds the availability widget and header
readout of the [portal](../portal/README.md). It runs only on `labprod`.

- No ingress and no UI exposure: the portal reads
  `http://gatus.gatus.svc.cluster.local:8080/api/v1/endpoints/statuses`
  in-cluster.
- `base/config.yaml` is the source of truth for the monitored endpoints. The
  generated ConfigMap name carries a content hash, so a change restarts Gatus.
- No credentials and no Kubernetes API access. Check history is kept in SQLite
  on the `gatus-data` PVC (`local-path`), which lets the portal show
  availability over 7 days; it is not backed up, and losing it only resets
  those figures. Alerting stays with Prometheus and Alertmanager.

## Verify

```sh
kubectl kustomize apps/workloads/gatus/clusters/labprod >/dev/null
kubectl --context labprod get application gatus-labprod -n argocd-system
kubectl --context labprod get deployment,pod -n gatus
```
