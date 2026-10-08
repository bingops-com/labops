# Authentik

Authentik runs only on `labprod`, backed by
`authentik-labprod-postgresql`. Cloudflare Tunnel publishes
`https://auth.lab.bingo`.

The tracked blueprint owns four OIDC applications: confidential Argo CD at
`https://argocd.lab.bingo/auth/callback`, public-PKCE Grafana at
`https://grafana.lab.bingo/login/generic_oauth`, the public-PKCE LabOps Portal
at `https://lab.bingo/auth/callback`, and public-PKCE RomM at
`https://romm.lab.bingo/api/oauth/openid`. RomM receives Authentik group names
through a dedicated `groups` scope; `romm-admins` grants its administrator role.
Its dedicated `email` scope emits the verified-email claim required by RomM on
Authentik 2025.10 and later. Only the confidential Argo CD client secret and the
Authentik bootstrap password are stored in the Bitwarden `labprod` project and
mapped by tracked BitwardenSecret resources.

After reconciliation, verify the Authentik discovery endpoint and each login
through trusted HTTPS without printing tokens or Secret data.
