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

- Player accounts have no administrator role. The separate operator UI requires
  Authentik as described below; ordinary and bootstrap accounts must be denied.
- Ingress selects only the `bingops` Cloudflare connector in `cloudflare`.
  Check actual labels, prove unrelated pods cannot reach Games and verify that
  an untrusted caller cannot supply trusted proxy headers. Server egress is DNS
  and PostgreSQL, plus TCP/443 to declared Cloudflare ranges for Authentik;
  backup networking belongs to the CNPG/Barman operators.
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

## Administration

`https://games.lab.bingo/admin/` uses Authentik's `games-admin` public PKCE
provider, declared in `apps/platform/authentik/blueprint.yaml`. The sole
administrator is `bingops`, also required to belong to `games-admins` and have
an active account. `akadmin` and ordinary Authentik users are denied. Games
checks current userinfo on each protected request. Issuer, audience, signature,
expiry, nonce and browser-bound single-use state are verified; forwarded identity
headers and player cookies confer no administrator rights. The opaque, Secure,
HttpOnly administrator cookie lasts at most 15 minutes, with no refresh token.
Tokens and pending PKCE verifiers live only in bounded server memory and vanish
on restart. Local logout ends the Games administrator session, not Authentik SSO.

The panel lists bounded pages of players, room metadata and reports. Operator
actions can resolve/dismiss reports or revoke player sessions and WebSockets;
they require a CSRF token and a written reason, committed with the action to
`admin_audit`. No API edits or deletes this journal. Revocation is not a ban:
the player may sign in again. Passwords, historical email and recovery codes are
never exposed to the panel. There is no password-reset bypass or room-close
operation. Existing migrations are preserved; schema migration 8 is additive.

Rebuild order: Authentik including the existing `bingops` identity and the new
blueprint, then the published Games commit image and matching chart, then the
authorized Games synchronization. Both pins now select merged Games commit
`0b9458ac3e48488724fbf5d5d15ee3bfc26aaed2`. Its public Linux/amd64 image was
verified anonymously with digest
`sha256:8129c282d7120b01e4076ebf21380777dcbe706a66cab77cef0a374b8aa704ed`
on 2026-10-12. For future releases, verify publication before advancing both pins.

Before the first migration to schema 8, create the release-specific on-demand
backup below and require phase `completed`. The manifest is an operator action,
deliberately outside the Argo CD Kustomization; the resulting backup and R2 objects
are generated recovery state. Reapplying the same manifest is idempotent and does
not create a second backup. Future upgrades must use a new reviewed checkpoint
name rather than reusing this completed backup. This checkpoint does not replace
the declared daily ScheduledBackup or a tested isolated restore. The checkpoint
completed successfully on 2026-10-12 before the administrator upgrade, with
`LastBackupSucceeded=True` and `ContinuousArchiving=True`.

```sh
kubectl --context labprod apply -f apps/workloads/games/operations/pre-admin-0b9458ac-backup.yaml
kubectl --context labprod get backup games-pre-admin-0b9458ac -n games -o jsonpath='{.status.phase}'
```

`networkPolicy.adminTo` follows [Cloudflare's IPv4 ranges](https://www.cloudflare.com/ips-v4),
reviewed on 2026-10-12. Review changes to those ranges declaratively. The server's
OIDC client permits only the issuer's HTTPS origin and refuses redirects.
Authentik outages deny administration while public play stays available. No
new secret is introduced: the operator password and Authentik signing key use
their existing recovery process in `docs/authentik.md`. Group removal is the
declarative revocation path; repeating it or blueprint reconciliation is safe.

After an authorized deployment, test `/admin/` as `bingops`, ordinary user and
`akadmin`. Group-removal and inactive-account denial are covered by isolated
signed-issuer tests; a live revocation test of the sole `bingops` identity needs
separate authorization and a documented restoration path. Verify mutation reasons in the journal and player
HTTP/WebSocket revocation without collecting any token or recovery code. Confirm
the declared NetworkPolicy is enforced and that only TCP/443 to the issuer
works. An Authentik failure must not affect `/healthz` or `/livez`.

## Safe verification

```sh
helm template games /path/to/games/chart --namespace games --values apps/workloads/games/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/workloads/games/clusters/labprod >/dev/null
kubectl kustomize apps/gitops/clusters/labprod >/dev/null
python3 apps/platform/authentik/tests/check_games_admin.py
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
This release adds migration 8; earlier binaries, including the recovery-code
release, reject the newer schema and are not valid image-only rollbacks.
Database restoration is a separate
operation with its own recovery point and acceptance checks. CNPG is protected
by Helm keep; do not delete namespace, PVC or R2 archives to roll back app code.

Git/runbooks own reconstruction and dependency order. R2 credentials recover
from Bitwarden; CNPG regenerates application credentials. Recovery hashes follow
database backups and the mandatory post-restore invalidation above. Bootstrap
can retry after partial failure; live cleanup is explicitly separate. Remaining
production gates are NetworkPolicy enforcement and runtime/isolated-restore
acceptance. The pinned image is published and the pre-upgrade base backup is
complete. The authorized application upgrade does not replace Flannel or claim
that its declared NetworkPolicy is enforced; that existing cluster limitation
still needs a separately reviewed policy-controller change. SMTP delivery is no
longer a gate.
