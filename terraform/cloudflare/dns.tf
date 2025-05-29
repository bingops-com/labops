resource "cloudflare_record" "bingops" {
  zone_id = data.cloudflare_zone.bingops.id
  name    = "@"
  content = cloudflare_zero_trust_tunnel_cloudflared.bingops_tunnel.cname
  type    = "CNAME"
  proxied = true
}

resource "cloudflare_record" "www_bingops" {
  zone_id = data.cloudflare_zone.bingops.id
  name    = "www"
  content = cloudflare_zero_trust_tunnel_cloudflared.bingops_tunnel.cname
  type    = "CNAME"
  proxied = true
}
