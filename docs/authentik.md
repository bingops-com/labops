# Authentik and Argo CD OIDC

Authentik runs only on `labprod` at `https://auth.lab.bingo`. Cloudflare DNS
and the production tunnel publish this hostname; TLS terminates at the Traefik
Ingress with a Let's Encrypt DNS-01 certificate. PostgreSQL uses an 8 Gi
persistent volume in namespace `authentik`.

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

Three strict-scope SealedSecrets contain the Authentik application key,
PostgreSQL passwords, bootstrap administrator credentials and the two distinct
OIDC client secrets. Plaintext values must never be recovered into Git or logs.
They are recoverable only with the backed-up private sealing keys for their
owning cluster. Back up the Authentik PostgreSQL volume as identity data;
additional users and credentials remain generated state.

Local bootstrap inputs are staged only under the ignored
`apps/platform/authentik/credentials/` directory. Never commit this directory;
store the administrator password in the team password manager and use the local
file only while generating its strict-scope SealedSecret. Delete the staging
file immediately after `kubeseal --validate` succeeds.

On a fresh database, Authentik consumes the sealed `AUTHENTIK_BOOTSTRAP_EMAIL`
and `AUTHENTIK_BOOTSTRAP_PASSWORD` values automatically. Its blueprint creates
`argocd-admins` and adds `akadmin`, so `/if/flow/initial-setup/` is not required.
The bootstrap variables do not reset an existing database. Rotate the exposed
initial password after the first successful login and update the password
manager; never record the replacement in this repository.

## Delivery order

1. Review and apply the Cloudflare Terraform change for `auth.lab.bingo`.
2. Reconcile the labprod app-of-apps so the Authentik configuration, chart,
   PostgreSQL, Ingress and tunnel route are created.
3. Wait for the bootstrap blueprint to create both providers and group
   membership, then reconcile the Argo CD overlays on labprod and labtest.
4. Validate OIDC discovery and both browser callbacks. The built-in Argo CD
   administrator is disabled declaratively on both clusters; recovery uses a
   reviewed Git revert and Kubernetes core access.

Non-sensitive verification commands:

```sh
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd/.well-known/openid-configuration >/dev/null
curl --fail --show-error --silent https://auth.lab.bingo/application/o/argocd-test/.well-known/openid-configuration >/dev/null
```

Open both Argo CD URLs in a private browser session and select **Log in via
Authentik**. Verify an ordinary user is read-only and an `argocd-admins` member
has administrator permissions. Do not use `curl -k`.
