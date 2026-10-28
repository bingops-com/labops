# Common Games / Slots accounts and PostgreSQL

Prepared locally; **not connected to the GitOps root or deployed**. Existing
production pins, databases, backups, namespaces, ingress and Authentik are
unchanged. Do not merge a values switch before the two new application images
and charts are published and the migration has been rehearsed on restored data.

## Data and access

One CNPG cluster, `games/arcade-postgresql`, owns database `arcade` and R2 prefix
`arcade`. It replaces the two physical database instances only after acceptance
and a separately approved retirement. It remains one instance on local-path:
this saves a database process but does not introduce high availability.

`identity.users` contains the common ID, pseudo, Argon2id password and original
Games fields plus Slots wallet/score fields. Games shop credits and Slots
wallets are separate columns, never summed. `identity.sessions` and recovery
hashes are common. Each application retains its own schema and migration ledger:
`games` (version 8) and `slots` (version 1). Their incompatible `game_stats`
tables remain separate. Existing Games IDs, rooms, friendships, items, reports
and audit references are retained; Slots stats are remapped through
`identity.account_links`. The source-ID map is durable recovery state.

Both servers opt in explicitly using `GAMES_SHARED_ACCOUNTS=true` or
`SLOTS_SHARED_ACCOUNTS=true`; unprepared databases are refused. Each site keeps
its own host-only cookie and login screen, with the same credentials. Password
changes, recovery-code rotation/recovery and administrator session revocation
apply to both sites. Account recovery remains in Games; Slots-only players may
sign into Games and generate their codes. Authentik still protects only the
operator panel; player accounts acquire no administrative role.

The first version deliberately trusts both backends as owners of the common
account database; this is not SQL isolation between the two applications.
NetworkPolicy enforcement remains a production gate (the observed Flannel
installation does not enforce it). Do not claim isolation from rendered YAML.

## Collision policy and proof

An overlapping, case-insensitive pseudo is merged only after its owner signs in
with **both** passwords. The resulting ID, display pseudo and password come
from Games, its recovery codes stay valid, and its Slots wallet/statistics are
preserved. Unique accounts keep their ID/password and gain access to both games.

Each affected player runs the helper locally for their own accounts:

```sh
python3 hacks/link-game-accounts.py --output /private/path/my-account-link.csv
```

The helper uses only the two fixed HTTPS login origins, rejects redirects and
prompts for passwords without echo. No password or bearer cookie is persisted.
Its exclusive mode-0600 CSV contains the pseudo and SHA-256 session hashes.
The player sends only this private proof to the migration operator through an
existing private channel. Never collect players' passwords. Proofs are generated
private state, not Git configuration; remove them after acceptance.

Migration verifies both hashes against the **current restored source sessions**,
their user IDs, pseudo and expiration. A revoked/expired proof is refused.
Collect proofs before the final write freeze/backup so those sessions are in
the restore. A same password or same pseudo alone proves nothing. If any
collision lacks proof, the whole merge is refused with no partial changes;
do not discard, silently rename or take over that account to force a cutover.

## Ownership, inputs and reconstruction

LabOps owns the Application, cluster, ObjectStore, ScheduledBackup, PodMonitor,
credential reconciler and migration. Games/Slots own their versioned schemas
and published charts. CNPG generates `games/arcade-postgresql-app` (role
`arcade`); no new password needs a Bitwarden entry. The namespace-local
`games-r2-credentials` mapping reuses the existing bucket-scoped key and token
bootstrap from the Games runbook. Terraform owns the bucket.

The credential CronJob reads only that named CNPG Secret and reconciles
`slots/arcade-database`. Its URI hostname is normalized to the Games namespace
FQDN before copying. Kubernetes `create` cannot be restricted to a resource
name; the target Role therefore permits Secret creation in Slots, while
reads/patches are limited to `arcade-database`. The service account is only
mounted by this job. No credential is printed or committed. After CNPG password
rotation, wait for reconciliation and perform an authorized restart of every
consuming application to refresh its environment.

Ghost is retired. The reconciler no longer copies credentials into its
namespace and its target Role/RoleBinding are removed. Its retained standalone
database remains independent of any Arcade migration; see the
[Ghost runbook](../ghost/README.md).

Non-Git inputs: the existing bucket-scoped R2 key and Bitwarden machine token
(recover/rotate as documented in the [CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md)),
published application images, and Barman backup objects. Player proofs are
needed for the first migration only; after cutover restore the common backup,
never repeat the legacy merge. The Authentik identity/signing-key recovery
process remains in `docs/authentik.md`.

Rebuild order: storage → Bitwarden bootstrap/mapping → CNPG/Barman → Games and
Slots namespaces → ObjectStore → cluster restore → credential reconciler →
published application charts using shared mode → public readiness checks.
`recovery/labprod` restores generation `arcade-postgresql-g1` and archives as
`-g2`. Review both generation names for subsequent incarnations. Never change
bootstrap on an existing cluster. The database image is pinned to
`18.4-system-trixie`, matching both source cluster specifications read on
2026-10-13. Use PostgreSQL 18 clients for the actual import; the local synthetic
rehearsal uses PostgreSQL 17 and does not validate Barman or the production CNI.

## Migration sequence

1. Publish/review the Games and Slots changes with shared mode **off**. Keep
   chart/image pins aligned with published merge commits. Deploying, pushing
   and synchronizing require separate explicit authorization.
2. Rehearse the entire flow on disposable restored copies. The excluded
   `rehearsal/labprod` overlay creates three dedicated `-rehearsal` clusters,
   without archivers or public application connections. Use those suffixed
   cluster/service names for the clone rename/port-forward commands below and
   `arcade-pg-services.py --rehearsal` in a separate private client directory.
   Their databases retain the guarded `arcade_*_restore` and `arcade` names.
   Never use the final target for rehearsal or reuse earlier restored snapshots
   for the final cutover. `application.yaml`
   is the manual-sync Application candidate, excluded from the GitOps root.
   After authorization, add it to the root in the reviewed provisioning change;
   reconcile `staging/labprod` and wait for the new cluster/backups/credential
   CronJob. This does not switch either app. Keep both old clusters declared.
3. Collect player proofs. For the final cutover, set `maintenance: true` in
   **both** application production values, commit and synchronize those values
   under the authorized maintenance window. This declaratively sets both
   Deployments to zero and allows Slots to return in-memory table stakes on
   graceful shutdown. Wait for both pods to stop; do not perform a live dump
   while players can still change passwords or spend credits. The separate
   CNPG clusters and backups continue running.
4. Require fresh completed backups and successful WAL archival for both
   sources after the freeze. Restore **fresh final copies** with
   `operations/restore-sources.yaml`, outside GitOps. Their historical archive
   generations/ObjectStores must match the verified source metadata. Clones
   have no WAL archiver, so they cannot write into source archive generations.
5. On the restored copies only, rename their restored databases to
   `arcade_games_restore` and `arcade_slots_restore`. Configure private libpq
   service entries `arcade-games-copy`, `arcade-slots-copy` and `arcade-target`,
   pointing to those clones and the new empty `arcade` database. A service
   file is generated, private operator client configuration; keep mode 0600
   outside Git and use a private `.pgpass`/runtime credentials, never a URI in
   shell history. Operator access comes from the clone-generated CNPG Secrets
   or approved local pod access; never export a source production password.

The following reviewed commands target only the disposable restore clusters.
They are operator actions requiring deployment/restore authorization. A retry
after the rename should verify the new database name rather than rename again.

```sh
kubectl --context labprod exec -n games "$(kubectl --context labprod get cluster arcade-games-restore -n games -o jsonpath='{.status.currentPrimary}')" -- psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'ALTER DATABASE games RENAME TO arcade_games_restore'
kubectl --context labprod exec -n slots "$(kubectl --context labprod get cluster arcade-slots-restore -n slots -o jsonpath='{.status.currentPrimary}')" -- psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'ALTER DATABASE slots RENAME TO arcade_slots_restore'
kubectl --context labprod port-forward --address=127.0.0.1 -n games service/arcade-games-restore-rw 55463:5432
kubectl --context labprod port-forward --address=127.0.0.1 -n slots service/arcade-slots-restore-rw 55464:5432
kubectl --context labprod port-forward --address=127.0.0.1 -n games service/arcade-postgresql-rw 55465:5432
python3 hacks/arcade-pg-services.py --directory /private/path/arcade-clients
export PGSERVICEFILE=/private/path/arcade-clients/pg_service.conf PGPASSFILE=/private/path/arcade-clients/pgpass
```

Keep each port-forward in its own terminal. The service generator requires only
`get` on `games/arcade-games-restore-app`, `slots/arcade-slots-restore-app` and
`games/arcade-postgresql-app`; renaming additionally requires operator pod exec
on the two clones. The output directory must be 0700 and outside Git; files
are atomic 0600 replacements, safe to regenerate after partial failure or CNPG
rotation. Passwords are recovered from these newly generated CNPG Secrets,
not operator chat/history. Consumers are only the local libpq clients. Remove
the generated directory after acceptance. Safe verification uses
`SELECT current_database(), current_user` through each service, never printing
passwords or Secret JSON. The three loopback ports are generated operator
access configuration and can be changed together with the helper's options.

6. Stage the restored schemas with the guarded helper. It rejects original
   database names, old pg_dump clients and non-empty targets. It renames schemas
   on the disposable copies and streams schema-qualified dumps in one target
   transaction; no dump text replacement or plaintext dump file is used.

```sh
ARCADE_GAMES_RESTORE_SERVICE=arcade-games-copy ARCADE_SLOTS_RESTORE_SERVICE=arcade-slots-copy ARCADE_TARGET_SERVICE=arcade-target bash apps/workloads/arcade/migration/stage-copies.sh
PGSERVICE=arcade-target psql -X -v ON_ERROR_STOP=1 -c '\copy migration.links FROM STDIN WITH (FORMAT csv)' < /private/path/all-account-links.csv
PGSERVICE=arcade-target psql -X -f apps/workloads/arcade/migration/preflight.sql
PGSERVICE=arcade-target psql -X -f apps/workloads/arcade/migration/merge.sql
```

The preflight prints counts only. Require `missing_valid_proofs=0`. If an import
failed before COMMIT the target is unchanged and the clone schema renaming is
safe to retry. If import succeeded but proof-table preparation failed, rerun
`prepare.sql` directly; never overwrite the already staged schemas. The guarded
import deliberately refuses an existing destination on retry. `merge.sql` is
transactional and a second successful execution is a no-op, including after a
restore; it does not revoke new sessions. Account totals are checked in SQL.
Old Slots passwords are removed only from the disposable destination archive;
original databases/backups remain intact.

7. Verify account conservation, independent balances, all related statistics,
   both login directions, recovery and cross-site session revocation. Require
   a completed common backup and an isolated restore before reopening.
   `operations/verify-common-restore.yaml` is the separate, non-archiving
   verification clone of the common generation; inspect aggregate counts and
   schema version there through approved pod-local psql, never output player
   records or passwords. Merge
   the reviewed `cutover/*-values.yaml` settings into the owning production
   values while retaining `database.cnpg.enabled=true`; this keeps source
   clusters/backups tracked and avoids Argo pruning them. Switch both apps
   together, then remove the maintenance flags through the authorized change.
   All players must log in again. Check health and real player acceptance.

## Recovery and rollback

Before reopening writes, rollback simply restores the previous values/credential
selection and removes maintenance mode; source data has remained frozen. After
players write to the common database, switching to stale source databases would
lose their new progress. Freeze again and restore a reviewed common backup/PITR
instead. Both apps share the same restore point. Verify Barman restore on a new
incarnation before deleting any database, PVC, archive or temporary restore.
Retiring the old clusters/restore copies and their historical archives requires
explicit approval of each exact target and is a separate PR.

On a new empty installation with no accounts, initialize the two published
schemas in disposable development databases, stage them and merge without any
proofs. On recovery of an existing installation, use the common backup overlay.
Do not initialize an empty database over lost account data.

## Verification

Offline configuration checks and local integration rehearsal:

```sh
kubectl kustomize apps/workloads/arcade/staging/labprod >/dev/null
kubectl kustomize apps/workloads/arcade/recovery/labprod >/dev/null
kubectl kustomize apps/workloads/arcade/rehearsal/labprod >/dev/null
bash -n apps/workloads/arcade/migration/stage-copies.sh
PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres ARCADE_GAMES_BINARY=/tmp/arcade-games ARCADE_SLOTS_BINARY=/tmp/arcade-slots python3 -B apps/workloads/arcade/tests/integration.py
```

Build the two binaries from the reviewed Games/Slots repositories after their
web builds. The test requires libpq tools, rejects non-loopback connections and
creates only random `arcade_e2e_*` databases and restored fixture copies. It
exercises the real import helper, invalid/expired proofs, atomic refusal,
idempotence, ID/stat/wallet preservation, concurrent registration, both actual
HTTP servers, global revocation, recovery-code reuse denial and dump/restore.
All fixture databases/processes are removed on completion; no production account
or secret is used. CI pins the two application revisions for reproducibility
and uses PostgreSQL 18.4 with matching containerized libpq clients. Its first
remote run requires those application commits to be pushed; local verification
does not substitute for that CI run or the restored-production-data rehearsal.

Post-authorization read-only verification (no Secrets or player data):

```sh
kubectl --context labprod get cluster arcade-postgresql -n games
kubectl --context labprod get backup,scheduledbackup -n games
kubectl --context labprod get cronjob,job -n games
curl -fsS https://games.lab.bingo/healthz
curl -fsS https://slots.lab.bingo/healthz
```

Reproducibility answers: reconstruction follows this runbook and the declared
recovery overlay; non-Git inputs and their recovery owners are listed above;
partial imports roll back, preparation retries safely and successful merges
are idempotent; lifecycle ownership/order is explicit; safe verification uses
counts, health, backup conditions and disposable fixtures. Production PG18,
Barman restore, live collision coverage and enforced network isolation remain
acceptance gates, not claims made by the local PostgreSQL 17 rehearsal.
