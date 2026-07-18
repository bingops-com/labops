node_name                    = "homelab"
node_pool                    = "Kubernetes"
datastore                    = "nvme2-lvm"
iso_datastore                = "local"
talos_nocloud_template_vm_id = 1234

clusters = {
  labmgmt = {
    endpoint = "192.168.1.150"
  }
}

nodes = {
  talos-labmgmt-cp-01 = {
    address        = "192.168.1.150/24"
    gateway        = "192.168.1.1"
    vm_id          = 150
    mac_address    = "02:00:00:00:01:50"
    cores          = 4
    memory         = 8192
    storage        = 100
    network_bridge = "vmbr0"
    cluster        = "labmgmt"
    role           = "controlplane"
  }
}
