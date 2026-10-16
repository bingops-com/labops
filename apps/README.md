# GitOps applications

LabOps has one CAPI workload environment: `labprod`. `labmgmt` remains the
Terraform-owned management cluster and does not host applications.

There are no alternate production or staging overlays. The `clusters/labprod`
directories are retained as explicit Kustomize boundaries for the sole
workload cluster.

Argo CD is bootstrapped from `apps/argocd/clusters/labprod` and the root
Application `apps/gitops/bootstrap/labprod.yaml`. The root reconciles
`apps/gitops/clusters/labprod`; platform components use negative sync waves
and workloads use wave zero. Every active Application, including Games and the
root, enables automatic synchronization, pruning and self-healing. A reviewed
LabOps merge selects desired state; application image publication precedes any
immutable version update. Dormant applications excluded from the root remain
outside this policy. Restore and maintenance procedures retain their explicit
write-freeze and reconciliation-suspension steps.
The `rom-labprod` migration target passed its restore and acceptance gates and
is now the production ROM stack, including its one-click catalogue of curated
homebrew and freely distributable games. The former `romm-labprod` Application,
namespace and local volumes were retired after the accepted migration; the R2
file archive and Barman backup remain the recovery sources.

Production names under `lab.bingo` are explicit. Cloudflare Tunnel publishes
`auth.lab.bingo`, `portfolio.lab.bingo`, `rom-requests.lab.bingo`,
`rom.lab.bingo`, `slots.lab.bingo`, `games.lab.bingo`, `ghost.lab.bingo`
and `status.lab.bingo`; `bingops.com` and
`www.bingops.com` reach the portfolio. Argo CD and Grafana remain private
through exact-name Tailscale split-DNS routes, Coder and its dynamic `dev.lab.bingo` previews use the private
`lab.bingo` parent route, and the LabOps Portal is
private at the `lab.bingo` apex. The private names resolve to `192.168.10.151`;
the private DNS zone `lab.bingo` forwards every other name (for example
`auth.lab.bingo`) to public resolvers. TLS uses the Bitwarden-delivered
cert-manager token and Cloudflare DNS-01.

Secrets are represented only by BitwardenSecret mappings. The sole Bitwarden
machine token is injected with `./hacks/bootstrap-bitwarden.sh labprod`.
PostgreSQL backups use the Terraform-owned `bingops-cnpg-labprod` R2 bucket.

Coder's operator-managed database and retained experimentation workspace are
defined in `workloads/coder`. Its native SSH NodePort remains private through
the existing LAN/Tailscale route. Deployment and recovery acceptance are
tracked in [the Coder runbook](workloads/coder/README.md).
The independent `dev-labprod` Application follows
[`bingops-com/dev`](https://github.com/bingops-com/dev) for the development dashboard
and discovery/gallery agent; LabOps retains its Coder ingress, TLS and repository allowlist.

Render before delivery:

```sh
kubectl kustomize --enable-helm apps/argocd/clusters/labprod >/dev/null
kubectl kustomize --enable-helm apps/gitops/clusters/labprod >/dev/null
```

Bootstrap after the cluster is ready:

```sh
kubectl --context labprod apply -k apps/argocd/clusters/labprod
kubectl --context labprod apply -f apps/gitops/bootstrap/labprod.yaml
```

Those commands are live operations and require explicit authorization. Normal
delivery is a reviewed merge to `master`; Argo CD then reconciles production.
See [the application runbook](../docs/gitops-applications.md).
