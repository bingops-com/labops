locals {
  ubuntu_release = "20261020"
  ubuntu_url     = "https://cloud-images.ubuntu.com/releases/jammy/release-20261020/ubuntu-22.04-server-cloudimg-amd64.img"
  ubuntu_sha256  = "2099e63da0b822ef8e05e3d596c1b402eaaae658fc08ab919cb8495bfcdc488b"
  ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
  hosts = join("\n", concat([
    "127.0.0.1 localhost",
    "::1 localhost ip6-localhost ip6-loopback"
  ], [for name, node in var.nodes : "${split("/", node.lab_address)[0]} ${name}"], [""]))
}

resource "proxmox_virtual_environment_pool" "cka" {
  pool_id = "CKA"
  comment = "Disposable Ubuntu CKA training lab; terraform/cka owns its lifecycle."
}

resource "proxmox_storage_directory" "snippets" {
  id               = "cka-snippets"
  path             = "/var/lib/vz/cka-snippets"
  nodes            = [var.node_name]
  content          = ["snippets"]
  create_base_path = true
  create_subdirs   = true
  shared           = false
}

# PVE 8.3 accepts cloud disk images as iso/*.img. The newer import content
# type is deliberately not enabled on the existing shared local datastore.
resource "proxmox_download_file" "ubuntu" {
  node_name          = var.node_name
  datastore_id       = var.image_datastore
  content_type       = "iso"
  file_name          = "cka-ubuntu-22.04-${local.ubuntu_release}.img"
  url                = local.ubuntu_url
  checksum           = local.ubuntu_sha256
  checksum_algorithm = "sha256"
  overwrite          = false
}

resource "proxmox_virtual_environment_file" "cloud_init" {
  for_each     = var.nodes
  node_name    = var.node_name
  datastore_id = proxmox_storage_directory.snippets.id
  content_type = "snippets"
  upload_mode  = "stream"
  overwrite    = false

  source_raw {
    file_name = "cka-${each.key}-cloud-init.yaml"
    data = "#cloud-config\n${yamlencode({
      hostname         = each.key
      manage_etc_hosts = false
      ssh_pwauth       = false
      disable_root     = true
      package_update   = true
      package_upgrade  = false
      timezone         = "Etc/UTC"
      users = [{
        name                = "ubuntu"
        groups              = ["sudo"]
        shell               = "/bin/bash"
        lock_passwd         = true
        sudo                = ["ALL=(ALL) NOPASSWD:ALL"]
        ssh_authorized_keys = [local.ssh_public_key]
      }]
      packages = concat(["qemu-guest-agent", "rsync", "nfs-common"], each.key == "k8s-master" ? ["nfs-kernel-server"] : [])
      write_files = concat([
        {
          path        = "/etc/hosts"
          owner       = "root:root"
          permissions = "0644"
          content     = local.hosts
        },
        {
          path        = "/etc/cka-lab.json"
          owner       = "root:root"
          permissions = "0644"
          content     = jsonencode({ name = each.key, lab_ip = split("/", each.value.lab_address)[0], management_ip = split("/", each.value.management_address)[0], kubernetes_preinstalled = false })
        },
        {
          path        = "/usr/local/sbin/cka-base-setup"
          owner       = "root:root"
          permissions = "0755"
          content     = file("${path.module}/templates/base-setup.sh")
        }
        ], each.key == "k8s-master" ? [
        {
          path        = "/etc/exports.d/cka.exports"
          owner       = "root:root"
          permissions = "0644"
          content     = "/opt/shared ${split("/", var.nodes["k8s-worker-1"].lab_address)[0]}(rw,sync,no_subtree_check,root_squash)\n"
        },
        {
          path        = "/etc/nfs.conf.d/cka.conf"
          owner       = "root:root"
          permissions = "0644"
          content     = "[nfsd]\nvers3=n\nvers4=y\nudp=n\ntcp=y\n"
        }
        ] : [
        {
          path        = "/etc/systemd/system/opt-shared.mount"
          owner       = "root:root"
          permissions = "0644"
          content     = "[Unit]\nDescription=CKA shared files from master\nWants=network-online.target\nAfter=network-online.target\n\n[Mount]\nWhat=${split("/", var.nodes["k8s-master"].lab_address)[0]}:/opt/shared\nWhere=/opt/shared\nType=nfs4\nOptions=rw,hard,timeo=50,retrans=2\n"
        },
        {
          path        = "/etc/systemd/system/opt-shared.automount"
          owner       = "root:root"
          permissions = "0644"
          content     = "[Unit]\nDescription=CKA shared files automount\n\n[Automount]\nWhere=/opt/shared\nTimeoutIdleSec=60\n\n[Install]\nWantedBy=multi-user.target\n"
        }
      ])
      runcmd = concat([
        ["/usr/local/sbin/cka-base-setup"]
        ], each.key == "k8s-master" ? [
        ["systemctl", "enable", "--now", "nfs-kernel-server.service"],
        ["exportfs", "-ra"],
        ["systemctl", "restart", "nfs-kernel-server.service"]
        ] : [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "opt-shared.automount"]
      ])
    })}"
  }
}

resource "proxmox_virtual_environment_vm" "node" {
  for_each    = var.nodes
  node_name   = var.node_name
  vm_id       = each.value.vm_id
  name        = each.key
  pool_id     = proxmox_virtual_environment_pool.cka.pool_id
  description = "CKA Ubuntu 22.04 lab; ${each.value.lab_address}; Kubernetes installed manually by the learner."
  tags        = ["cka", "terraform", "ubuntu-22-04"]
  on_boot     = true
  started     = true
  boot_order  = ["scsi0"]

  cpu {
    cores   = each.value.vcpus
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = each.value.memory_mib
    floating  = 0
  }

  agent {
    enabled = true
    wait_for_ip {
      disabled = true
    }
  }

  disk {
    datastore_id = var.disk_datastore
    file_id      = proxmox_download_file.ubuntu.id
    interface    = "scsi0"
    file_format  = "raw"
    size         = var.disk_gib
    discard      = "on"
    ssd          = true
  }

  network_device {
    bridge      = var.bridge
    model       = "virtio"
    vlan_id     = var.management_vlan
    mac_address = each.value.management_mac
    firewall    = false
  }

  network_device {
    bridge      = var.bridge
    model       = "virtio"
    vlan_id     = var.lab_vlan
    mac_address = each.value.lab_mac
    firewall    = false
  }

  initialization {
    datastore_id      = var.disk_datastore
    type              = "nocloud"
    user_data_file_id = proxmox_virtual_environment_file.cloud_init[each.key].id
    dns {
      servers = var.dns_servers
    }
    ip_config {
      ipv4 {
        address = each.value.management_address
        gateway = var.management_gateway
      }
    }
    ip_config {
      ipv4 {
        address = each.value.lab_address
      }
    }
  }

  operating_system {
    type = "l26"
  }
  serial_device {}
}
