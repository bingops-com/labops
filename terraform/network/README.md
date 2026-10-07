# Network and Tailscale DNS

This Terraform stack owns the tailnet DNS configuration, including exact-name
split routes for `argocd.lab.bingo` and `grafana.lab.bingo`, plus the
`lab.bingo` zone (LabOps Portal apex), through the `labprod` DNS VIP
`192.168.10.160`. Because Tailscale split DNS matches subdomains, the private
CoreDNS `lab.bingo` zone answers only the apex and forwards every other name,
such as the public `auth.lab.bingo`, to `1.1.1.1`/`9.9.9.9`. The former
`test.lab.bingo` and `welcome.lab.bingo` (Glance) routes are removed.

The Tailscale OAuth client is an external sensitive input with the minimum DNS
write and network scopes required by this stack. Store it only in an ignored
variables file and rotate it in the admin console if lost.

Review a Terraform plan before apply because it contacts and changes the live
tailnet. Verify `argocd`, `grafana` and the `lab.bingo` apex resolve to `192.168.10.151` while on
LAN/Tailscale and are not publicly routed.
