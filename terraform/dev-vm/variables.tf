variable "proxmox_api_url" {
  type = string
}
variable "proxmox_api_token" {
  type      = string
  sensitive = true
}
variable "proxmox_insecure" {
  type    = bool
  default = true
}
variable "proxmox_ssh_private_key_path" {
  type    = string
  default = "~/.ssh/homeops-proxmox"
}
variable "proxmox_ssh_host" {
  type    = string
  default = "192.168.1.100"
}
variable "node_name" {
  type    = string
  default = "homelab"
}
variable "vm_id" {
  type    = number
  default = 160
  validation {
    condition     = var.vm_id == 160
    error_message = "This stack is reserved for development VM 160."
  }
}
variable "address" {
  type    = string
  default = "192.168.10.170/24"
}
