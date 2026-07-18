output "node_addresses" {
  description = "Talos node addresses by hostname."
  value       = { for name, node in var.nodes : name => split("/", node.address)[0] }
}

output "talos_nocloud_template" {
  description = "Terraform-managed Proxmox template used by labmgmt and CAPMOX."
  value = {
    node  = var.node_name
    vm_id = proxmox_virtual_environment_vm.talos_nocloud_template.vm_id
  }
}

output "talosconfigs" {
  description = "Talos client configurations keyed by cluster name."
  value       = { for name, config in data.talos_client_configuration.cluster : name => config.talos_config }
  sensitive   = true
}

output "kubeconfigs" {
  description = "Kubernetes client configurations keyed by cluster name."
  value       = { for name, config in talos_cluster_kubeconfig.cluster : name => config.kubeconfig_raw }
  sensitive   = true
}
