locals {
  cluster_nodes = {
    for cluster_name in keys(var.clusters) : cluster_name => {
      for name, node in var.nodes : name => node if node.cluster == cluster_name
    }
  }
  controlplanes = {
    for cluster_name, nodes in local.cluster_nodes : cluster_name => {
      for name, node in nodes : name => node if node.role == "controlplane"
    }
  }
  workers = {
    for cluster_name, nodes in local.cluster_nodes : cluster_name => {
      for name, node in nodes : name => node if node.role == "worker"
    }
  }
  bootstrap = {
    for cluster_name, nodes in local.controlplanes : cluster_name => sort(keys(nodes))[0]
  }
  installer = "factory.talos.dev/metal-installer/${var.talos_schematic_id}:${var.talos_version}"
}

resource "proxmox_virtual_environment_vm" "node" {
  for_each = var.nodes

  lifecycle {
    replace_triggered_by = [proxmox_virtual_environment_vm.talos_nocloud_template.id]
  }

  name        = each.key
  node_name   = var.node_name
  vm_id       = each.value.vm_id
  pool_id     = var.node_pool
  description = "Talos ${each.value.role} for ${each.value.cluster}"

  started    = true
  on_boot    = true
  boot_order = ["scsi0", "ide2"]

  clone {
    vm_id        = proxmox_virtual_environment_vm.talos_nocloud_template.vm_id
    node_name    = var.node_name
    datastore_id = var.datastore
    full         = true
  }

  agent {
    enabled = false
  }

  # Declare the boot ISO on labmgmt explicitly. Existing clones do not inherit
  # hardware changes made later to template 1234.
  cdrom {
    file_id   = proxmox_download_file.talos_nocloud_iso.id
    interface = "ide2"
  }

  initialization {
    datastore_id = var.datastore
    # ide2 is the explicit Talos boot ISO above. CAPMOX uses ide0 for workload
    # seeds, so use a third interface for labmgmt's seed.
    interface = "sata0"
    type      = "nocloud"

    dns {
      servers = var.nameservers
    }

    ip_config {
      ipv4 {
        address = each.value.address
        gateway = each.value.gateway
      }
    }
  }

  cpu {
    type    = "host"
    cores   = each.value.cores
    sockets = 1
  }

  memory {
    dedicated = each.value.memory
    floating  = each.value.memory
  }

  disk {
    datastore_id = var.datastore
    file_format  = "raw"
    size         = each.value.storage
    interface    = "scsi0"
    discard      = "on"
    ssd          = true
  }

  network_device {
    bridge      = each.value.network_bridge
    mac_address = each.value.mac_address
    model       = "virtio"
    vlan_id     = var.kubernetes_vlan_id
  }

  operating_system {
    type = "l26"
  }
}
