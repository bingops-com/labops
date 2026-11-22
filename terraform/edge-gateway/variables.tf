variable "enabled" {
  type        = bool
  description = "Whether the gateway VM exists. False retains its IPv4, DNS, firewall and SSH key, but removes the VM and consumed Tailscale bootstrap key."
  default     = true
}

variable "name" {
  type        = string
  description = "Hetzner and Tailscale hostname for the stateless public edge gateway."
  default     = "labops-edge-01"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", var.name))
    error_message = "name must be a lowercase DNS label between 2 and 63 characters."
  }
}

variable "location" {
  type        = string
  description = "Hetzner Cloud location. Nuremberg provides a central European entry point."
  default     = "nbg1"
}

variable "server_type" {
  type        = string
  description = "Hetzner Cloud server type. CX23 is sufficient for a layer-4 gateway."
  default     = "cx23"
}

variable "image" {
  type        = string
  description = "Hetzner Cloud operating-system image."
  default     = "debian-13"
}

variable "public_dns_zone" {
  type        = string
  description = "Cloudflare DNS zone containing public names for services exposed by the gateway."
  default     = "bingops.com"

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", var.public_dns_zone))
    error_message = "public_dns_zone must be a lowercase DNS zone such as bingops.com."
  }
}

variable "public_dns_records" {
  type        = set(string)
  description = "DNS labels in public_dns_zone that resolve directly to the retained gateway IPv4."
  default     = ["pz"]

  validation {
    condition = alltrue([
      for name in var.public_dns_records : can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", name))
    ])
    error_message = "public_dns_records must contain lowercase DNS labels."
  }
}

variable "ssh_public_key_path" {
  type        = string
  description = "Operator SSH public-key path for public recovery access or the Hetzner console. Public SSH is disabled by default."
}

variable "public_ssh_source_cidrs" {
  type        = set(string)
  description = "Optional IPv4 CIDRs allowed to connect to public TCP/22. Keep empty to permit SSH only through Tailscale."
  default     = []

  validation {
    condition     = alltrue([for cidr in var.public_ssh_source_cidrs : can(cidrnetmask(cidr)) && !strcontains(cidr, ":")])
    error_message = "public_ssh_source_cidrs must contain valid IPv4 CIDRs."
  }
}

variable "tailscale_tag" {
  type        = string
  description = "Tag assigned to the edge gateway by its single-use Tailscale auth key."
  default     = "tag:edge-gateway"

  validation {
    condition     = can(regex("^tag:[a-zA-Z0-9-]+$", var.tailscale_tag))
    error_message = "tailscale_tag must use the tag:name form."
  }
}

variable "tailscale_version" {
  type        = string
  description = "Pinned Tailscale Debian package version installed by cloud-init."
  default     = "1.98.9"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.tailscale_version))
    error_message = "tailscale_version must be a semantic version such as 1.98.9."
  }
}

variable "forwards" {
  description = "Public layer-4 forwards. Source CIDRs are enforced by both the Hetzner firewall and nftables."
  type = map(object({
    protocol     = string
    listen_port  = number
    target_ip    = string
    target_port  = number
    source_cidrs = optional(set(string), ["0.0.0.0/0"])
  }))

  default = {}

  validation {
    condition = alltrue([
      for name in keys(var.forwards) : can(regex("^[a-z0-9][a-z0-9-]{0,62}$", name))
    ])
    error_message = "Forward names must be lowercase labels containing only letters, digits and hyphens."
  }

  validation {
    condition = alltrue([
      for forward in values(var.forwards) : contains(["tcp", "udp"], lower(forward.protocol))
    ])
    error_message = "Each forward protocol must be tcp or udp."
  }

  validation {
    condition = alltrue([
      for forward in values(var.forwards) :
      forward.listen_port >= 1 && forward.listen_port <= 65535 &&
      forward.target_port >= 1 && forward.target_port <= 65535
    ])
    error_message = "Listen and target ports must be between 1 and 65535."
  }

  validation {
    condition = alltrue(flatten([
      for forward in values(var.forwards) : [
        for cidr in forward.source_cidrs : can(cidrnetmask(cidr)) && !strcontains(cidr, ":")
      ]
    ]))
    error_message = "Forward source_cidrs must contain valid IPv4 CIDRs."
  }

  validation {
    condition = alltrue([
      for forward in values(var.forwards) : can(cidrhost("${forward.target_ip}/32", 0)) && !strcontains(forward.target_ip, ":")
    ])
    error_message = "Each forward target_ip must be an IPv4 address."
  }

  validation {
    condition = length(distinct([
      for forward in values(var.forwards) : "${lower(forward.protocol)}:${forward.listen_port}"
    ])) == length(var.forwards)
    error_message = "Each public protocol/listen_port pair must be unique."
  }
}
