locals {
  ansible_role_dir = "${path.module}/../../ansible/roles/proxmox_vlan_router"
  ansible_role_hash = sha256(join("", [
    for file in sort(fileset(local.ansible_role_dir, "**")) : filesha256("${local.ansible_role_dir}/${file}")
  ]))
}

resource "terraform_data" "proxmox_vlan_router" {
  triggers_replace = [
    local.ansible_role_hash,
    filesha256("${path.module}/../../ansible/proxmox-router.yml"),
    filesha256("${path.module}/../../ansible/inventories/main/hosts"),
  ]

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = "ansible-playbook -i ansible/inventories/main/hosts ansible/proxmox-router.yml --diff"
  }
}
