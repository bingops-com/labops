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
    username    = "bingo"
    private_key = file(pathexpand(var.proxmox_ssh_private_key_path))
    node {
      name    = var.node_name
      address = var.proxmox_ssh_host
    }
  }
}

locals {
  image_build       = "20261116-2664"
  image_url         = "https://cloud.debian.org/images/cloud/trixie/${local.image_build}/debian-13-genericcloud-amd64-${local.image_build}.qcow2"
  image_sha512      = "37cb32b320820417eb04b335afcf489bfb4cecce4a957190d09cb2bffbe02b56a1cadd62d78c6ead92aa7839d5ea65e4260f994bbb4b54490df59fdf11ee1d97"
  apt_tools         = jsondecode(file("${path.module}/../../environments/dev-vm/apt-tools.json"))
  tailscale_version = one([for tool in local.apt_tools : tool.version if tool.name == "tailscale"])
}

resource "proxmox_virtual_environment_pool" "dev" {
  pool_id = "Development"
  comment = "Standalone development VM; terraform/dev-vm owns its lifecycle."
}

resource "proxmox_storage_directory" "snippets" {
  id               = "dev-vm-snippets"
  path             = "/var/lib/vz/dev-vm-snippets"
  nodes            = [var.node_name]
  content          = ["snippets"]
  create_base_path = true
  create_subdirs   = true
  shared           = false
}

resource "proxmox_download_file" "debian" {
  node_name          = var.node_name
  datastore_id       = "local"
  content_type       = "iso"
  file_name          = "dev-debian-13-${local.image_build}.img"
  url                = local.image_url
  checksum           = local.image_sha512
  checksum_algorithm = "sha512"
  overwrite          = false
}

resource "proxmox_virtual_environment_file" "cloud_init" {
  node_name    = var.node_name
  datastore_id = proxmox_storage_directory.snippets.id
  content_type = "snippets"
  upload_mode  = "stream"
  overwrite    = true
  source_raw {
    file_name = "dev-cloud-init.yaml"
    data = "#cloud-config\n${yamlencode({
      hostname        = "dev"
      ssh_pwauth      = false
      disable_root    = true
      package_update  = true
      package_upgrade = false
      timezone        = "Etc/UTC"
      bootcmd         = [["cloud-init-per", "once", "dev-ssh-bootstrap", "systemctl", "mask", "--now", "ssh.service", "ssh.socket"]]
      users = [{
        name                = "dev"
        uid                 = 1000
        ssh_authorized_keys = [for key in split("\n", trimspace(file("${path.module}/../../environments/dev-vm/authorized_keys"))) : key if trimspace(key) != "" && !startswith(trimspace(key), "#")]
        groups              = ["sudo"]
        shell               = "/bin/bash"
        lock_passwd         = true
        sudo                = ["ALL=(ALL) NOPASSWD:ALL"]
      }]
      packages = ["qemu-guest-agent", "nftables", "curl", "ca-certificates", "openssh-server", "python3", "sudo"]
      write_files = [
        { path = "/etc/nftables.conf", permissions = "0644", content = file("${path.module}/../../ansible/roles/dev_vm/files/nftables.conf") },
        { path = "/usr/local/sbin/dev-first-boot", permissions = "0755", content = templatefile("${path.module}/templates/first-boot.sh.tftpl", { tailscale_version = local.tailscale_version }) },
        { path = "/etc/ssh/sshd_config.d/00-dev-vm.conf", permissions = "0644", content = file("${path.module}/../../ansible/roles/dev_vm/files/sshd.conf") }
      ]
      runcmd = [["/usr/local/sbin/dev-first-boot"]]
    })}"
  }
}

resource "proxmox_virtual_environment_vm" "dev" {
  node_name   = var.node_name
  vm_id       = var.vm_id
  name        = "dev"
  pool_id     = proxmox_virtual_environment_pool.dev.pool_id
  description = "Development VM. SSH and HTTPS only over Tailscale. No Coder runtime."
  on_boot     = true
  started     = true
  boot_order  = ["scsi0"]
  tags        = ["dev", "terraform", "tailscale"]
  cpu {
    cores = 4
    type  = "host"
  }
  memory {
    dedicated = 8192
    floating  = 0
  }
  agent {
    enabled = true
    wait_for_ip {
      disabled = true
    }
  }
  disk {
    datastore_id = "local-lvm"
    file_id      = proxmox_download_file.debian.id
    interface    = "scsi0"
    file_format  = "raw"
    size         = 80
    discard      = "on"
    ssd          = true
  }
  network_device {
    bridge      = "vmbr0"
    model       = "virtio"
    vlan_id     = 10
    mac_address = "02:DE:00:00:01:60"
  }
  initialization {
    datastore_id      = "local-lvm"
    type              = "nocloud"
    user_data_file_id = proxmox_virtual_environment_file.cloud_init.id
    dns {
      servers = ["1.1.1.1", "9.9.9.9"]
    }
    ip_config {
      ipv4 {
        address = var.address
        gateway = "192.168.10.1"
      }
    }
  }
  operating_system {
    type = "l26"
  }
  serial_device {}
  lifecycle {
    prevent_destroy = true
    # First-boot user data reconstructs a lost VM; Ansible owns the live OS.
    ignore_changes = [initialization[0].user_data_file_id]
  }
}

output "dev" {
  value = { vm_id = var.vm_id, node = var.node_name, address = var.address, ssh_user = "dev", ssh_access = "Tailscale only; enroll via Proxmox guest agent before configuration" }
}
