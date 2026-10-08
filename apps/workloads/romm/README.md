# RomM

RomM 5.3.1 is delivered to `labprod` by Argo CD at
`https://romm.lab.bingo`. Cloudflare Tunnel publishes the hostname and Traefik
terminates its cert-manager certificate. Authentik provides OIDC login through
a public PKCE client, so there is no OIDC client secret to recover.

The workload owns a 200 Gi `local-path` PVC mounted at `/romm`, an ephemeral
Valkey cache, and a one-instance CloudNativePG cluster. CNPG generates the
`romm-postgresql-app` credential; RomM also uses its random password as the
session-signing key. Recreating the database therefore invalidates existing
sessions without introducing a second secret. The database is archived daily
to `s3://bingops-cnpg-labprod/romm` with 14-day retention. The namespace-local
Bitwarden mapping reuses the existing bucket-scoped CNPG R2 credential, copied
by the least-privilege token synchronizer from `argocd-system`.

## Access

Authentik group membership is the source of truth for RomM roles. Members of
`romm-admins` are administrators; every authenticated Authentik user is granted
the normal user role. `bingops` is the sole declared administrator. The setup
wizard is disabled and OIDC registration is explicit, so the first successful
Authentik login creates the RomM account without a local bootstrap credential.
Native password login remains available as a recovery path.

## Data and recovery

Git reconstructs all Kubernetes resources, Authentik configuration, DNS and
tunnel routing. Bitwarden owns the pre-existing CNPG R2 key, whose minimum
permission is object read/write/list on `bingops-cnpg-labprod`; creation,
rotation and recovery are documented in the
[CloudNativePG runbook](../../../docs/infrastructure/cloudnative-pg.md). CNPG
database recovery uses the Barman archive in the RomM prefix.

For a CNPG recovery, declare `database: romm` and `owner: romm` under the
temporary `bootstrap.recovery` configuration and omit `secret`. CNPG generates
a new `romm-postgresql-app` Secret and updates the restored owner's password
after promotion. RomM then reconnects with that generated credential; because
it is also the session-signing key, existing browser sessions are invalidated.
The generated Secret is runtime state, not an input that must be copied out of
the cluster.

The ROM library, downloaded metadata, saves and optional RomM configuration on
`romm-data` are user data and are deliberately not committed or copied to the
database backup. Their owner is the lab operator. Keep legally obtained source
media or an independent encrypted backup outside the cluster, then restore the
expected `library`, `resources`, `assets` and `config` directories below
`/romm`. This is the only input that cannot be recovered from Git or the CNPG
archive. A lost PVC without that external copy is an explicit data-loss gap.

## Validation

Render without contacting the cluster:

```sh
kubectl kustomize apps/workloads/romm/clusters/labprod >/dev/null
```

After a reviewed merge and Argo CD reconciliation, verify without reading any
Secret values:

```sh
kubectl --context labprod get application romm-labprod -n argocd-system
kubectl --context labprod get deployment,pod,pvc,cluster,scheduledbackup -n romm
curl --fail --silent --show-error https://romm.lab.bingo/api/heartbeat >/dev/null
```

Uploading the same library tree again and rescanning is safe after a partial
failure. Kubernetes, CNPG and the token synchronizer reconcile declaratively;
the synchronizer creates or updates only `romm/bw-auth-token`.
