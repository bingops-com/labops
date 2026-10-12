# Isolated fixture for the shared games-mail.tf symlink. No state or operator
# inputs are loaded from the owning Cloudflare stack; every provider is mocked.
terraform {
  required_version = ">= 1.10.0"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52.0"
    }
  }
}

variable "cloudflare_lab_zone_id" {
  type    = string
  default = "00000000000000000000000000000000"
}

variable "games_mail" {
  type = object({
    egress_ipv4     = string
    dkim_selector   = string
    dkim_public_key = string
  })
  default = null
}

locals {
  games_mail = var.games_mail
}
