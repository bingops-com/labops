variable "cloudflare_account_id" {
  description = "L'identifiant du compte Cloudflare"
  type        = string
}

variable "cloudflare_api_token" {
  description = "Token API Cloudflare avec permissions pour gérer les tunnels"
  type        = string
  sensitive   = true
}
