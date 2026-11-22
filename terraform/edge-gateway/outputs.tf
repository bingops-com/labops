output "public_ipv4" {
  description = "Stable public IPv4 address to publish in DNS or game connection details."
  value       = hcloud_primary_ip.edge_gateway.ip_address
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
    for name, forward in var.forwards : name => {
      protocol    = lower(forward.protocol)
      public      = "${hcloud_primary_ip.edge_gateway.ip_address}:${forward.listen_port}"
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
