output "public_ipv4" {
  description = "Current public IPv4 address (null when fully suspended) to publish in DNS or game connection details."
  value       = try(hcloud_primary_ip.edge_gateway[0].ip_address, null)
}

output "server_id" {
  description = "Hetzner Cloud server identifier."
  value       = try(hcloud_server.edge_gateway[0].id, null)
}

output "server_name" {
  description = "Hetzner and Tailscale hostname."
  value       = try(hcloud_server.edge_gateway[0].name, null)
}

output "public_forwards" {
  description = "Non-sensitive summary of the public layer-4 forwarding table."
  value = {
    for name, forward in(local.resources_enabled ? var.forwards : {}) : name => {
      protocol    = lower(forward.protocol)
      public      = "${hcloud_primary_ip.edge_gateway[0].ip_address}:${forward.listen_port}"
      destination = "${forward.target_ip}:${forward.target_port}"
    }
  }
}

output "public_hostnames" {
  description = "DNS-only service names resolving to the public edge gateway."
  value = sort([
    for record in cloudflare_record.public_services : record.hostname
  ])
}
