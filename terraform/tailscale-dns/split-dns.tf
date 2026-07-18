resource "tailscale_dns_split_nameservers" "labtest" {
  domain      = "test.bingops.com"
  nameservers = ["192.168.10.152"]
}
