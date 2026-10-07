# Bitwarden Secrets Manager

LabOps uses one Bitwarden US project for the sole workload environment,
`labprod`. Git owns the operator Applications and BitwardenSecret UUID
mappings; the project owns plaintext values.

The machine account needs read-only access to that project. Store its token
outside Git and inject it idempotently:

```sh
BWS_LABPROD_ACCESS_TOKEN='<token>' ./hacks/bootstrap-bitwarden.sh labprod
```

Rotate a lost token in Bitwarden, rerun the helper, and revoke the old token
after mappings report success. Verification must inspect resource readiness and
Secret key names only, never values.
