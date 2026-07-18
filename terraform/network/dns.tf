resource "tailscale_dns_configuration" "tailnet" {
  nameservers {
    address = "1.1.1.1"
  }

  nameservers {
    address = "9.9.9.9"
  }

  magic_dns          = true
  override_local_dns = true
}
