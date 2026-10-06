# Network and Tailscale DNS

This Terraform stack owns the tailnet DNS configuration, including exact-name
split routes for `argocd.lab.bingo`, `grafana.lab.bingo` and
`home.lab.bingo` through the `labprod` DNS VIP `192.168.10.160`. The former
`test.lab.bingo` route is intentionally removed.

The Tailscale OAuth client is an external sensitive input with the minimum DNS
write and network scopes required by this stack. Store it only in an ignored
variables file and rotate it in the admin console if lost.

Review a Terraform plan before apply because it contacts and changes the live
tailnet. Verify all three production names resolve to `192.168.10.151` while on
LAN/Tailscale and are not publicly routed.
