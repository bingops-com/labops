variable "proxmox_api_url" {
  type        = string
  description = "Existing Proxmox endpoint; supplied from the ignored operator credential file."
}

variable "proxmox_api_token" {
  type        = string
  sensitive   = true
  description = "Existing operator API token; never store in tracked configuration."
}

variable "proxmox_insecure" {
  type    = bool
  default = true
}

variable "proxmox_ssh_host" {
  type    = string
  default = "192.168.1.100"
}

variable "proxmox_ssh_username" {
  type    = string
  default = "bingo"
}

variable "proxmox_ssh_private_key_path" {
  type    = string
  default = "~/.ssh/homeops-proxmox"
}

variable "node_name" {
  type    = string
  default = "homelab"
}

variable "disk_datastore" {
  type    = string
  default = "local-lvm"
}

variable "image_datastore" {
  type    = string
  default = "local"
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "management_vlan" {
  type    = number
  default = 10
}

variable "lab_vlan" {
  type    = number
  default = 60
}

variable "management_gateway" {
  type    = string
  default = "192.168.10.1"
}

variable "dns_servers" {
  type    = list(string)
  default = ["1.1.1.1", "9.9.9.9"]
}

variable "ssh_public_key_path" {
  type        = string
  description = "Path to the dedicated lab SSH public key. The private key stays outside Terraform."
  default     = "keys/bingops.pub"
}

variable "disk_gib" {
  type    = number
  default = 32
}

variable "nodes" {
  type = map(object({
    vm_id              = number
    memory_mib         = number
    vcpus              = number
    management_address = string
    lab_address        = string
    management_mac     = string
    lab_mac            = string
  }))
  default = {
    k8s-master = {
      vm_id              = 620
      memory_mib         = 1800
      vcpus              = 2
      management_address = "192.168.10.20/24"
      lab_address        = "192.168.60.20/24"
      management_mac     = "02:CA:00:00:06:20"
      lab_mac            = "02:CA:00:00:60:20"
    }
    k8s-worker-1 = {
      vm_id              = 621
      memory_mib         = 3000
      vcpus              = 2
      management_address = "192.168.10.21/24"
      lab_address        = "192.168.60.21/24"
      management_mac     = "02:CA:00:00:06:21"
      lab_mac            = "02:CA:00:00:60:21"
    }
  }

  validation {
    condition     = toset(keys(var.nodes)) == toset(["k8s-master", "k8s-worker-1"])
    error_message = "This training topology contains exactly k8s-master and k8s-worker-1."
  }

  validation {
    condition     = length(distinct([for n in values(var.nodes) : n.vm_id])) == 2 && alltrue([for n in values(var.nodes) : !contains([130, 150, 151, 1234], n.vm_id)])
    error_message = "VM IDs must be unique and must not target the existing management, production, template or game VMs."
  }
}
