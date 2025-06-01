node_name = "homelab"
node_pool = "Kubernetes"

nodes = {
  # Production
  prodk3s = {
    host_ip        = "192.168.1.160/24"
    gw             = "192.168.1.1"
    vm_id          = 160
    cores          = 4
    memory         = 8192 # 8GB
    storage        = 300 # GB
    network_bridge = "vmbr0"
    role           = "master"
    environment    = "production"
  },
  # Preprod
  ppk3s = {
    host_ip        = "192.168.1.170/24"
    gw             = "192.168.1.1"
    vm_id          = 170
    cores          = 2
    memory         = 4096 # 4GB
    storage        = 300 # GB
    network_bridge = "vmbr0"
    role           = "master"
    environment    = "preprod"
  }
}

datastore      = "nvme2-lvm"
template_vm_id = "9999"
