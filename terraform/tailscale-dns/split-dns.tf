resource "tailscale_dns_split_nameservers" "labtest" {
  domain      = "test.lab.bingo"
  nameservers = ["192.168.1.152"]
}

resource "tailscale_dns_split_nameservers" "argocd_labprod" {
  domain      = "argocd.lab.bingo"
  nameservers = ["192.168.1.151"]
}
