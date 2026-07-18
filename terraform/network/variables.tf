variable "tailscale_oauth_client_id" {
  type        = string
  description = "Tailscale OAuth client ID loaded from credentials.auto.tfvars."
}

variable "tailscale_oauth_client_secret" {
  type        = string
  description = "Tailscale OAuth client secret loaded from credentials.auto.tfvars."
  sensitive   = true
}

variable "tailscale_tailnet" {
  type        = string
  description = "Tailscale tailnet ID. A dash selects the credential's default tailnet."
  default     = "-"
}

variable "tailscale_router_hostname" {
  type        = string
  description = "Short Tailscale hostname of the Proxmox subnet router."
  default     = "homelab"
}

variable "tailscale_subnet_routes" {
  type        = set(string)
  description = "Subnet routes enabled for the Proxmox Tailscale router."
  default = [
    "192.168.1.0/24",
    "192.168.10.0/24",
  ]
}
