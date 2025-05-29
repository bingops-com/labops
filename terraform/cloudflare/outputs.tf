output "cloudflare_tunnel_credentials" {
  value = {
    AccountTag   = var.cloudflare_account_id
    TunnelName   = cloudflare_zero_trust_tunnel_cloudflared.bingops_tunnel.name
    TunnelID     = cloudflare_zero_trust_tunnel_cloudflared.bingops_tunnel.id
    TunnelSecret = random_password.tunnel_secret.result
  }
  sensitive = true
}

output "tunnel_id" {
  value       = cloudflare_zero_trust_tunnel_cloudflared.bingops_tunnel.id
  description = "Cloudflare Zero Trust Tunnel ID"
}
