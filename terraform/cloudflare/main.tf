terraform {
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7.2"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.5.3"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.4"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
