# Authentik

Authentik runs only on `labprod`, backed by
`authentik-labprod-postgresql`. Cloudflare Tunnel publishes
`https://auth.lab.bingo`.

The tracked blueprint owns two OIDC applications: confidential Argo CD at
`https://argocd.lab.bingo/auth/callback` and public-PKCE Grafana at
`https://grafana.lab.bingo/login/generic_oauth`. Their production credentials
and bootstrap password are stored in the Bitwarden `labprod` project and
mapped by tracked BitwardenSecret resources.

After reconciliation, verify the Authentik discovery endpoint and both logins
through trusted HTTPS without printing tokens or Secret data.
