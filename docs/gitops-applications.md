# GitOps application delivery

There is one workload environment, `labprod`. Every application has one
production overlay at `apps/workloads/<app>/clusters/labprod` and one Argo CD
Application at `apps/gitops/clusters/labprod/<app>.yaml`.

Use immutable image tags or digests. Public hostnames must be added explicitly
to `terraform/cloudflare/locals.tf` and `apps/cloudflare/bingops/values.yaml`.
Private Argo CD and Grafana names stay on Tailscale split DNS. Secret values
belong in the Bitwarden `labprod` project; Git contains only UUID mappings.

Validate locally before merging:

```sh
kubectl kustomize "apps/workloads/${APP_NAME}/clusters/labprod" >/dev/null
kubectl kustomize --enable-helm apps/gitops/clusters/labprod >/dev/null
```

`master` is the declared production revision. A reviewed merge is the normal
deployment authorization. For an exceptional branch deployment, first push the
branch, inspect `./hacks/deploy.sh diff prod --revision <branch>`, then run
`./hacks/deploy.sh deploy prod --revision <branch>`; the helper asks for an
additional confirmation. Return to `master` with
`./hacks/deploy.sh restore prod`.

Verify without reading Secrets:

```sh
./hacks/deploy.sh status prod
kubectl --context labprod get applications -n argocd-system
```

Rollback by reverting the production commit or restoring `master`, then wait
for Argo CD to report Synced and Healthy.
