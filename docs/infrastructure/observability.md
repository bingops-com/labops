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

Fluent Bit persists its tail database and filesystem backlog under
`/var/lib/fluent-bit` on each node. Its HTTP metrics endpoint is discovered by
Prometheus through a `ServiceMonitor`; the `LabOps / Logging` Grafana dashboard
shows collection/indexing throughput, retries, errors, dropped records and the
latest Elasticsearch logs. The `labops-log-pipeline` rules alert when Fluent
Bit is no longer scraped, stops reading container logs, encounters sustained
Elasticsearch errors, drops records or skips oversized lines.

Alertmanager routes notifications to the three existing Discord webhooks:

- `critical` for every critical alert, repeated every two hours while active;
- `infrastructure` for Kubernetes, Argo CD, monitoring and logging components;
- `applications` for the remaining workload alerts.

Messages include the status, cluster, severity, namespace, grouped occurrence
count, summary, description, and dashboard or runbook links when supplied by
the alert. No additional Discord channel is required until a separate on-call
audience or retention policy is needed.

Gatus endpoint failures reuse the `applications` receiver instead of copying a
Discord webhook into the `gatus` namespace. Prometheus scrapes Gatus through
the workload-owned `ServiceMonitor`; two consecutive failed checks raise
`GatusEndpointDown`, and the next successful check produces the resolved
notification. A separate critical alert detects missing Gatus metrics. The
existing Bitwarden `applications-url` mapping remains the only non-Git input.

Elasticsearch runs as a single node. The bootstrap Job therefore installs the
`logs-labprod` index template (priority 200, above the built-in `logs`
template, which Elasticsearch refuses to overwrite) with
`number_of_replicas: 0` and the failure store disabled, and sets zero replicas
on existing `logs-labprod-*` indices and their failure-store indices. With any
replica the cluster stays yellow, Argo CD reports
`observability-config-labprod` as Progressing and its sync never completes.
`kubectl --context labprod get elasticsearch -n logging` must report `green`.

Confirm the `fluent-bit` Prometheus target, the `LabOps / Logging` dashboard,
recent `logs-labprod-*` documents and firing/resolved Discord notifications
after reconciliation.
