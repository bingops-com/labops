output "cloudflare_tunnel_credentials" {
  value = {
    for name, tunnel in cloudflare_zero_trust_tunnel_cloudflared.tunnels : name => {
      AccountTag   = var.cloudflare_account_id
      TunnelName   = tunnel.name
      TunnelID     = tunnel.id
      TunnelSecret = local.tunnels_with_secrets[name].secret
    }
  }
  sensitive = true
}

output "tunnel_ids" {
  value = {
    for name, tunnel in cloudflare_zero_trust_tunnel_cloudflared.tunnels :
    tunnel.name => tunnel.id
  }
  description = "IDs des tunnels Cloudflare"
}

# Génération d'un fichier JSON par tunnel
resource "local_file" "tunnel_credentials" {
  for_each = cloudflare_zero_trust_tunnel_cloudflared.tunnels

  filename = "${path.module}/credentials/${each.value.name}.json"
  content = jsonencode({
    AccountTag   = var.cloudflare_account_id
    TunnelName   = each.value.name
    TunnelID     = each.value.id
    TunnelSecret = local.tunnels_with_secrets[each.key].secret
  })
  file_permission = "0600"

  depends_on = [null_resource.create_credentials_directory]

}

resource "null_resource" "create_credentials_directory" {
  provisioner "local-exec" {
    command = "mkdir -p ${path.module}/credentials"
    interpreter = ["bash", "-c"]
  }
}
