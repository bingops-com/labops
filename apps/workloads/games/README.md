# Games

Prepared public multiplayer service at `https://games.lab.bingo`. Argo CD reads
the public Games chart at an immutable commit, with the matching commit image.
LabOps owns namespace, R2 mapping, database backups, Cloudflare routing and DNS.
`games-labprod` stays manually synchronized until production acceptance passes.
Merging preparation does not authorize deployment or public opening.

## Reconstruction and inputs

1. Rebuild storage, Bitwarden, CloudNativePG/Barman, monitoring and the Cloudflare
   connector. Demonstrate NetworkPolicy enforcement before synchronizing Games.
   The observed Flannel v0.28.4 installation has no policy controller; review
   enabling enforcement separately. Do not replace the CNI during an app sync.
2. Publish the Games image for the exact commit pinned in `games.yaml` and
   `values.yaml`, and verify an anonymous pull before deployment. Chart and image
   must advance together. The recovery-code release requires a new image;
   the previously published mail-based image does not implement these routes.
   If merging Games changes the commit SHA, update both pins to the resulting
   merge commit after its image CI succeeds. Never synchronize an unpublished
   branch-commit image.
3. Recover the bucket-scoped R2 key from Bitwarden `labprod`. The mapping exposes
   identifiers only. CNPG generates the database URI; Games owns R2 prefix
   `games`, continuous WAL archiving and daily backups retained for 14 days.
4. After explicit deployment authorization and the isolation check, synchronize
   Games directly. No mail relay, SMTP account, SMS or mail DNS is required.
   The namespace token bootstrap is idempotent and controllers retry dependencies.
   Correct declared inputs after partial failure and retry without copying secrets.

## Accounts and recovery codes

Registration needs a pseudo and password. Ten random single-use recovery codes
are shown once, with a private download and an acknowledgement before closing.
PostgreSQL stores only their SHA-256 hashes; there are no codes in Git, logs,
URLs, browser localStorage/sessionStorage or normal account responses.

Recovery needs the pseudo, one code and a new password. The code is consumed,
the password changed and all previous sessions revoked atomically. The other
codes remain valid. The player is then signed in. Regeneration from “Mon compte”
requires the current password, invalidates the old set and revokes other devices.
The UI displays only the number remaining after the initial display is closed.

Existing accounts keep their credentials and see a warning when they have no
codes. They generate their own codes after signing in. The application no longer
reads or exposes historical email fields, and previous mail recovery routes are
disabled. Without both password and saved codes, access cannot be recovered by
an operator. Players own the safe storage of their plaintext codes; they are not
operator secrets and do not belong in the LabOps Bitwarden project.

The old Mail Application is excluded from the GitOps root. Legacy SMTP/DKIM
Bitwarden entries and optional Postfix artifacts are dormant; this change does
not delete live credentials, volumes or DNS. `games_mail = null` keeps mail DNS
disabled. The abandoned WAN-IP preparation in other checkouts must not be applied.

## Production acceptance

- Accounts have no administrator role or operator UI; Authentik is not applicable.
- Ingress selects only the `bingops` Cloudflare connector in `cloudflare`.
  Check actual labels, prove unrelated pods cannot reach Games and verify that
  an untrusted caller cannot supply trusted proxy headers. Server egress is DNS
  and PostgreSQL only; backup networking belongs to the CNPG/Barman operators.
- Verify registration without email, code download, count after use, rejection
  of a used code, regeneration, old-code rejection and HTTP/WebSocket revocation.
  Codes must not be collected in screenshots, logs or support tickets.
- The CNPG cluster `games-postgresql` uses 2 GiB local-path, one instance and
  generated `games-postgresql-app` credentials. Check `ContinuousArchiving=True`,
  a completed backup and an isolated restore. See
  [CNPG recovery](../../../docs/infrastructure/cloudnative-pg.md).
- Games has one replica with Recreate. Upgrades interrupt active games, then
  restore occupied lobbies. Empty rooms expire after ten minutes. A PostgreSQL
  outage removes `/healthz` readiness without failing `/livez` liveness.
- Verify HTTPS, secure cookies, eight-letter joins, every game, reconnection,
  host handover and bounded load before public use.

## Safe verification

```sh
helm template games /path/to/games/chart --namespace games --values apps/workloads/games/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/workloads/games/clusters/labprod >/dev/null
kubectl kustomize apps/gitops/clusters/labprod >/dev/null
terraform -chdir=terraform/cloudflare fmt -check
```

Read-only checks after an authorized deployment:

```sh
kubectl --context labprod get application games-labprod -n argocd-system
kubectl --context labprod get deployment,pod,cluster,scheduledbackup,backup -n games
curl -fsS https://games.lab.bingo/healthz
curl -fsS https://games.lab.bingo/livez
```

## Recovery and rollback

Follow the pinned Games README to restore CNPG into a new cluster/release, using
`recovery.serverName=games-postgresql-g1` and a distinct new archive generation.
Never change the bootstrap of an existing cluster or overwrite earlier archives.

A database restore can resurrect already-consumed recovery codes and sessions.
Before reconnecting public traffic, explicitly authorize and run this invalidation
against the **isolated restored cluster only**, adapting its pod name:

```sh
kubectl --context labprod exec -n games games-restore-postgresql-1 -- psql -U postgres -d games -v ON_ERROR_STOP=1 -c 'BEGIN; DELETE FROM recovery_codes; DELETE FROM sessions; COMMIT;'
```

Verify zero remaining codes/sessions without printing hashes, test a synthetic
account and resumed archiving, then perform the separately authorized cutover.

```sh
kubectl --context labprod exec -n games games-restore-postgresql-1 -- psql -U postgres -d games -v ON_ERROR_STOP=1 -c 'SELECT (SELECT COUNT(*) FROM recovery_codes) AS remaining_codes, (SELECT COUNT(*) FROM sessions) AS remaining_sessions;'
```

Players sign in with the password present in the restored backup and generate
fresh codes. A forgotten password with no surviving recovery credential cannot
be recovered; never re-enable historical mail recovery to bypass this rule.

Roll back image and chart together only to a release compatible with the schema.
This release adds a migration; the prior mail-based binary rejects the newer
schema and is not a valid image-only rollback. Database restoration is a separate
operation with its own recovery point and acceptance checks. CNPG is protected
by Helm keep; do not delete namespace, PVC or R2 archives to roll back app code.

Git/runbooks own reconstruction and dependency order. R2 credentials recover
from Bitwarden; CNPG regenerates application credentials. Recovery hashes follow
database backups and the mandatory post-restore invalidation above. Bootstrap
can retry after partial failure; live cleanup is explicitly separate. Remaining
production gates are publication of the pinned image, NetworkPolicy enforcement
and runtime/backup/restore acceptance. SMTP delivery is no longer a gate.
