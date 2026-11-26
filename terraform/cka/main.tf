terraform {
  required_version = ">= 1.10.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.111.1"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_api_url
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure

  ssh {
    agent       = false
    username    = var.proxmox_ssh_username
    private_key = file(pathexpand(var.proxmox_ssh_private_key_path))
    node {
      name    = var.node_name
      address = var.proxmox_ssh_host
    }
  }
}
