# Authentik and Argo CD OIDC

Authentik runs only on `labprod` at `https://auth.lab.bingo`. Cloudflare DNS
and the production tunnel publish this hostname; TLS terminates at the Traefik
Ingress with a Let's Encrypt DNS-01 certificate. PostgreSQL uses an 8 Gi
persistent volume in namespace `authentik`.

The `local-path-storage-labprod` Argo CD Application installs Rancher's
local-path provisioner, pinned to `v0.0.36`, before Authentik. Its default
`local-path` StorageClass stores volumes below
`/var/lib/kubelet/local-path-provisioner` on the Talos node selected for the
workload. The path is below Talos' existing writable kubelet data mount; do not
move it below an unmounted `/var/mnt` path, which remains read-only.
The provisioner namespace explicitly permits privileged workloads because its
short-lived volume helper mounts that host path. Without this Pod Security
exception, PostgreSQL remains Pending and Cloudflare returns 502 for Authentik.
This is node-local storage: it survives pod restarts, but it is neither shared
nor replicated and does not replace the PostgreSQL backup required for node or
cluster replacement.

The file-based Authentik blueprint declaratively owns two confidential OIDC
providers:

| Client | Issuer | Redirect URI |
| --- | --- | --- |
| `argocd` | `https://auth.lab.bingo/application/o/argocd/` | `https://argocd.lab.bingo/auth/callback` |
| `argocd-test` | `https://auth.lab.bingo/application/o/argocd-test/` | `https://argocd.test.lab.bingo/auth/callback` |

The blueprint also owns the `argocd-admins` group. Authenticated users default
to Argo CD read-only access; members of that group inherit `role:admin`.
Production Argo CD has no Traefik IP allowlist, while test retains its
LAN/Tailscale allowlist. `argocd.lab.bingo` remains private split DNS and is not
published through the Cloudflare tunnel.

## Secrets and recovery

BitwardenSecret mappings deliver the Authentik application key, PostgreSQL
passwords, bootstrap administrator credentials and the two distinct OIDC client
secrets from the `labprod` Bitwarden project. Plaintext values must never be
recovered into Git or logs. Back up the Authentik PostgreSQL volume as identity data;
additional users and credentials remain generated state.

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

1. Review and apply the Cloudflare Terraform change for `auth.lab.bingo`.
2. Reconcile the labprod app-of-apps. Wait for `local-path-storage-labprod` to
   become Healthy and for the PostgreSQL PVC to become Bound before Authentik,
   its Ingress and the tunnel route are considered ready.
3. Wait for the bootstrap blueprint to create both providers and group
   membership, then reconcile the Argo CD overlays on labprod and labtest.
4. Validate OIDC discovery and both browser callbacks. The built-in Argo CD
   administrator is disabled declaratively on both clusters; recovery uses a
   reviewed Git revert and Kubernetes core access.

Non-sensitive verification commands:

```sh
kubectl --context labprod get storageclass local-path
kubectl --context labprod -n authentik get pvc,pod
kubectl --context labprod get namespace local-path-storage -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}{"\n"}'
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd/.well-known/openid-configuration >/dev/null
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd-test/.well-known/openid-configuration >/dev/null
```

Open both Argo CD URLs in a private browser session and select **Log in via
Authentik**. Verify an ordinary user is read-only and an `argocd-admins` member
has administrator permissions. Do not use `curl -k`.
