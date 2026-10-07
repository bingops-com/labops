# Bitwarden Secrets Manager

LabOps uses one Bitwarden US project for the sole workload environment,
`labprod`. Git owns the operator Applications and BitwardenSecret UUID
mappings; the project owns plaintext values.

The machine account needs read-only access to that project. Store its token
outside Git and inject it idempotently into the cluster bootstrap namespaces:

```sh
BWS_LABPROD_ACCESS_TOKEN='<token>' ./hacks/bootstrap-bitwarden.sh labprod
```

Rotate a lost token in Bitwarden, rerun the helper, and revoke the old token
after mappings report success. Verification must inspect resource readiness and
Secret key names only, never values.

Workloads that declare an in-cluster token synchronizer do not require another
manual token injection. Project Zomboid copies only the `token` key from the
bootstrap Secret in `argocd-system` to `pz-server` every five minutes. Its
ServiceAccount can read only the named source Secret; in the target namespace
it can create Secrets (Kubernetes RBAC cannot restrict `create` by resource
name) and can read or modify only `bw-auth-token`.
