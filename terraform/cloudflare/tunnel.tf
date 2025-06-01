resource "random_password" "tunnel_secret" {
  for_each = { for idx, tunnel in var.tunnels : idx => tunnel if tunnel.secret == null }

  length           = 32
  special          = false
  override_special = ""
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "tunnels" {
  for_each = local.tunnels_with_secrets

  account_id = var.cloudflare_account_id
  name       = each.value.name
  secret     = each.value.secret
}
