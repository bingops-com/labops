# Monitoring and logging

LabOps deploys the same observability architecture to `labtest` and `labprod`,
with environment-specific capacity and retention:

| Component | labtest | labprod |
| --- | --- | --- |
| Prometheus | 2-day / 1.5 GB retention cap, 2 GiB PVC | 7-day / 8 GB retention cap, 10 GiB PVC |
| Grafana | 1 GiB PVC | 2 GiB PVC |
| Alertmanager | 512 MiB PVC | 1 GiB PVC |
| Elasticsearch | 384 MiB heap, 2 GiB PVC, 2-day ILM | 768 MiB heap, 10 GiB PVC, 7-day ILM |
| Fluent Bit | One DaemonSet Pod | One DaemonSet Pod |

The Prometheus chart provisions its maintained Kubernetes dashboards. LabOps
also provisions the version-controlled `LabOps / Operations` dashboard in both
environments. It combines alert count, node and Pod health, PVC pressure,
namespace CPU and memory, recent restarts and the environment-local
Elasticsearch log stream. The Grafana sidecar discovers it from the
`grafana-dashboard-labops-operations` ConfigMap; no dashboard is imported from
an unpinned external URL or maintained manually in Grafana.

Argo CD owns the ECK operator, Elasticsearch resource,
`kube-prometheus-stack`, Fluent Bit, ingress, RBAC and all configuration.
Local-path PVCs contain generated operational history rather than source data.
They are intentionally not backed up: rebuilding a cluster starts new metric
and log history. ECK uses `DeleteOnScaledownOnly` so an Application recreation
does not implicitly delete the Elasticsearch PVC, but a node or cluster loss
still loses this generated history.

Grafana is private at `grafana.test.lab.bingo` and `grafana.lab.bingo` and uses
the LAN/Tailscale allowlist. Authentication is delegated to Authentik through
public OIDC clients with Authorization Code and PKCE, so Grafana needs neither
a local administrator credential nor an OIDC client secret. Initial local
administrator creation and the login form are disabled. The Helm chart may
still render its internal admin Secret, but Grafana does not create or expose
that account and no external value is required. Members of
`grafana-admins` receive Grafana administrator access; other authenticated
users receive Viewer access. Elasticsearch has no Ingress; its HTTP Service is
cluster-local, uses dedicated least-privilege users and retains ECK's generated
HTTP and transport TLS. Internal clients encrypt traffic but skip verification
of ECK's private HTTP CA because it is not replicated across namespaces. Do not
expose that Service through an Ingress, NodePort or tunnel.

## External secrets

Create these five entries in each environment's Bitwarden project. Values are
not recoverable from Git and must never be copied into a manifest, issue, CI
variable or shell history.

| Bitwarden name | Purpose | Required value |
| --- | --- | --- |
| `observability-discord-critical-webhook-url` | All alerts carrying `severity=critical` | Webhook for the environment's `🚨-critical` channel |
| `observability-discord-infrastructure-webhook-url` | Kubernetes, nodes, Argo CD, ingress, storage and observability warnings | Webhook for the environment's `⚙️-infrastructure` channel |
| `observability-discord-applications-webhook-url` | Workload alerts not caught by the critical or infrastructure routes | Webhook for the environment's `📦-applications` channel |
| `observability-elasticsearch-grafana-password` | Read-only Grafana datasource user | Unique URL-safe password using only letters, digits, `_` and `-` |
| `observability-elasticsearch-fluent-bit-password` | `logs-<cluster>-*` writer | Unique URL-safe password using only letters, digits, `_` and `-` |

Create two categories in Discord, then three text channels in each category:

| Category | Channels |
| --- | --- |
| `LABOPS · PRODUCTION` | `🚨-critical`, `⚙️-infrastructure`, `📦-applications` |
| `LABOPS · TEST` | `🚨-critical`, `⚙️-infrastructure`, `📦-applications` |

Keep production channels above test and deny ordinary members the **Manage
Webhooks** permission. The critical channel should have the most restrictive
write permissions and the highest notification level; humans should not post
routine discussion there. Infrastructure contains Kubernetes, node, Argo CD,
Traefik, certificate, storage, Prometheus, Grafana, Elasticsearch and Fluent
Bit alerts. Applications is the default route for workload alerts. All three
receivers send resolved notifications. `Watchdog` and `InfoInhibitor` are
intentionally discarded to avoid periodic noise.

For every channel, open its settings, create a dedicated incoming webhook under
**Integrations**, give it a recognizable name such as `Alertmanager labprod
critical`, and store its URL immediately in the corresponding Bitwarden entry.
The webhooks remain enabled; Alertmanager does not require a GitHub webhook or
a bot token. Rotate any URL that is disclosed.

Replace every fake `00000000-...` UUID in the matching
`apps/platform/observability/<cluster>/bitwarden-secrets.yaml` with the ID of
the Bitwarden entry named above. The Grafana Elasticsearch password UUID is
intentionally used twice: once in the Grafana namespace and once for the
Elasticsearch bootstrap. Do not merge or deploy while a fake UUID remains.

The operator produces these Kubernetes Secrets:

| Namespace | Secret | Keys |
| --- | --- | --- |
| `monitoring` | `observability-discord` | `critical-url`, `infrastructure-url`, `applications-url` |
| `monitoring` | `observability-grafana-datasource` | `elasticsearch-password` |
| `logging` | `observability-elasticsearch-clients` | `grafana-password`, `fluent-bit-password` |

ECK separately generates `observability-es-elastic-user` for bootstrap only.
Grafana and Fluent Bit never use this superuser. A PostSync Job waits for
Elasticsearch, idempotently creates two constrained roles/users and the ILM
policy, then deletes itself after success.

## First deployment and reconstruction

1. Create all five Bitwarden entries per environment and commit their UUID
   mappings in place of the fake values.
2. Merge the reviewed GitOps changes. The root Applications create the
   `monitoring` and `logging` namespaces before their dependent charts.
3. Inject or rotate the namespace-local Bitwarden machine token with
   `./hacks/bootstrap-bitwarden.sh labtest` and then
   `./hacks/bootstrap-bitwarden.sh labprod`. The helper is idempotent and does
   not print the token.
4. Wait for the Bitwarden mappings, ECK operator, Elasticsearch and bootstrap
   Job before expecting Fluent Bit and Grafana to become ready.
5. Review and explicitly apply `terraform/network` to add the exact
   `grafana.lab.bingo` Tailscale split-DNS route. Git changes do not authorize
   this Terraform apply. Test Grafana remains covered by the existing
   `test.lab.bingo` wildcard route.

The order is safe after partial failure. Re-running the helper replaces only
the machine-token Secrets; Argo CD and ECK reconciliation are idempotent; the
bootstrap API calls replace the same roles, users, ILM policy and template.

## Rotation

For either Elasticsearch client password, replace the Bitwarden value, wait
for both generated Secrets to refresh, then request a normal Argo CD sync of
`observability-config-<cluster>`. Its PostSync Job updates the Elasticsearch
user idempotently. Grafana or Fluent Bit may need a reviewed rollout to reload
its environment variable. Rotate one client at a time and verify it before
rotating the next.

For Discord, rotate one channel at a time. Create its replacement webhook
first, replace the matching Bitwarden value, wait for the Secret refresh,
perform a reviewed Alertmanager rollout, verify a notification in that exact
channel, and only then delete the old webhook.

## Non-sensitive verification

Run these checks without decoding Secret data:

```sh
kubectl --context labtest get applications -n argocd-system monitoring-labtest eck-operator-labtest observability-config-labtest fluent-bit-labtest
```

```sh
kubectl --context labprod get applications -n argocd-system monitoring-labprod eck-operator-labprod observability-config-labprod fluent-bit-labprod
```

```sh
kubectl --context labtest get elasticsearch,pods,pvc -n logging
```

```sh
kubectl --context labprod get elasticsearch,pods,pvc -n logging
```

```sh
kubectl --context labprod get secret -n monitoring observability-discord observability-grafana-datasource
```

From LAN or Tailscale, both Grafana URLs must validate with the normal system
trust store. From outside both networks they must be unreachable. In Grafana,
confirm Authentik redirects automatically, an ordinary user is Viewer and a
`grafana-admins` member is Grafana Admin. Then confirm the Prometheus and
Elasticsearch datasources, a Kubernetes dashboard,
and recent `logs-<cluster>-*` documents. Finally send controlled critical,
infrastructure and application alerts and confirm both firing and resolved
messages arrive in exactly the expected environment channels.

## Capacity and growth

Both workload clusters currently have one scheduling node and local RWO
storage, so this stack is intentionally single-replica and not highly
available. Before increasing retention, measure PVC use and node memory. Add
cluster capacity and a replicated storage design before adding Prometheus or
Elasticsearch replicas; merely increasing replica counts on one node does not
provide failure tolerance.
