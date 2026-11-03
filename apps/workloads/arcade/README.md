# Common Games / Slots accounts and PostgreSQL

The common-account activation follows the reviewed migration below. Keep the
source databases and their backups until explicit retirement. Production
activation requires a restored-data rehearsal, aggregate conservation checks,
a completed common backup and a verified isolated restore. CKA consumes only
the restricted cka_app role after its schema migration.

## Original activation — 2026-11-03 (historical preservation mode)

The common target contains all 4 Games and 7 Slots source principals. Both
homonymous pairs are preserved separately; no passwords were collected or
identities merged. Final source backups were taken after both deployments
stopped gracefully. The final import was compared against the fresh restored
sources, and cka/001 schema plus the restricted role passed a rollback-only
write/read check over trusted TLS. Backup cka-common-accepted-20261103 was
restored into arcade-common-restore; all identity fields, ID mappings, both
statistics tables and CKA schema matched exactly before reopening.

The original clusters, PVCs, archive generations and isolated migration copies
remain retained. After acceptance, hacks/hibernate-arcade-copies.py --apply
stops only the six named copies, retaining their CRs/PVCs. This generated
migration state is outside GitOps; re-running is safe. Resume a specific copy
with kubectl annotate cluster NAME -n NAMESPACE cnpg.io/hibernation=off
--overwrite when needed. Never apply this to the common consumer or either
source cluster. Their retirement requires a separately scoped approval; they
are not production consumers. Rebuild production from the common backup,
never from the frozen pre-cutover source databases. Existing cookies were
revoked at cutover and users must sign in again.

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
The current Flannel installation does not enforce NetworkPolicy. This rollout
therefore provides no packet-level isolation between applications. Games and
Slots remain trusted database owners; CKA uses verify-full TLS and a restricted
SQL role. Enabling a policy engine is a separate cluster-wide change, because
it would also enforce existing policies for other workloads. Do not claim
network isolation from rendered YAML.

## Canonical accounts and profiles — approved policy, 2026-11-04

Games, Slots and CKA use one case-insensitive username directory. For a legacy
collision, retain the earliest `(created_at, id COLLATE "C")` account: its ID,
username, creation time and password remain authoritative. The operator has
explicitly selected this policy; no service selector or double-login proof is
required for this upgrade. The losing password and recovery credentials stop
working. All password sessions are revoked once; players reconnect using the
retained account. Do not change this policy during recovery.

`migration/unify-accounts.sql` upgrades the historical preserve-collisions
layout atomically. Games-owned profile/credits and Slots-owned wallet/score
come from their respective original accounts; separate balances are never
summed. Foreign keys, reports/audit IDs, room and podium JSON exact ID references
are remapped. Modified original identity/progress rows and losing recovery
hashes remain in the private `identity.account_merge_archive`, covered by the
common backup and its access controls. `identity.account_aliases` retains old
IDs; account_links retains service provenance. Unknown composite references or
conflicting primary keys abort the transaction for operator review. No source
cluster, PVC or archive is deleted.

`migration/account-contract.sql` owns the common profile, preferences and stable
verified LabOps SSO subject mapping. Public profiles are opt-in; email, security
settings and preferences remain private. CKA calls eight narrowly scoped SQL
capabilities as `cka_app`; functions are owned by `arcade`, never `postgres`,
use a fixed pg_catalog search path, and grant no direct archive/profile access.
The trusted CKA backend verifies the current session, CSRF and password proofs.
SSO-only identities can create a first password in their own profile. Recovery
codes use the existing Games hash format and work across all three services.

The initial approved username directory is allowlisted once for SSO attachment.
Subsequent registrations cannot claim an unrelated SSO username: linking then
requires the common password plus the verified same-name SSO session. Provider
and subject, rather than a mutable username, keep later SSO logins stable.

Future applications consume the same identity directory and credential contract,
with their data in a separate schema. They must not add a login service selector
or another password table. account_links accepts safe service identifiers rather
than a fixed Games/Slots list. New services still require their own reviewed
integration, session/CSRF boundary and least-privilege role.

### Upgrade an existing common database

1. Run the loopback integration_unified.py rehearsal against the real published
   Games/Slots binaries. Wake only the retained `games/arcade-common-restore`
   clone, wait for its primary, then run:

   ```sh
   python3 hacks/unify-arcade-accounts.py --target rehearsal
   python3 hacks/unify-arcade-accounts.py --target rehearsal --apply
   ```

   The helper compares credentials, independent service fields, references and
   original archives in memory; it outputs counts only. No new physical restore
   volume is needed. Rehibernate the clone after acceptance.
2. Prepare and publish compatible CKA images before the maintenance window.
   Gracefully freeze Games/Slots with both production maintenance flags. Freeze
   only the CKA web Deployment using a temporary committed Application Kustomize
   replicas override; leave the private controller running. Wait until all three
   web Pods are gone. This also stops CKA profile/progress writers.
3. Create a fresh completed common CNPG plugin Backup (generated operator state,
   outside GitOps) after the freeze and
   require healthy WAL archiving. Retain all source data and old backups.
   Execute the committed helper with that backup name:

   ```sh
   python3 hacks/unify-arcade-accounts.py --target production --backup BACKUP_NAME --apply
   ```

   It refuses a live writer, stale/mismatched backup or unready target. SQL is
   executed as the non-superuser schema owner. Each migration marker and its
   transaction make retries safe; original import scripts are historical only.
4. Require a completed post-upgrade backup. Verify a fresh logical dump/restore
   inside the isolated existing clone with private internal comparisons using
   `python3 hacks/verify-arcade-unified-restore.py --backup NAME --apply`.
   It creates and drops only its own randomly named verification database,
   leaving the clone’s existing data and every PVC intact. This
   proves current SQL/data restoration; the original Barman physical restore
   was separately qualified on November 3. A new full physical recovery needs
   additional disk headroom and must not overwrite an existing cluster.
5. Deploy the prepared CKA image, remove its temporary replicas override and both game
   maintenance flags through GitOps. Verify both user views match, public pages
   respond, profile APIs reject anonymous access, and all apps are Healthy/Synced.

Both SQL upgrades are idempotent, including after restore. Before reopening,
rollback requires a reviewed common backup/PITR, never the old frozen Games or
Slots source databases. After writes resume, freeze again before recovery.
No original database, PVC or archive retirement is included.

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
published application images, and Barman backup objects. The current canonical upgrade uses the explicit earliest-account policy, not
player proof collection. After the first migration, after cutover restore the common backup,
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
rehearsal uses PostgreSQL 18 and does not validate Barman or the production CNI.

## Original first-cutover sequence (historical, not an upgrade runbook)

1. Publish/review the Games and Slots changes with shared mode **off**. Keep
   chart/image pins aligned with published merge commits. Deploying, pushing
   and synchronizing require separate explicit authorization.
2. Verify node disk headroom before provisioning copies. This production
   restore encountered DiskPressure with concurrent copies; image GC recovered
   space, but local-path source/target/verification volumes all share the node
   disk. Account for all retained copies and leave ample margin above eviction
   thresholds. Do not bypass DiskPressure with a toleration or delete retained
   databases/PVCs to make a migration proceed. Rehearse the entire flow on disposable restored copies. The excluded
   `rehearsal/labprod` overlay creates three dedicated `-rehearsal` clusters,
   without archivers or public application connections. Use those suffixed
   cluster/service names for the clone rename/port-forward commands below and
   `arcade-pg-services.py --rehearsal` in a separate private client directory.
   Their databases retain the guarded `arcade_*_restore` and `arcade` names.
   Never use the final target for rehearsal or reuse earlier restored snapshots
   for the final cutover. The canonical
   `apps/gitops/clusters/labprod/arcade.yaml` Application owns
   the common database. Reconcile `staging/labprod` and wait for the new cluster/backups/credential
   CronJob. This does not switch either app. Keep both old clusters declared.
3. Choose preserve-collisions mode, or collect proofs for verified merging. For the final cutover, set `maintenance: true` in
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

From an authorized in-cluster operator workspace, --direct-cluster uses the
three fixed restore/target service FQDNs with verify-full TLS and their CNPG
CA Secrets. This avoids unreliable port-forwarding. Otherwise keep each
loopback port-forward in its own terminal. The service generator requires only
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
PGSERVICE=arcade-target psql -X -v ON_ERROR_STOP=1 -f apps/workloads/arcade/migration/merge.sql
```

For preserve-collisions mode, run preserve-collisions.sql after staging instead
of importing proofs/preflight/merge.sql. Then run
hacks/verify-arcade-preservation.py with the same three service environment
variables. It compares all original account fields and game_stats in memory,
prints aggregate counts only, and refuses acceptance on any mismatch.

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
schemas in disposable development databases, stage with preserve-collisions.sql,
then apply unify-accounts.sql and account-contract.sql as arcade. On recovery of an existing installation, use the common backup overlay.
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
