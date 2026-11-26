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
  insecure  = false
  ssh {
    agent       = false
    username    = "bingo"
    private_key = file(pathexpand(var.proxmox_ssh_private_key_path))
    node {
      name    = "homelab"
      address = "192.168.1.100"
    }
  }
}

variable "proxmox_api_url" { type = string }
variable "proxmox_api_token" {
  type      = string
  sensitive = true
}
variable "proxmox_ssh_private_key_path" {
  type    = string
  default = "~/.ssh/homeops-proxmox"
}
variable "lab" {
  type = object({
    id                 = string
    start_nodes        = bool
    gateway_public_key = string
    node_public_key    = string
    nodes = map(object({
      vmid = number
      ip   = string
      role = string
    }))
  })
  validation {
    condition = (
      can(regex("^[a-f0-9-]{36}$", var.lab.id)) &&
      length(var.lab.nodes) >= 2 && length(var.lab.nodes) <= 6 &&
      alltrue([for name, n in var.lab.nodes : contains([710, 711, 712, 720, 721, 722], n.vmid) && can(regex("^cka-(cp|worker)-[1-3]$", name)) && can(regex("^172\\.30\\.90\\.(1[0-2]|2[0-2])$", n.ip))]) &&
      length(distinct([for n in values(var.lab.nodes) : n.vmid])) == length(var.lab.nodes)
    )
    error_message = "Only the fixed CKA-UI VM range, private subnet and generated lab identity are permitted."
  }
}

locals {
  guests = merge({
    "cka-gateway" = { vmid = 700, ip = "172.30.90.1", role = "gateway" }
  }, var.lab.nodes)
  control_planes = [for n in values(var.lab.nodes) : n if n.role == "control-plane"]
}

resource "proxmox_virtual_environment_pool" "lab" {
  pool_id = "CKA-UI"
  comment = "Single disposable CKA lab; owned exclusively by terraform/cka-ui."
}
resource "proxmox_storage_directory" "snippets" {
  id               = "cka-ui-snippets"
  path             = "/var/lib/vz/cka-ui-snippets"
  nodes            = ["homelab"]
  content          = ["snippets"]
  create_base_path = true
  create_subdirs   = true
  shared           = false
}
resource "proxmox_download_file" "ubuntu" {
  node_name          = "homelab"
  datastore_id       = "local"
  content_type       = "iso"
  file_name          = "cka-ui-ubuntu-22.04-20261020.img"
  url                = "https://cloud-images.ubuntu.com/releases/jammy/release-20261020/ubuntu-22.04-server-cloudimg-amd64.img"
  checksum           = "2099e63da0b822ef8e05e3d596c1b402eaaae658fc08ab919cb8495bfcdc488b"
  checksum_algorithm = "sha256"
  overwrite          = false
}

resource "proxmox_virtual_environment_file" "network" {
  for_each     = local.guests
  node_name    = "homelab"
  datastore_id = proxmox_storage_directory.snippets.id
  content_type = "snippets"
  upload_mode  = "stream"
  overwrite    = false
  source_raw {
    file_name = "${var.lab.id}-${each.key}-network.yaml"
    data = yamlencode({
      version = 2
      ethernets = merge({
        eth0 = {
          match       = { macaddress = format("02:ca:90:00:%02x:%02x", floor(each.value.vmid / 256), each.value.vmid % 256) }
          "set-name"  = "eth0"
          addresses   = [each.value.role == "gateway" ? "192.168.10.22/24" : "${each.value.ip}/24"]
          routes      = [{ to = "0.0.0.0/0", via = each.value.role == "gateway" ? "192.168.10.1" : "172.30.90.1" }]
          nameservers = { addresses = ["1.1.1.1", "9.9.9.9"] }
        }
        }, each.value.role == "gateway" ? {
        eth1 = {
          match      = { macaddress = "02:ca:90:01:02:bc" }
          "set-name" = "eth1"
          addresses  = ["172.30.90.1/24"]
        }
      } : {})
    })
  }
}

resource "proxmox_virtual_environment_file" "cloud_init" {
  for_each     = local.guests
  node_name    = "homelab"
  datastore_id = proxmox_storage_directory.snippets.id
  content_type = "snippets"
  upload_mode  = "stream"
  overwrite    = false
  source_raw {
    file_name = "${var.lab.id}-${each.key}-cloud-init.yaml"
    data = "#cloud-config\n${yamlencode({
      hostname        = each.key
      ssh_pwauth      = false
      disable_root    = true
      package_update  = true
      package_upgrade = false
      timezone        = "Etc/UTC"
      users = [{
        name                = "ubuntu"
        groups              = ["sudo"]
        shell               = "/bin/bash"
        lock_passwd         = true
        sudo                = ["ALL=(ALL) NOPASSWD:ALL"]
        ssh_authorized_keys = [each.value.role == "gateway" ? var.lab.gateway_public_key : var.lab.node_public_key]
      }]
      packages = concat(["qemu-guest-agent", "ca-certificates", "curl", "gnupg", "netcat-openbsd"], each.value.role == "gateway" ? ["nftables", "haproxy"] : ["conntrack", "socat"])
      write_files = concat([
        { path = "/etc/cka-ui-identity", owner = "root:root", permissions = "0644", content = var.lab.id },
        { path = "/etc/ssh/sshd_config.d/60-cka-ui.conf", owner = "root:root", permissions = "0644", content = "PasswordAuthentication no\nPermitRootLogin no\nX11Forwarding no\nAllowAgentForwarding no\nPermitTunnel no\n${each.value.role == "gateway" ? "AllowTcpForwarding local\nPermitOpen ${join(" ", [for n in values(var.lab.nodes) : "${n.ip}:22"])}" : "AllowTcpForwarding no"}\n" }
        ], each.value.role == "gateway" ? [
        { path = "/etc/nftables.conf", owner = "root:root", permissions = "0600", content = file("${path.module}/templates/gateway.nft") },
        { path = "/etc/haproxy/haproxy.cfg", owner = "root:root", permissions = "0644", content = "global\n  user haproxy\n  group haproxy\n  daemon\ndefaults\n  mode tcp\n  timeout connect 5s\n  timeout client 60s\n  timeout server 60s\nfrontend kubernetes\n  bind 172.30.90.1:6443\n  default_backend controlplanes\nbackend controlplanes\n  balance roundrobin\n${join("\n", [for i, n in local.control_planes : "  server cp${i + 1} ${n.ip}:6443 check"])}\n" },
        { path = "/etc/sysctl.d/90-cka-gateway.conf", owner = "root:root", permissions = "0644", content = "net.ipv4.ip_forward=1\nnet.ipv6.conf.all.disable_ipv6=1\nnet.ipv6.conf.default.disable_ipv6=1\n" }
      ] : [])
      runcmd = concat([
        ["systemctl", "enable", "--now", "qemu-guest-agent"], ["systemctl", "restart", "ssh"]
        ], each.value.role == "gateway" ? [
        ["sysctl", "--system"], ["nft", "-f", "/etc/nftables.conf"], ["systemctl", "enable", "--now", "nftables"], ["systemctl", "restart", "haproxy"]
      ] : [])
    })}"
  }
}

resource "proxmox_virtual_environment_vm" "guest" {
  for_each    = local.guests
  node_name   = "homelab"
  vm_id       = each.value.vmid
  name        = each.key
  pool_id     = proxmox_virtual_environment_pool.lab.pool_id
  description = "CKA-UI ${var.lab.id}; exclusively owned by terraform/cka-ui."
  tags        = ["cka-ui", "terraform", "disposable"]
  on_boot     = false
  started     = each.value.role == "gateway" || var.lab.start_nodes
  boot_order  = ["scsi0"]
  cpu {
    cores = 2
    type  = "host"
  }
  memory {
    dedicated = each.value.role == "gateway" ? 1024 : each.value.role == "control-plane" ? 3072 : 2048
    floating  = 0
  }
  agent {
    enabled = true
    wait_for_ip { disabled = true }
  }
  disk {
    datastore_id = "local-lvm"
    file_id      = proxmox_download_file.ubuntu.id
    interface    = "scsi0"
    file_format  = "raw"
    size         = 24
    discard      = "on"
    ssd          = true
  }
  network_device {
    bridge      = each.value.role == "gateway" ? "vmbr0" : "vmbr90"
    model       = "virtio"
    vlan_id     = each.value.role == "gateway" ? 10 : null
    mac_address = format("02:ca:90:00:%02x:%02x", floor(each.value.vmid / 256), each.value.vmid % 256)
    firewall    = false # Isolation is outside the learner VM: host guard + gateway.
  }
  dynamic "network_device" {
    for_each = each.value.role == "gateway" ? [1] : []
    content {
      bridge      = "vmbr90"
      model       = "virtio"
      mac_address = "02:ca:90:01:02:bc"
      firewall    = false
    }
  }
  initialization {
    datastore_id         = "local-lvm"
    type                 = "nocloud"
    user_data_file_id    = proxmox_virtual_environment_file.cloud_init[each.key].id
    network_data_file_id = proxmox_virtual_environment_file.network[each.key].id
  }
  operating_system { type = "l26" }
  serial_device {}
}
