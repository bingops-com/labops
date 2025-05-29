resource "random_password" "tunnel_secret" {
  length  = 32
  special = false
  override_special = ""
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "bingops_tunnel" {
  account_id = var.cloudflare_account_id
  name       = "bingops-tunnel"
  secret     = random_password.tunnel_secret.result
}
