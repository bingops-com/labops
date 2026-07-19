locals {
  zone_ids = {
    "bingops" = var.cloudflare_bingops_zone_id
    "lab"     = var.cloudflare_lab_zone_id
  }

  zone_domains = {
    "bingops" = "bingops.com"
    "lab"     = "lab.bingo"
  }

  lab_tunnel_hostnames = toset([
    "auth.lab.bingo",
    "portfolio.lab.bingo",
  ])

  tunnels_with_secrets = {
    for idx, tunnel in var.tunnels : tunnel.name => {
      name      = tunnel.name
      secret    = tunnel.secret != null ? tunnel.secret : random_password.tunnel_secret[idx].result
      hostnames = tunnel.hostnames
      zone_id   = local.zone_ids[tunnel.zone_name]
      zone_name = tunnel.zone_name
    }
  }
}
