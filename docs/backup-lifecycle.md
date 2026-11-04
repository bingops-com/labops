# Backup lifecycle and retired databases

This is the current lifecycle policy after the 2026-11-04 audit. Resource names
and apparent age alone do not establish that data is obsolete. Match live
application credential references, database sessions and desired state first.

| Data | Owner and consumers | Current policy |
| --- | --- | --- |
| `games/arcade-postgresql`, R2 `arcade/` | Arcade; Games, Slots and CKA | Active database, WAL and daily backups. Preserve production and its recovery chain. |
| `games/games-postgresql`, R2 `games/` | Games LabOps overlay, historical pre-cutover data | Retained Cluster/PVC; hibernated, PDB disabled, daily backup suspended. |
| `slots/slots-postgresql`, R2 `slots/` | Slots LabOps overlay, historical pre-cutover data | Retained Cluster/PVC; hibernated, PDB disabled, daily backup suspended. |
| `ghost/ghost-postgresql`, R2 `ghost/` | Ghost retained-data Application | Retained Cluster/PVC; hibernated, PDB disabled, PodMonitor removed, daily backup suspended. |
| Six isolated Arcade restore/rehearsal copies | Operator-created fixtures outside GitOps | Already hibernated; retained until exact-target deletion is confirmed. See Arcade runbook for names and restore fixtures. |
| ROM, R2 `romm/` and `rom-files/` | Active ROM stack | Keep both database and file backups. The old `romm/` prefix still contains the active `rom-postgresql-g2` archive generation. |
| AFFiNE, Authentik, Coder and retained Coder home | Their owning Applications/runbooks | Keep database, WAL and declared file backups. |
| Project Zomboid | PZ workload; dedicated `bingops-pz-labprod` bucket | Keep the active server's file backup. A stopped old VM is not permission to purge current backups. |

The stopped databases keep their original Cluster and PVC identities. Games and
Slots chart CNPG generation is disabled; LabOps explicitly owns the same
Cluster/ScheduledBackup objects through `retained-postgresql.yaml` and the
ObjectStore through each overlay's `object-store.yaml`. Application manifests
continue to select Arcade credentials. Reconciliation must not replace the
production database or roll application pods merely to freeze old sources.

Hibernation stops PostgreSQL and WAL writers; `ScheduledBackup.spec.suspend=true`
stops new base backups. Retaining the ObjectStore and credential synchronizer
does not create backups. Their Bitwarden mappings remain for access to archived
data and token rotation. Do not remove shared credentials as incidental cleanup.
Historical Backup CRs and R2 objects remain recovery state. The audited R2 bucket
lifecycle only aborts incomplete multipart uploads after seven days; it has no
object expiration. Frozen archives are not a continuously refreshed recovery
window, and the local retained PVCs are not additional remote backups.

## Destruction boundary

Deletion of any Cluster, PVC, generated Secret or remote archive is a separate
irreversible step: confirm exact namespace/name or bucket/prefix and the recovery
loss first. In particular, the shared CNPG bucket also contains active Arcade,
ROM, Coder, AFFiNE and Authentik data. Never use a whole-bucket purge to clean up
one retired application. Inventory a prefix, stop its writers, and use a bounded
prefix-only plan if that exact deletion is approved. Deleting a Cluster may
cascade to its owned PVCs and generated Secrets; inspect ownership before acting.
Declared local-path PVC sizes are not real disk reservations; measure filesystem
usage before claiming recovered capacity.

## Reconstruction and recovery

Git owns the lifecycle declarations; Argo owns delivery and CNPG owns Pods,
services and generated database credentials. Storage and CNPG/Barman must exist
before Arcade recovery; its credentials must be distributed before Games, Slots
and CKA start. Recover current production from the common Arcade backup, never
from stale standalone Games/Slots sources. The owning
[Arcade runbook](../apps/workloads/arcade/README.md) covers contracts and acceptance.

An ordinary rebuild must not revive Ghost or initialize empty historical
sources. Before rebuilding an empty cluster, pause the affected Applications in
Git or exclude their retained Cluster manifests until a deliberate historical
restore is approved. Existing `initdb` stanzas describe original creation; they
are not recovery instructions. Restore into an isolated Cluster using bootstrap
recovery and a new archive generation, then commit its intended lifecycle before
resuming reconciliation. Never reuse an existing archive generation for initdb.

Non-Git inputs are the retained PVC contents, Barman/file archives, the existing
Bitwarden machine token and least-privilege bucket key. The LabOps operator owns
creation, rotation and recovery of shared credentials in the
[CNPG runbook](infrastructure/cloudnative-pg.md) and the file-backup workload
runbooks. Git contains identifiers only. Database application credentials are
CNPG-generated and distributed through Arcade's idempotent reconciler; never
export their values into Git or diagnostic reports.

Reapplying these declarations after partial failure is idempotent for existing
retained data. A missing Cluster/PVC is a restore gate: do not blindly create an
empty replacement. A retry of any separately authorized deletion must check UID
and ownership and treat an already-absent approved fixture as complete.

## Verification without secrets

```sh
kubectl --context labprod get scheduledbackup -A
kubectl --context labprod -n games get cluster games-postgresql -o jsonpath='{.metadata.uid}{" "}{.status.conditions}{"\n"}'
kubectl --context labprod -n slots get cluster slots-postgresql -o jsonpath='{.metadata.uid}{" "}{.status.conditions}{"\n"}'
kubectl --context labprod -n ghost get cluster ghost-postgresql -o jsonpath='{.metadata.uid}{" "}{.status.conditions}{"\n"}'
kubectl --context labprod get pods -A -l cnpg.io/cluster
kubectl --context labprod -n games get cluster arcade-postgresql
kubectl --context labprod get applications -n argocd-system
```

Require hibernation condition `True` with reason `Hibernated`, no retired database
pod/PDB/PodMonitor, suspended schedules, unchanged retained Cluster/PVC identities,
active common backups, and healthy Games/Slots/CKA. Check archive timestamps and
counts without reading object contents. No Secret data is needed for acceptance.
