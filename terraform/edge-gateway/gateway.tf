locals {
  resources_enabled = var.enabled || var.retain_gateway_resources

  nftables_config = templatefile("${path.module}/nftables.conf.tftpl", {
    forwards                = var.forwards
    public_ssh_source_cidrs = var.public_ssh_source_cidrs
  })

  bootstrap_revision = sha256(jsonencode({
    image             = var.image
    location          = var.location
    name              = var.name
    nftables          = local.nftables_config
    server_type       = var.server_type
    ssh_public_key    = trimspace(file(pathexpand(var.ssh_public_key_path)))
    tailscale_tag     = var.tailscale_tag
    tailscale_version = var.tailscale_version
  }))
}

resource "terraform_data" "bootstrap_revision" {
  count            = local.resources_enabled ? 1 : 0
  triggers_replace = [local.bootstrap_revision]
}

resource "tailscale_tailnet_key" "edge_gateway" {
  count         = var.enabled ? 1 : 0
  reusable      = false
  ephemeral     = var.tailscale_ephemeral
  preauthorized = true
  expiry        = 3600
  tags          = [var.tailscale_tag]

  lifecycle {
    replace_triggered_by = [terraform_data.bootstrap_revision[0]]
  }
}

resource "hcloud_ssh_key" "operator" {
  count      = local.resources_enabled ? 1 : 0
  name       = "${var.name}-operator"
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "hcloud_primary_ip" "edge_gateway" {
  count       = local.resources_enabled ? 1 : 0
  name        = "${var.name}-ipv4"
  type        = "ipv4"
  location    = var.location
  auto_delete = false

  labels = {
    component = "edge-gateway"
    managed   = "terraform"
  }
}

resource "hcloud_firewall" "edge_gateway" {
  count = local.resources_enabled ? 1 : 0
  name  = "${var.name}-firewall"

  rule {
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0"]
    description = "IPv4 diagnostics and path MTU discovery"
  }

  rule {
    direction   = "in"
    protocol    = "udp"
    port        = "41641"
    source_ips  = ["0.0.0.0/0"]
    description = "Tailscale direct WireGuard traffic"
  }

  dynamic "rule" {
    for_each = length(var.public_ssh_source_cidrs) == 0 ? [] : [var.public_ssh_source_cidrs]
    content {
      direction   = "in"
      protocol    = "tcp"
      port        = "22"
      source_ips  = sort(tolist(rule.value))
      description = "Restricted public SSH recovery access"
    }
  }

  dynamic "rule" {
    for_each = var.forwards
    content {
      direction   = "in"
      protocol    = lower(rule.value.protocol)
      port        = tostring(rule.value.listen_port)
      source_ips  = sort(tolist(rule.value.source_cidrs))
      description = "Forward ${rule.key}"
    }
  }

  labels = {
    component = "edge-gateway"
    managed   = "terraform"
  }
}

resource "hcloud_server" "edge_gateway" {
  count       = var.enabled ? 1 : 0
  name        = var.name
  image       = var.image
  server_type = var.server_type
  location    = var.location
  ssh_keys    = [hcloud_ssh_key.operator[0].id]
  firewall_ids = [
    hcloud_firewall.edge_gateway[0].id,
  ]

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    auth_key_b64        = base64encode(tailscale_tailnet_key.edge_gateway[0].key)
    hostname            = var.name
    nftables_config_b64 = base64encode(local.nftables_config)
    tailscale_version   = var.tailscale_version
  })

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.edge_gateway[0].id
    ipv6_enabled = false
  }

  backups            = false
  delete_protection  = false
  rebuild_protection = false

  labels = {
    component = "edge-gateway"
    managed   = "terraform"
  }
}

data "cloudflare_zone" "public" {
  name = var.public_dns_zone
}

resource "cloudflare_record" "public_services" {
  for_each = local.resources_enabled && var.publish_dns ? var.public_dns_records : toset([])

  zone_id = data.cloudflare_zone.public.id
  name    = each.value
  content = hcloud_primary_ip.edge_gateway[0].ip_address
  type    = "A"
  ttl     = var.public_dns_ttl
  proxied = false
}
