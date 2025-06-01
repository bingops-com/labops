variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "cloudflare_api_token" {
  description = "Cloudflare API Token"
  type        = string
  sensitive   = true
}

variable "cloudflare_bingops_zone_id" {
  description = "Zone ID for bingops.com"
  type        = string
  sensitive   = true
}

variable "cloudflare_lab_zone_id" {
  description = "Zone ID for lab.bingo"
  type        = string
  sensitive   = true
}

variable "tunnels" {
  description = "Tunnels configuration and their routes for Cloudflare"
  type = list(object({
    name      = string
    secret    = optional(string)
    hostnames = list(string)
    zone_name = string
  }))
  default = []
}
