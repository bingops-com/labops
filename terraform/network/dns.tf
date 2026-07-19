resource "tailscale_dns_configuration" "tailnet" {
  nameservers {
    address = "1.1.1.1"
  }

  nameservers {
    address = "9.9.9.9"
  }

  split_dns {
    domain = "test.lab.bingo"

    nameservers {
      address = "192.168.10.170"
    }
  }

  split_dns {
    domain = "argocd.lab.bingo"

    nameservers {
      address = "192.168.10.160"
    }
  }

  magic_dns          = true
  override_local_dns = true
}
