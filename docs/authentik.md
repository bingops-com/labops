# Authentik application OIDC

Authentik runs only on `labprod` at `https://auth.lab.bingo`. Cloudflare DNS
and the production tunnel publish this hostname; TLS terminates at the Traefik
Ingress with a Let's Encrypt DNS-01 certificate. CloudNativePG owns the
single-instance `authentik-labprod-postgresql` cluster and its 8 Gi persistent
volume in namespace `authentik`; Authentik connects through the generated
`authentik-labprod-postgresql-rw` service.

The `local-path-storage-labprod` Argo CD Application installs Rancher's
local-path provisioner, pinned to `v0.0.36`, before Authentik. Its default
`local-path` StorageClass stores volumes below
`/var/lib/kubelet/local-path-provisioner` on the Talos node selected for the
workload. The path is below Talos' existing writable kubelet data mount; do not
move it below an unmounted `/var/mnt` path, which remains read-only.
The provisioner namespace explicitly permits privileged workloads because its
short-lived volume helper mounts that host path. Without this Pod Security
exception, CloudNativePG remains Pending and Cloudflare returns 502 for Authentik.
This is node-local storage: it survives pod restarts, but it is neither shared
nor replicated and does not replace the PostgreSQL backup required for node or
cluster replacement.

The file-based Authentik blueprint declaratively owns the application OIDC
providers:

| Client | Type | Issuer | Redirect URI |
| --- | --- | --- | --- |
| `argocd` | Confidential | `https://auth.lab.bingo/application/o/argocd/` | `https://argocd.lab.bingo/auth/callback` |
| `argocd-test` | Confidential | `https://auth.lab.bingo/application/o/argocd-test/` | `https://argocd.test.lab.bingo/auth/callback` |
| `grafana` | Public with PKCE | `https://auth.lab.bingo/application/o/grafana/` | `https://grafana.lab.bingo/login/generic_oauth` |
| `grafana-test` | Public with PKCE | `https://auth.lab.bingo/application/o/grafana-test/` | `https://grafana.test.lab.bingo/login/generic_oauth` |

The blueprint also owns the `argocd-admins` and `grafana-admins` groups.
Authenticated users default to read-only access in both applications; members
of the matching group inherit administrator access. Grafana's public clients
use Authorization Code with PKCE and deliberately have no client secret.
Production Argo CD has no Traefik IP allowlist, while test retains its
LAN/Tailscale allowlist. `argocd.lab.bingo` remains private split DNS and is not
published through the Cloudflare tunnel.

## Secrets and recovery

BitwardenSecret mappings deliver the Authentik application key, PostgreSQL
passwords, bootstrap administrator credentials, R2 credentials and the two
distinct Argo CD OIDC client secrets from the `labprod` Bitwarden project.
Grafana has no OIDC or local administrator secret. Plaintext
values must never be recovered into Git or logs. Continuous WAL archiving and
daily base backups under the dedicated production R2 prefix are the durable
recovery source; additional users and credentials remain generated state.

Create and rotate these values directly in the Bitwarden `labprod` project.
Never stage them under `apps/platform/authentik/credentials/` or commit local
copies. Git stores only the non-sensitive project, organization and secret UUIDs.

On a fresh database, Authentik consumes the synchronized `AUTHENTIK_BOOTSTRAP_EMAIL`
and `AUTHENTIK_BOOTSTRAP_PASSWORD` values automatically. Its blueprint creates
`argocd-admins` and adds `akadmin`, so `/if/flow/initial-setup/` is not required.
The bootstrap variables do not reset an existing database. Rotate the exposed
initial password after the first successful login and update the password
manager; never record the replacement in this repository.

## Delivery order

1. Review and apply the Cloudflare Terraform changes for `auth.lab.bingo` and
   the production R2 bucket, then provision its bucket-scoped credentials in
   the `labprod` Bitwarden project.
2. Reconcile local-path storage, the CloudNativePG operator, Barman Cloud and
   `postgresql-labprod`. Wait for the CNPG cluster to become Ready, its PVC to
   become Bound and WAL archiving to succeed before reconciling Authentik.
3. Reconcile Authentik, which disables the bundled PostgreSQL subchart and
   connects to the CNPG read-write service. Keep the retained PVC from the old
   StatefulSet until login and OIDC validation pass; the accepted migration is
   a new empty Authentik database rather than an in-place data conversion.
4. Wait for the bootstrap blueprint to create all four providers and group
   memberships, then reconcile the Argo CD and monitoring Applications.
5. Validate OIDC discovery and all four browser callbacks. The built-in Argo CD
   administrator is disabled declaratively on both clusters; recovery uses a
   reviewed Git revert and Kubernetes core access.

Non-sensitive verification commands:

```sh
kubectl --context labprod get storageclass local-path
kubectl --context labprod -n authentik get clusters.postgresql.cnpg.io,pvc,pod
kubectl --context labprod -n authentik get objectstores.barmancloud.cnpg.io,scheduledbackups.postgresql.cnpg.io
kubectl --context labprod get namespace local-path-storage -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}{"\n"}'
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd/.well-known/openid-configuration >/dev/null
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd-test/.well-known/openid-configuration >/dev/null
curl --fail --show-error --silent https://auth.lab.bingo/application/o/grafana/.well-known/openid-configuration >/dev/null
curl --fail --show-error --silent https://auth.lab.bingo/application/o/grafana-test/.well-known/openid-configuration >/dev/null
```

Open both Argo CD URLs in a private browser session and select **Log in via
Authentik**. Verify an ordinary user is read-only and an `argocd-admins` member
has administrator permissions. Open both Grafana URLs and verify automatic
Authentik redirection, Viewer access by default and administrator access for a
`grafana-admins` member. Do not use `curl -k`.
