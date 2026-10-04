# Operator helpers

- `cluster-setup.sh` installs client access for `labmgmt` and `labprod`.
- `capi-init.sh` installs the pinned providers on `labmgmt`.
- `bootstrap-bitwarden.sh labprod` creates namespace-local operator tokens
  from `BWS_LABPROD_ACCESS_TOKEN` without printing it.
- `deploy.sh` diffs, temporarily deploys, reports or restores production Argo
  CD Applications. Deployment asks for explicit confirmation.
- `retire-lost-kube-vms.sh` is reserved for the documented total-disk-loss
  recovery and must receive the exact approved VM IDs.

Examples:

```sh
./hacks/cluster-setup.sh --management-only
./hacks/cluster-setup.sh --workload labprod
./hacks/deploy.sh status prod
```

Kubeconfigs and Talos configs are sensitive generated artifacts installed with
mode 0600. Do not commit them or paste their contents into logs.
