# Games

Prepared public multiplayer service at `https://games.lab.bingo`. Argo CD reads
the public Games chart at an immutable commit, with the matching commit image.
LabOps owns namespace, values, Bitwarden mappings, database backups, Cloudflare
routing and DNS. `games-labprod` and `mail-labprod` remain manually synchronized.

## Reconstruction and inputs

1. Rebuild storage, Bitwarden, CloudNativePG/Barman, cert-manager, monitoring and
   the Cloudflare connector. The read-only check on 2026-10-12 found Flannel
   v0.28.4 and kube-proxy without any NetworkPolicy controller. Adding/reviewing
   enforcement and proving isolation remain blocking requirements for public
   Games. Do not replace the live CNI during an application sync.
2. The chart and image use merged Games commit
   `45b139864ed0e58c4184a36a0e7ef9283725c65c`; its security-gated publication
   succeeded and the image is publicly available. For future releases, publish
   the pinned commit image and verify its exact tag before updating chart/image
   together. Repository and package visibility are independent. Verify anonymous
   pulls of both the Games and Postfix images before sync; Postfix is published
   by LabOps CI after merge.
3. Recover the existing bucket-scoped R2 key from Bitwarden `labprod`. The tracked
   mapping exposes identifiers only. CNPG generates the database URI; Games
   owns R2 prefix `games`, continuous WAL archiving and daily 14-day backups.
4. Prepare the local Postfix relay using
   [its owning runbook](../../platform/mail/labprod/README.md). It owns the
   SMTP password/DKIM key creation and rotation, DNS inputs, certificate,
   durable queue, direct-delivery requirements and isolated tests. No external
   transactional email account is required.
5. After explicit deployment authorization, sync Mail first, check TLS and
   health, then sync Games. Controllers retry missing dependencies and the
   namespace token bootstrap is idempotent. A partial failure requires fixing
   the declared input and retrying, without copying or printing credentials.

The helper accepts only the SMTP password and DKIM **UUIDs**, never values:

```sh
python3 apps/workloads/games/configure-smtp.py SMTP_PASSWORD_UUID DKIM_PRIVATE_KEY_UUID
```

It creates three Bitwarden mappings: the shared SMTP password in Games and
Mail, and the DKIM private key only in Mail. Repeated runs do not duplicate
resources. Its optional public DNS flags populate Terraform configuration.
The real identifiers are now tracked in
[`clusters/labprod/smtp-secret.yaml`](clusters/labprod/smtp-secret.yaml) and
Mail's SMTP/DKIM mappings. Recover the existing `games-smtp-password` and
`games-dkim-private-key` entries from Bitwarden during reconstruction; rerun
the helper only when their identifiers change. The machine account must have
read access to both entries in `labprod`; configuration alone does not prove
that access or the secret values are valid.
No invented IP or private key is committed. Public SMTP DNS metadata remains
unset, and delivery, isolation and runtime acceptance still block public use.

## Production acceptance

- Accounts are public pseudonymous player identities with no administrator role
  or operator UI; Authentik is not applicable.
- Games verifies mandatory STARTTLS from `relay.mail.svc:587` against the
  `smtp.games.lab.bingo` certificate and authenticates with a Bitwarden password.
  SMTP egress selects only the internal relay; Postfix independently refuses
  anonymous relay access even before NetworkPolicy enforcement.
- Ingress selects only the `bingops` Cloudflare connector in `cloudflare`.
  Confirm actual pod labels, show unrelated pods cannot reach Games, and prove
  that trusted proxy headers cannot be supplied through an untrusted path.
- The CNPG cluster `games-postgresql` uses 2 GiB local-path, one instance and
  generated `games-postgresql-app` credentials. Verify WAL archiving,
  `ContinuousArchiving=True`, a completed backup, and an isolated restore.
  See [CNPG recovery](../../../docs/infrastructure/cloudnative-pg.md).
- Games is one replica with Recreate. Upgrades interrupt live games, then restore
  occupied rooms in the lobby. Empty rooms expire after ten minutes. PostgreSQL
  outages must remove `/healthz` readiness without failing `/livez` liveness.
- Test real HTTPS, secure cookies, confirmation/recovery to a controlled mailbox,
  eight-letter joins, every game, reconnection, host handover and bounded load.
  Verify SPF/DKIM/DMARC and actual receipt; never collect reset links in logs.
  Neither local tests nor YAML rendering prove direct SMTP deliverability.

## Safe verification

```sh
helm template games /path/to/games/chart --namespace games --values apps/workloads/games/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/workloads/games/clusters/labprod >/dev/null
kubectl kustomize apps/platform/mail/labprod >/dev/null
terraform -chdir=terraform/cloudflare fmt -check
```

Read-only checks after deployment authorization:

```sh
kubectl --context labprod get application games-labprod mail-labprod -n argocd-system
kubectl --context labprod get deployment,pod,cluster,scheduledbackup,backup -n games
curl -fsS https://games.lab.bingo/healthz
curl -fsS https://games.lab.bingo/livez
```

## Recovery and rollback

Follow the pinned Games README to restore CNPG into a new cluster/release:
`recovery.serverName=games-postgresql-g1`, with a distinct new archive generation.
Verify a synthetic account and resumed archiving before an authorized cutover.
Never change an existing cluster's bootstrap or overwrite earlier archives.

Roll back image and chart together. The database is protected by Helm keep;
do not delete namespace, PVC or R2 archives to roll back application code.
Restore creation, DNS cutover and cleanup are separate authorized operations.

Git/runbooks describe reconstruction, ownership and dependency order. R2/SMTP/
DKIM secrets recover from Bitwarden; CNPG and cert-manager regenerate their
application/TLS credentials. Helpers and controllers can retry after partial
failure. Safe verification is documented above. Remaining gaps are public mail
DNS metadata, Bitwarden access/value validation, direct deliverability,
NetworkPolicy enforcement and runtime acceptance.
