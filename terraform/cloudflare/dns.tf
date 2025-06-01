resource "cloudflare_record" "tunnel_routes" {
  for_each = {
    for pair in flatten([
      for tunnel_name, tunnel in local.tunnels_with_secrets : [
        for hostname in tunnel.hostnames : {
          tunnel_name = tunnel_name
          hostname    = hostname
          zone_id     = tunnel.zone_id
          domain      = local.zone_domains[tunnel.zone_name]
        }
      ]
    ]) : "${pair.tunnel_name}-${trimsuffix(pair.hostname, ".${local.zone_domains[local.tunnels_with_secrets[pair.tunnel_name].zone_name]}") == "" ? "@" : trimsuffix(pair.hostname, ".${local.zone_domains[local.tunnels_with_secrets[pair.tunnel_name].zone_name]}")}" => pair
  }

  zone_id  = each.value.zone_id
  name     = trimsuffix(each.value.hostname, ".${local.zone_domains[local.tunnels_with_secrets[each.value.tunnel_name].zone_name]}") == "" ? "@" : trimsuffix(each.value.hostname, ".${local.zone_domains[local.tunnels_with_secrets[each.value.tunnel_name].zone_name]}")
  content  = "${cloudflare_zero_trust_tunnel_cloudflared.tunnels[each.value.tunnel_name].id}.cfargotunnel.com"
  type     = "CNAME"
  proxied  = true
}
