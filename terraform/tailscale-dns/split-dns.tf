resource "tailscale_dns_split_nameservers" "labtest" {
  domain      = "test.lab.bingo"
  nameservers = ["192.168.10.170"]
}

resource "tailscale_dns_split_nameservers" "argocd_labprod" {
  domain      = "argocd.lab.bingo"
  nameservers = ["192.168.10.160"]
}
