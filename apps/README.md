# GitOps applications

LabOps has one CAPI workload environment: `labprod`. `labmgmt` remains the
Terraform-owned management cluster and does not host applications.

There are no alternate production or staging overlays. The `clusters/labprod`
directories are retained as explicit Kustomize boundaries for the sole
workload cluster.

Argo CD is bootstrapped from `apps/argocd/clusters/labprod` and the root
Application `apps/gitops/bootstrap/labprod.yaml`. The root reconciles
`apps/gitops/clusters/labprod`; platform components use negative sync waves
and workloads use wave zero. Automated pruning and self-healing are enabled.
The temporary `rom-labprod` blue/green target is the sole exception: automated
sync remains disabled until its documented restore and acceptance checks pass.

Production names under `lab.bingo` are explicit. Cloudflare Tunnel publishes
`auth.lab.bingo`, `portfolio.lab.bingo`, `rom.lab.bingo` and the migration
fallback `romm.lab.bingo`; `bingops.com` and `www.bingops.com` reach the
portfolio. Argo CD and Grafana remain private
through exact-name Tailscale split-DNS routes, and the LabOps Portal is
private at the `lab.bingo` apex. The private names resolve to `192.168.10.151`;
the private DNS zone `lab.bingo` forwards every other name (for example
`auth.lab.bingo`) to public resolvers. TLS uses the Bitwarden-delivered
cert-manager token and Cloudflare DNS-01.

Secrets are represented only by BitwardenSecret mappings. The sole Bitwarden
machine token is injected with `./hacks/bootstrap-bitwarden.sh labprod`.
PostgreSQL backups use the Terraform-owned `bingops-cnpg-labprod` R2 bucket.

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
