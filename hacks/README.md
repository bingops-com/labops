# Operator helpers

- `cluster-setup.sh` installs client access for the fixed `labmgmt` management
  cluster and sole `labprod` workload cluster.
- `capi-init.sh` installs the pinned providers on `labmgmt`.
- `bootstrap-bitwarden.sh labprod` creates namespace-local operator tokens
  from `BWS_LABPROD_ACCESS_TOKEN` without printing it.
- `deploy.sh` diffs, temporarily deploys, reports or restores production Argo
  CD Applications. Deployment asks for explicit confirmation.
- `retire-lost-kube-vms.sh` is reserved for the documented total-disk-loss
  recovery and must receive the exact approved VM IDs.
- `purge-r2-bucket.py` reports whether an R2 bucket contains objects and purges
  it only when `--purge` and an exact `--confirm-bucket` value are both given.
  It consumes the ignored Cloudflare Terraform credential without printing the
  token or object names.

Examples:

```sh
./hacks/cluster-setup.sh --management-only
./hacks/cluster-setup.sh
./hacks/deploy.sh status prod
./hacks/purge-r2-bucket.py bingops-cnpg-labtest
```

Kubeconfigs and Talos configs are sensitive generated artifacts installed with
mode 0600. Do not commit them or paste their contents into logs.

The helper seeds the platform bootstrap namespaces. Project Zomboid then
inherits token creation and rotation from `argocd-system` through its
GitOps-managed, least-privilege CronJob; do not inject the token into
`pz-server` manually.
