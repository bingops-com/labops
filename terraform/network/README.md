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

The native development VM uses `dev.lab.bingo` for SSH, HTTPS and
`PORT.dev.lab.bingo` application previews. Its dedicated split route sends
queries to native DNSmasq at `100.65.212.7`; CoreDNS mirrors that same private
answer. There is no public record or application tunnel. Connect with
`ssh dev@dev.lab.bingo` on Tailscale, port 22. The firewall accepts SSH only
through `tailscale0`; the verified Tailscale IP is the DNS recovery endpoint.
The parallel `code.lab.bingo` route and former Coder records are retired during
cutover. If re-enrollment changes the Tailscale IP, update this split route and
the mirrored answer together; never substitute the underlay address.

Review a Terraform plan before apply because it contacts and changes the live
tailnet. During the native Code route deployment, the retained worktree also
contained unrelated router changes: a targeted plan/apply of
`tailscale_dns_configuration.tailnet` isolated the additive DNS update rather
than running the router provisioner. Review the complete plan before later
network maintenance; targeting does not reconcile unrelated pending changes.
Verify `argocd`, `grafana` and the `lab.bingo` apex resolve to `192.168.10.151` while on
LAN/Tailscale and are not publicly routed.
