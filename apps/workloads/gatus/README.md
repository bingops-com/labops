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
  those figures.
- A `ServiceMonitor` exports Gatus results to Prometheus. After two consecutive
  failed checks and one additional minute, `GatusEndpointDown` routes through
  Alertmanager to the existing Discord `applications` webhook and sends a
  resolved notification after the next successful check. `GatusMetricsMissing`
  separately reports that Gatus itself has not been scraped for five minutes.
  Gatus holds no webhook URL: the existing Bitwarden-managed Alertmanager
  Secret remains the sole credential and recovery source.

## Verify

```sh
kubectl kustomize apps/workloads/gatus/clusters/labprod >/dev/null
kubectl --context labprod get application gatus-labprod -n argocd-system
kubectl --context labprod get deployment,pod -n gatus
kubectl --context labprod get servicemonitor,prometheusrule -n gatus
```

After authorized reconciliation, query Prometheus for an `up` series with
`namespace="gatus"` and `service="gatus"`. Test notifications with a reviewed,
temporary failing endpoint rather than changing a production Service or
disclosing the webhook URL. Prometheus or Alertmanager outages can prevent a
Discord notification; their independent alerts and the critical
`GatusMetricsMissing` rule cover Gatus failures while Prometheus remains up.
