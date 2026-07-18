resource "talos_machine_secrets" "cluster" {
  for_each = var.clusters

  talos_version = var.talos_version
}

data "talos_machine_configuration" "node" {
  for_each = var.nodes

  cluster_name       = each.value.cluster
  cluster_endpoint   = "https://${var.clusters[each.value.cluster].endpoint}:6443"
  machine_type       = each.value.role
  machine_secrets    = talos_machine_secrets.cluster[each.value.cluster].machine_secrets
  talos_version      = var.talos_version
  kubernetes_version = "1.36.1"
}

locals {
  node_patches = {
    for name, node in var.nodes : name => yamlencode({
      machine = {
        install = {
          disk  = "/dev/sda"
          image = local.installer
        }
        network = {
          nameservers = var.nameservers
          interfaces = [merge({
            deviceSelector = {
              hardwareAddr = node.mac_address
            }
            addresses = [node.address]
            routes = [{
              network = "0.0.0.0/0"
              gateway = node.gateway
            }]
            }, node.role == "controlplane" && try(var.clusters[node.cluster].control_plane_vip, null) != null ? {
            vip = { ip = var.clusters[node.cluster].control_plane_vip }
          } : {})]
        }
      }
      cluster = {
        # A cluster without workers must run workloads on its control-plane node.
        allowSchedulingOnControlPlanes = length(local.workers[node.cluster]) == 0
      }
    })
  }
}

resource "talos_machine_configuration_apply" "node" {
  for_each = var.nodes

  depends_on                  = [proxmox_virtual_environment_vm.node]
  client_configuration        = talos_machine_secrets.cluster[each.value.cluster].client_configuration
  machine_configuration_input = data.talos_machine_configuration.node[each.key].machine_configuration
  config_patches              = [local.node_patches[each.key]]
  endpoint                    = split("/", each.value.address)[0]
  node                        = split("/", each.value.address)[0]

  timeouts = {
    create = "15m"
    update = "15m"
  }
}

resource "talos_machine_bootstrap" "cluster" {
  for_each = var.clusters

  depends_on           = [talos_machine_configuration_apply.node]
  client_configuration = talos_machine_secrets.cluster[each.key].client_configuration
  endpoint             = split("/", local.controlplanes[each.key][local.bootstrap[each.key]].address)[0]
  node                 = split("/", local.controlplanes[each.key][local.bootstrap[each.key]].address)[0]
}

data "talos_client_configuration" "cluster" {
  for_each = var.clusters

  cluster_name         = each.key
  client_configuration = talos_machine_secrets.cluster[each.key].client_configuration
  endpoints            = [for node in values(local.controlplanes[each.key]) : split("/", node.address)[0]]
  nodes                = [for node in values(local.cluster_nodes[each.key]) : split("/", node.address)[0]]
}

resource "talos_cluster_kubeconfig" "cluster" {
  for_each = var.clusters

  depends_on           = [talos_machine_bootstrap.cluster]
  client_configuration = talos_machine_secrets.cluster[each.key].client_configuration
  endpoint             = split("/", local.controlplanes[each.key][local.bootstrap[each.key]].address)[0]
  node                 = split("/", local.controlplanes[each.key][local.bootstrap[each.key]].address)[0]
}
