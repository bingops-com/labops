locals {
  nocloud_iso_url = "https://factory.talos.dev/image/${var.talos_schematic_id}/${var.talos_version}/nocloud-amd64.iso"
}

resource "proxmox_download_file" "talos_nocloud_iso" {
  content_type = "iso"
  datastore_id = var.iso_datastore
  node_name    = var.node_name
  file_name    = "talos-${var.talos_version}-nocloud-amd64.iso"
  url          = local.nocloud_iso_url
  overwrite    = false
}

resource "proxmox_virtual_environment_vm" "talos_nocloud_template" {
  name        = "talos-${var.talos_version}-nocloud"
  node_name   = var.node_name
  vm_id       = var.talos_nocloud_template_vm_id
  pool_id     = var.node_pool
  description = "Talos nocloud template managed by Terraform for CAPI"

  started    = false
  on_boot    = true
  template   = true
  boot_order = ["scsi0", "ide0"]

  agent {
    enabled = false
  }

  cdrom {
    file_id   = proxmox_download_file.talos_nocloud_iso.id
    interface = "ide0"
  }

  cpu {
    type    = "host"
    cores   = 2
    sockets = 1
  }

  memory {
    dedicated = 2048
    floating  = 2048
  }

  disk {
    datastore_id = var.datastore
    file_format  = "raw"
    interface    = "scsi0"
    size         = 32
  }

  network_device {
    bridge = "vmbr0"
    model  = "virtio"
  }

  operating_system {
    type = "l26"
  }
}
