# AFFiNE Notes

`https://notes.lab.bingo` runs AFFiNE 0.27.4 on `labprod`, managed by the
`affine-labprod` Argo CD Application. Images are pinned; no upstream Helm chart
or ad-hoc host installation is required. The upstream deployment reference is
<https://github.com/toeverything/AFFiNE/releases/tag/v0.27.4>.

## Ownership and authentication

LabOps owns the namespace, retained PVC, CNPG database, migrations, cache,
initialization, backup/restore Jobs, SSO blueprint, tunnel route and DNS record.
The app and its migration init container run without a ServiceAccount token as
UID 1000. The server runs in production mode and generates its GraphQL schema
in a bounded, disposable `/app/src` volume; the rest of its root filesystem
remains read-only. PostgreSQL uses the operator-managed application credential; it has
no trust-authentication or public Service. Valkey is an internal, disposable
cache, not the recovery source for notes.

Both Cloudflare Tunnel and the private Traefik ingress route the entire notes
hostname through Authentik's embedded proxy. There is no direct public route
to the AFFiNE Service. The `notes-admins` group and both application policies
allow only the active `bingops` account. The shared outpost registration stays
in the existing `romm.yaml` blueprint, preserving the ROM requests provider.

AFFiNE also uses Authentik OIDC at `/application/o/notes-sso/`, with a strict
`https://notes.lab.bingo/oauth/callback` URI, signed tokens and PKCE. The
OIDC application is hidden from the dashboard; the Notes proxy is the visible
launch entry. An internal TLS host alias reuses the existing Traefik address
`192.168.10.151` for `auth.lab.bingo`; update it with that platform endpoint.

The OIDC client is **public**, as in the existing RomM/Coder integrations.
AFFiNE's pinned OAuth provider checks for a nonempty `clientSecret` before
enabling OIDC, so `config.json` supplies an explicitly public compatibility
marker. It is not a credential: Authentik's public-client authorization-code
exchange does not authenticate that value. AFFiNE supplies PKCE and validates
the signed ID token. This avoids creating an additional external secret;
do not change the Authentik client to confidential without adding proper
credential ownership and recovery. Upstream behavior is implemented in
`src/plugins/oauth/providers/def.ts`, `oidc.ts` and Authentik's token view.

The PostSync initializer uses AFFiNE's supported first-admin setup API to
create the account matching the owner's verified Authentik email. Its random
local password is discarded and never logged; normal sign-in is OIDC, not
that password. Reconciliation preserves existing accounts. Change an existing
owner email through AFFiNE administration before changing its IdP email; the
initializer does not rename existing accounts. Ordinary password signup is
disabled; OAuth linking remains enabled behind the owner-only IdP policy.
AI and the optional external indexer are not enabled by this deployment.

## Persistence, backups and retention

CNPG owns `affine-postgresql`, using PostgreSQL 18.4 standard with pgvector
created before the upstream migrations. Its generated `affine-postgresql-app`
Secret supplies database access. The `affine-data` PVC contains `config/`
(including the generated `private.key`) and `storage/` (attachments/avatars).
Namespace, database and data PVC are protected against Argo pruning/deletion.
Local-path requests are not a hard storage quota; monitor actual disk usage.

Backups have two complementary recovery paths:

| Data | Schedule | R2 destination | Retention |
| --- | --- | --- | --- |
| CNPG base backup + continuous WAL | Daily 03:10 UTC | `bingops-cnpg-labprod/affine/affine-postgresql-g1` | 14-day recovery window |
| Complete application archive: pg_dump, config/key and files | Daily 03:20 UTC | `bingops-cnpg-labprod/affine-files/snapshots/<UTC timestamp>.tar.gz` | 14 days from archive timestamp |

The file Job first creates a transaction-consistent custom-format database
dump, then packages configuration and storage. It uploads one immutable
archive with rclone integrity checks, avoiding per-file cloud scans. Only a
successful upload permits cleanup. Cleanup validates timestamped archive names
and deletes exact files older than 14 days; unknown names are retained.
It never uses a source file's modification time as archive age.

The database dump is consistent, while the filesystem is copied live, not an
atomic snapshot across both stores. A file changing during tar causes the Job
to fail and retry. Use a maintenance window for a fully quiescent export before
major upgrades or storage migrations. Combined application recovery may lose
up to 24 hours since the last successful archive; failures extend this window.
R2 archives contain private application material and must remain private.

PostSync hooks initialize the owner, make an initial complete backup, then
restore it into a disposable PostgreSQL instance and filesystem in an
`emptyDir`. The restore-check Pod has no production database credential,
production PVC or ServiceAccount token. Its database listens only on loopback.
It verifies pg_restore, the owner table, private key and storage directory.
Hooks retain completion/failure state and use BeforeHookCreation for retries.
CronJobs run independently after initial acceptance.

## Inputs outside Git and reconstruction

No new external account credential is introduced. The existing bucket-scoped
R2 key and Bitwarden machine token are owned/recovered/rotated through
[the Cloudflare runbook](../../../docs/infrastructure/cloudflare.md) and
the existing Bitwarden bootstrap. The tracked namespace token synchronizer
recreates `bw-auth-token`, then Bitwarden materializes `affine-r2-credentials`.
Do not broaden it beyond the existing backup bucket. Database credentials are
generated by CNPG, and AFFiNE's private key is generated in its retained PVC.
Recover application identity/configuration from the complete archive; do not
start AFFiNE against an empty data PVC when preserving an existing identity.

Rebuild order: R2/Bitwarden, CNPG/Barman, Authentik and shared proxy blueprint,
namespace/token mapping, database/data PVC, migrations/server, initializer,
initial backup and isolated restore check. GitOps owns the order through sync
waves. Recreating a fresh initdb database requires a new archive generation
suffix; an existing Barman prefix must never be overwritten by another cluster
incarnation. Follow [the CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md).

For recovery, preserve the old database/PVC and pause the file CronJob and app
through a reviewed Git change. Download a selected archive into private staging,
restore config/storage to a new PVC and pg_restore into a new database, or use
Barman point-in-time recovery with the matching archived files. Reconcile
migrations only after both data sources are restored. Verify OIDC, documents,
attachments and a new successful backup before retiring the old resources.
The normal PostSync restore-check is the non-destructive validation procedure;
it can be retried by an authorized full app sync. Never restore over the only
production copy or delete the previous data as part of a failed retry.

## Verification and upgrades

```sh
kubectl --context labprod -n argocd-system get application affine-labprod
kubectl --context labprod -n affine get deployment,pod,pvc,cluster,backup,scheduledbackup,cronjob,job,bitwardensecret
```

Require a Ready server, successful owner initialization and initial file
backup, completed isolated restore check, a completed CNPG backup and
`ContinuousArchiving=True`. Anonymous HTTPS requests must redirect to
Authentik; other Authentik users must fail the owner policy. Never print
Secrets, session cookies, private keys, dump contents or full HTTP responses
containing user data. Job summaries and condition fields are sufficient for
routine acceptance. The CronJob's last-success timestamp advances only after
its first scheduled execution, independently from the initial hook Job.

Before an upgrade, take and verify a complete application backup. Pin the new
AFFiNE image in both server and migration containers, review migrations, and
let GitOps rerun the hooks. An image rollback alone may not undo schema changes;
restore the paired database/config/files if upstream does not support rollback.
No direct cluster-only configuration or manual registry setting is needed.
