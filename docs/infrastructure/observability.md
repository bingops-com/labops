# Observability

`labprod` runs ECK-managed Elasticsearch, kube-prometheus-stack and Fluent
Bit. Grafana is private at `grafana.lab.bingo`, resolved by the production
Tailscale split-DNS service. Alertmanager webhooks and Elasticsearch client
passwords are delivered from the Bitwarden `labprod` project.

Argo CD owns the operator, configuration, monitoring and log-forwarding
Applications. Verify them without reading Secrets:

```sh
kubectl --context labprod get applications -n argocd-system monitoring-labprod eck-operator-labprod observability-config-labprod fluent-bit-labprod
kubectl --context labprod get elasticsearch,pods,pvc -n logging
```

Elasticsearch runs as a single node. The bootstrap Job therefore installs the
`logs-labprod` index template (priority 200, above the built-in `logs`
template, which Elasticsearch refuses to overwrite) with
`number_of_replicas: 0` and the failure store disabled, and sets zero replicas
on existing `logs-labprod-*` indices and their failure-store indices. With any
replica the cluster stays yellow, Argo CD reports
`observability-config-labprod` as Progressing and its sync never completes.
`kubectl --context labprod get elasticsearch -n logging` must report `green`.

Confirm Prometheus targets, Grafana datasources, recent `logs-labprod-*`
documents and firing/resolved Discord notifications after reconciliation.
