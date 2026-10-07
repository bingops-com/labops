# Retired Tailscale split-DNS stack

This stack is retired. The authoritative tailnet DNS declaration is
`terraform/network/dns.tf`; do not plan or apply this directory.

After applying the reviewed network-stack migration, detach any obsolete
resources from this retired state without deleting the production remote route:

```sh
terraform -chdir=terraform/tailscale-dns state rm tailscale_dns_split_nameservers.labtest tailscale_dns_split_nameservers.argocd_labprod
```

State mutation requires explicit authorization. Keep a protected state backup
until `argocd.lab.bingo` and `grafana.lab.bingo` resolve correctly.
