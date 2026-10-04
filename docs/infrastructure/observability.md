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

Confirm Prometheus targets, Grafana datasources, recent `logs-labprod-*`
documents and firing/resolved Discord notifications after reconciliation.
