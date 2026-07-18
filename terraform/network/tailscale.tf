data "tailscale_device" "proxmox_router" {
  hostname = var.tailscale_router_hostname
  wait_for = "60s"
}

resource "tailscale_device_subnet_routes" "proxmox_router" {
  depends_on = [terraform_data.proxmox_vlan_router]

  device_id = data.tailscale_device.proxmox_router.node_id
  routes    = var.tailscale_subnet_routes
}
