variable "proxmox_api_url" {
  type        = string
  description = "Proxmox API URL loaded from credentials.auto.tfvars, for example https://192.168.1.10:8006/."

  validation {
    condition     = can(regex("^https://[^/]+(?::[0-9]+)?/?$", var.proxmox_api_url))
    error_message = "proxmox_api_url must be an HTTPS Proxmox API endpoint."
  }
}

variable "proxmox_api_token" {
  type        = string
  description = "Proxmox API token loaded from credentials.auto.tfvars in user@realm!token=secret form."
  sensitive   = true

  validation {
    condition     = can(regex("^[^=]+![^=]+=[^=]+$", var.proxmox_api_token))
    error_message = "proxmox_api_token must use the user@realm!token=secret format."
  }
}

variable "proxmox_insecure" {
  type        = bool
  description = "Allow a self-signed Proxmox API certificate."
  default     = true
}

variable "node_name" {
  type        = string
  description = "Proxmox node on which the Talos VMs run."
}

variable "node_pool" {
  type        = string
  description = "Proxmox resource pool for the Talos VMs."
  default     = "Kubernetes"
}

variable "kubernetes_vlan_id" {
  type        = number
  description = "802.1Q VLAN tag applied to every Kubernetes VM network device."
  default     = 10

  validation {
    condition     = var.kubernetes_vlan_id >= 1 && var.kubernetes_vlan_id <= 4094
    error_message = "kubernetes_vlan_id must be between 1 and 4094."
  }
}

variable "datastore" {
  type        = string
  description = "Proxmox datastore for VM disks."
}

variable "iso_datastore" {
  type        = string
  description = "Proxmox datastore used for the Talos nocloud ISO."
  default     = "local"
}

variable "talos_nocloud_template_vm_id" {
  type        = number
  description = "Existing Proxmox Talos nocloud template cloned for the management cluster."
  default     = 1234
}

variable "talos_version" {
  type        = string
  description = "Talos release used by both the boot ISO and installer image."
  default     = "v1.13.3"
}

variable "talos_schematic_id" {
  type        = string
  description = "Talos Image Factory schematic ID. The default is the standard metal image."
  default     = "376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba"
}

variable "clusters" {
  description = "Independent Talos clusters and their stable Kubernetes API endpoints."
  type = map(object({
    endpoint          = string
    control_plane_vip = optional(string)
  }))

  validation {
    condition     = length(var.clusters) > 0
    error_message = "At least one cluster is required."
  }
}

variable "nameservers" {
  type        = list(string)
  description = "DNS servers configured on Talos nodes."
  default     = ["1.1.1.1", "9.9.9.9"]
}

variable "nodes" {
  description = "Talos VM definitions. Reserve each MAC/address pair in DHCP so the ISO is reachable before static networking is applied."
  type = map(object({
    address        = string
    gateway        = string
    vm_id          = number
    mac_address    = string
    cores          = number
    memory         = number
    storage        = number
    network_bridge = string
    cluster        = string
    role           = string
  }))

  validation {
    condition     = alltrue([for node in values(var.nodes) : contains(["controlplane", "worker"], node.role)])
    error_message = "Each node role must be either controlplane or worker."
  }

  validation {
    condition     = length([for node in values(var.nodes) : node if node.role == "controlplane"]) > 0
    error_message = "At least one controlplane node is required."
  }

  validation {
    condition     = alltrue([for node in values(var.nodes) : contains(keys(var.clusters), node.cluster)])
    error_message = "Every node must reference a key declared in clusters."
  }
}
