output "lab" {
  description = "Non-sensitive lab inventory; use management_ip for SSH and lab_ip for Kubernetes."
  value = {
    for name, node in var.nodes : name => {
      vm_id         = proxmox_virtual_environment_vm.node[name].vm_id
      management_ip = split("/", node.management_address)[0]
      lab_ip        = split("/", node.lab_address)[0]
      user          = "ubuntu"
      vcpus         = node.vcpus
      memory_mib    = node.memory_mib
    }
  }
}
