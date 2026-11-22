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

The private `coder.lab.bingo` name also uses the existing `lab.bingo` parent
route. Its answer is owned by `apps/platform/private-dns/labprod`; adding
Coder does not require a tailnet DNS mutation.

The separate native development VM uses `code.lab.bingo`, whose private A
record points directly to its Tailscale address `100.65.212.7`. A more specific
`code.lab.bingo` split route in this stack sends queries directly to the native
VM's tailnet-only DNSmasq. CoreDNS retains the same answer as a parallel mirror;
there is no public Cloudflare record or application tunnel. Connect with
`ssh dev@code.lab.bingo` on Tailscale (standard port 22). The VM firewall
accepts SSH only through `tailscale0`. Coder and the current `dev.lab.bingo`
portal keep their existing names and addresses during parallel preparation.
If the VM is re-enrolled with a different Tailscale IP, review/update this A
record and the split route from `tailscale ip -4`; do not substitute its LAN
address. This native zone does not require the Kubernetes DNS service. The
verified Tailscale IP remains the SSH recovery endpoint during DNS maintenance.

Review a Terraform plan before apply because it contacts and changes the live
tailnet. During the native Code route deployment, the retained worktree also
contained unrelated router changes: a targeted plan/apply of
`tailscale_dns_configuration.tailnet` isolated the additive DNS update rather
than running the router provisioner. Review the complete plan before later
network maintenance; targeting does not reconcile unrelated pending changes.
Verify `argocd`, `grafana` and the `lab.bingo` apex resolve to `192.168.10.151` while on
LAN/Tailscale and are not publicly routed.
