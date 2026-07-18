output "tailscale_router_node_id" {
  description = "Stable Tailscale node ID of the Proxmox subnet router."
  value       = data.tailscale_device.proxmox_router.node_id
}

output "enabled_subnet_routes" {
  description = "Subnet routes enabled through the Proxmox router."
  value       = tailscale_device_subnet_routes.proxmox_router.routes
}
