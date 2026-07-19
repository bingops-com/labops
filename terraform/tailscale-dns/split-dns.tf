resource "tailscale_dns_split_nameservers" "labtest" {
  domain      = "test.bingops.com"
  nameservers = ["192.168.1.152"]
}

resource "tailscale_dns_split_nameservers" "argocd_labprod" {
  domain      = "argocd.bingops.com"
  nameservers = ["192.168.1.151"]
}
