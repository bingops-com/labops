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
  description = "Tailnet organization name."
  default     = "bingops.com"
}
