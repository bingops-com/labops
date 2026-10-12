# Dormant Postfix preparation

Games now uses offline single-use recovery codes. It has no SMTP dependency,
and `mail.yaml` is excluded from `apps/gitops/clusters/labprod/kustomization.yaml`.
The retained Postfix manifests/image/tests are optional infrastructure artifacts;
do not synchronize them as part of a Games deployment.

The previous SMTP password and DKIM mappings refer to existing Bitwarden entries
`games-smtp-password` and `games-dkim-private-key` in `labprod`. Games no longer
mounts or reads either entry. This change does not revoke credentials, delete
Secrets, remove a PVC or change a running relay. Check actual consumers and
obtain separate authorization before cleanup or reuse.

For future reuse, declare the new consumer, sender domain, secret mappings,
certificate and network policy in Git, update this runbook and review the relay's
egress path before deployment. Direct SMTP needs verified TCP/25, fixed egress,
provider PTR, reputation and mail DNS. An authenticated upstream relay needs
its own Bitwarden credentials, verified TLS and provider sender authorization.
The Cloudflare website tunnel does not supply SMTP delivery.

The legacy direct-delivery DNS remains disabled by `games_mail = null` in
`terraform/cloudflare/games-mail-settings.tf`. No external prerequisite for mail
blocks reconstruction of Games.

The retained isolated image tests use synthetic credentials and an internal
Docker network; they send no external mail:

```sh
python3 apps/platform/mail/tests/check.py labops-postfix:check
```
