# Slots

Slots uses [Arcade](../arcade/README.md), the production database shared with
Games and CKA, through the `arcade-database` credential. The legacy
`slots-postgresql` is hibernated recovery data with a suspended daily backup.
LabOps owns it in `retained-postgresql.yaml`; chart CNPG resources are disabled.
See the [backup lifecycle](../../../docs/backup-lifecycle.md).

Slots is the public fictional-credit game at `https://slots.lab.bingo`. Argo CD
combines the Helm chart and immutable application commit from
`bingops-com/slots` with the production values and prerequisite resources in
this directory. Application source merges do not change these pins. The candidate
chart/image pair is `3157ac7f3e8d9c74dd5fb8f2c029cef3419217c8`, the merge of
[Slots PR #6](https://github.com/bingops-com/slots/pull/6), including the previous
[Slots PR #5](https://github.com/bingops-com/slots/pull/5) advance repayment and
[Slots PR #4](https://github.com/bingops-com/slots/pull/4) restorations. The GHCR
package must be public because the pod has no registry credential.

This release improves multiplayer blackjack betting and split hands, adds
optional Perfect Pairs and 21+3 side bets, adjusts its timers, updates icons and
supports bounded repeated Plinko drops while Space is held. The previous
illustration, dialog and shared-account changes are retained. Shared mode
is enabled by the later Arcade cutover, with common database backups. Continuous sea ambience stays removed; action effects,
reel/coin sounds and bonus melodies remain available. Argo CD
replaces the single Slots instance when its image changes, briefly interrupting
play; PostgreSQL accounts, balances and backups are preserved. After an
authorized rollout, reload the page so the service worker updates the cached UI.

Before deployment, require the selected merge commit's master
image workflow to pass and verify anonymous Linux/amd64 access to the pinned
merge-commit image. Never select an unpublished or unmerged branch commit.
The chart and SQL persistence code are unchanged from PR #5; no schema migration
is introduced by this update. After rollout, verify multiplayer split hands,
side-bet settlements and Plinko hold/release behavior, as well as the existing
account and wallet checks below. Advance repayment transfers credits from
balance to score while reducing debt and stores preserved points in
`wallet.banked`, without a new SQL
schema. After the first repayment, an older engine that ignores `banked` is not
a safe rollback unless that wallet field is preserved. The source accounts and
balances must not be reset to force a rollback.

Slots retains automatic Argo synchronization: merging the finalized LabOps PR
triggers the rollout. Games follows the same automatic policy. No
new external inputs or bootstrap actions are introduced. Application publication
precedes LabOps version selection; Argo retries the declared pair idempotently.
An operator can reconstruct it from Git and the existing CNPG/R2 recovery inputs
below and verify health, immutable image tags and readiness without exposing data.

## Acceptance gate

- Database: `games/arcade-postgresql`, shared with Games and CKA.
- Backup: production WAL and daily backups use the `arcade` prefix in the shared
  `bingops-cnpg-labprod` bucket. `slots/` retains pre-cutover archives only.
  The shared R2 key remains in Bitwarden; mappings contain identifiers only.
- Legacy source: `slots-postgresql` must be hibernated, without a pod or PDB,
  with the same 2 GiB PVC and `slots-postgresql-daily.spec.suspend=true`.
- Authentik and administrators: not applicable. Player accounts are
  pseudonymous game identities with no privileged or administrative role;
  there is no operator UI. Administration is exclusively declarative or via
  the server-side `season` command.
- Other durable data: none. The container is read-only and all game state is in
  PostgreSQL.

The Bitwarden token bootstrap is idempotent: it creates the namespace copy on
the first run and patches it after rotation. Reconciliation can recover after a
partial failure; the BitwardenSecret and CNPG controllers retry once their
dependencies exist.

## Verify

```sh
helm lint /path/to/slots/chart
helm template slots /path/to/slots/chart --namespace slots --values apps/workloads/slots/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/workloads/slots/clusters/labprod >/dev/null
kubectl --context labprod get application slots-labprod -n argocd-system
kubectl --context labprod get deployment,pod,cluster,scheduledbackup -n slots
curl -fsS https://slots.lab.bingo/healthz
```

The `kubectl` and `curl` commands are post-merge, read-only checks. Confirm that
the common Arcade cluster is ready, its WAL archival succeeds, a common
`Backup` completes, account creation and ranked play work, and practice still works with the server stopped.
Do not read or print Secret data.

## Recovery and rollback

The R2 credential cannot be recovered from Git; rotate the shared
least-privilege token in Bitwarden if it is lost. Restore production using
[Arcade's common recovery](../arcade/README.md), including current Games and CKA
data. The frozen `slots` prefix is only for isolated historical inspection,
with a distinct new archive generation. Never select the stale standalone
source for a production rollback. Revert compatible image/chart pins together
without deleting any database or archives.
