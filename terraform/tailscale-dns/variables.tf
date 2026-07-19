variable "tailscale_oauth_client_id" {
  type        = string
  description = "Tailscale OAuth client ID with DNS write access."
  sensitive   = true
}

variable "tailscale_oauth_client_secret" {
  type        = string
  description = "Tailscale OAuth client secret with DNS write access."
  sensitive   = true
}

variable "tailscale_tailnet" {
  type        = string
  description = "Optional Tailscale tailnet ID. Leave null to use the tailnet that owns the OAuth client."
  default     = null
  nullable    = true
}
