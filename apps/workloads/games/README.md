# Games

Prepared public multiplayer service at `https://games.lab.bingo`. Argo CD reads
the chart from the public `bingops-com/games` repository at an immutable commit;
the matching public GHCR image must exist before reconciliation. LabOps owns
the values, namespace, Bitwarden mappings, Cloudflare routing and DNS.

The Application deliberately has no automated sync. This change prepares a
deployment; it is not approval to deploy. Keep the PR in draft until SMTP
prerequisites below are committed. After review, merging the tunnel values can
reconcile the route, but Games itself still requires an explicitly authorized
sync. Enable automation in a later reviewed change after acceptance.

## Inputs and reconstruction order

1. Rebuild the platform: local-path storage, Bitwarden Secrets Manager operator,
   CloudNativePG, Barman Cloud, monitoring and the Cloudflare connector. The CNI
   must enforce NetworkPolicy. The read-only check on 2026-10-12 found only
   `kube-flannel` (`ghcr.io/siderolabs/flannel:v0.28.4`) and `kube-proxy`, with
   no policy controller or Flannel policy sidecar. Isolation is therefore a
   **blocking prerequisite**, not an existing protection. Prepare and review a
   policy controller compatible with Talos, keeping Flannel routing and
   kube-proxy, or a separately planned CNI migration; then demonstrate actual
   enforcement before publishing Games. Do not replace the live CNI as part
   of an application sync. See [Flannel policy support](https://github.com/flannel-io/flannel/blob/master/Documentation/netpol.md).
2. Publish the Games commit image through its security-gated CI. GHCR visibility
   is separate from repository visibility: the package owner must set the Games
   package to public. The pod uses no registry credential. Verify an anonymous
   pull of the exact pinned image; never substitute a floating tag.
3. Recover the shared bucket-scoped R2 access key from the Bitwarden `labprod`
   project. The tracked mapping contains only existing identifiers. The bucket
   is `bingops-cnpg-labprod`, Games owns prefix `games`, and the chart creates
   ObjectStore, WAL archiving and daily backups with 14-day retention. See the
   [CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md) for key rotation.
4. Complete SMTP setup below, commit the identifier mapping and public DNS
   records, and review/apply Cloudflare separately. DNS application is not part
   of a PR push. Confirm the provider reports the domain as verified.
5. After explicit deployment authorization, sync `games-labprod`. The bootstrap
   copies the existing Bitwarden machine token from `argocd-system`, then the
   operator creates namespace-local credentials. CNPG generates the application
   URI; no database password is exported. Controller retries and token refresh
   make bootstrap and rotation repeatable after partial failure.
6. Complete the acceptance gate before opening the service to players.

## SMTP setup for the operator

The LabOps operator owns the external Resend account and its recovery/MFA in
their password manager. This is an unavoidable external prerequisite; Git
stores only configuration and identifiers.

1. In Resend, add `mail.games.lab.bingo` as a sending domain, select an available
   EU region, and disable open/click tracking for authentication links. Do not
   enable inbound email. This subdomain is separate from the web CNAME.
2. Copy the exact public DKIM/SPF/MX records supplied by Resend into
   `terraform/cloudflare/games-mail.tf`, `local.games_mail_dns_records` using
   `type`, `name`, `content` and optional `priority`. Add DMARC for this sending
   domain, initially `p=none`, and tighten it after verifying alignment. Mail
   records must remain unproxied. Keep this metadata in Git rather than making
   console-only Cloudflare changes. No DNS values are guessed in this PR.
3. Create a Resend key with **sending access restricted to this domain**. Store
   its value only as `games-smtp-password` in the existing Bitwarden `labprod`
   project; the operator machine account needs read access. Send/store its UUID
   as configuration, never paste the key into chat, a command, Git or a PR.
4. Generate the mapping with the actual UUID and commit the two resulting files:

```sh
python3 apps/workloads/games/configure-smtp.py BITWARDEN_SECRET_UUID
```

The helper accepts only a nonzero UUID, creates `smtp-secret.yaml` and registers
it in Kustomize. It never reads the secret value and is idempotent. Until it is
run, `games-smtp` intentionally does not exist and the Deployment cannot start;
there is no placeholder secret identifier to accidentally deploy.

The chart uses `smtp.resend.com:587`, username `resend`, mandatory STARTTLS with
certificate verification, and `noreply@mail.games.lab.bingo`. The API key becomes
only the `password` key of `games-smtp`. Reference:
[Resend SMTP](https://resend.com/docs/send-with-smtp) and
[domain verification](https://resend.com/docs/dashboard/domains/introduction).
For rotation, create a replacement domain-scoped key, update the same Bitwarden
secret, wait for synchronization, then explicitly restart Games to load the
updated environment. Test delivery before revoking the previous provider key.
If lost, create a new provider key; Git cannot recover its value.

## Acceptance and safe verification

- Authentication: no Authentik or administrator identity. Accounts are public
  pseudonymous player identities without privileged roles; no operator UI exists.
- Network: ingress only from the `bingops` Cloudflare connector in namespace
  `cloudflare`; verify its deployed pod labels match the values. Egress is DNS,
  the local CNPG cluster and public IPv4 TCP/587. Resend addresses can change,
  so SMTP is port-restricted rather than IP-pinned; STARTTLS verifies its name.
  Prove that an unrelated pod cannot reach Games or spoof trusted proxy headers.
- Availability: one replica with Recreate; upgrades interrupt live games, then
  restore occupied rooms in their lobby. Empty rooms expire after ten minutes.
  `/livez` checks the process; `/healthz` also checks PostgreSQL. A database outage
  must remove readiness without causing repeated application restarts.
- Data: all durable account/room state is PostgreSQL. Confirm WAL archival,
  `ContinuousArchiving=True`, a completed backup, and an isolated restore before
  relying on the backup. Local-path and one CNPG instance provide no node HA.
- User flows: real HTTPS and secure cookie, confirmation and password recovery
  to a controlled mailbox, two browsers joining by eight-letter code, every game
  starting, reconnect/host handover, and bounded load within the declared limits.
  Never include authentication links, mail bodies or Secret data in logs/reports.

Offline checks, with a checkout at the pinned Games commit:

```sh
helm template games /path/to/games/chart --namespace games --values apps/workloads/games/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/workloads/games/clusters/labprod >/dev/null
terraform -chdir=terraform/cloudflare fmt -check
```

Read-only checks after authorized deployment:

```sh
kubectl --context labprod get application games-labprod -n argocd-system
kubectl --context labprod get deployment,pod,cluster,scheduledbackup,backup -n games
kubectl --context labprod get bitwardensecrets -n games
curl -fsS https://games.lab.bingo/healthz
curl -fsS https://games.lab.bingo/livez
```

## Recovery and rollback

The generated CNPG application password is recreated by CNPG. R2 credentials
and the SMTP key are recovered/rotated from Bitwarden and their external owners,
never from Git. Follow the pinned Games README's recovery procedure: create a
new cluster/release with `database.cnpg.recovery.enabled=true`, source
`recovery.serverName=games-postgresql-g1`, and a distinct new archive generation.
Verify a synthetic account and resumed archiving before any authorized cutover.
Do not modify the bootstrap of an existing cluster or overwrite old archives.

Roll back by reverting the application image/chart pin together. The database
has Helm keep protection. Do not remove the Application, namespace, PVC or R2
archives to roll back application code. DNS cutover, restore creation and cleanup
are separate infrastructure operations requiring explicit authorization.

An operator can reconstruct from this runbook and Git once the documented SMTP
metadata is supplied. Missing inputs are tracked here rather than in chat;
ownership, ordering, retry behavior and checks are explicit. Policy enforcement
is currently absent; installing and proving it, plus runtime acceptance checks,
remain required before deployment to players.
