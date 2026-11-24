mock_provider "hcloud" {
  mock_resource "hcloud_firewall" {
    defaults = {
      id = "101"
    }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = {
      id = "102"
    }
  }
  mock_resource "hcloud_primary_ip" {
    defaults = {
      id         = "100"
      ip_address = "192.0.2.10"
    }
  }
}

mock_provider "tailscale" {}

mock_provider "cloudflare" {
  mock_data "cloudflare_zone" {
    defaults = {
      id = "00000000000000000000000000000000"
    }
  }
}

variables {
  ssh_public_key_path = "tests/operator.pub"
}

run "default_retains_existing_gateway" {
  command = apply

  assert {
    condition     = length(hcloud_server.edge_gateway) == 1
    error_message = "The default must keep the existing gateway enabled."
  }

  assert {
    condition     = length(tailscale_tailnet_key.edge_gateway) == 1
    error_message = "An enabled gateway needs its own single-use auth key."
  }
}

run "suspend_retains_address_and_dns" {
  command = apply

  variables {
    enabled = false
  }

  assert {
    condition     = length(hcloud_server.edge_gateway) == 0 && length(tailscale_tailnet_key.edge_gateway) == 0
    error_message = "Suspension must remove the VM and its consumed bootstrap key."
  }

  assert {
    condition     = output.public_ipv4 == run.default_retains_existing_gateway.public_ipv4 && length(cloudflare_record.public_services) == 1
    error_message = "Suspension must preserve the public IPv4 and DNS record."
  }

  assert {
    condition     = output.server_id == null && output.server_name == null
    error_message = "Suspension must expose absent VM outputs safely."
  }

  assert {
    condition     = hcloud_primary_ip.edge_gateway[0].auto_delete == false
    error_message = "The stable IPv4 must not disappear with the VM."
  }
}

run "resume_recreates_compute_with_same_address" {
  command = apply

  variables {
    enabled             = true
    tailscale_ephemeral = true
  }

  assert {
    condition     = length(hcloud_server.edge_gateway) == 1 && length(tailscale_tailnet_key.edge_gateway) == 1
    error_message = "Resume must create a new VM and a fresh bootstrap key."
  }

  assert {
    condition     = one(hcloud_server.edge_gateway[0].public_net).ipv4 == tonumber(hcloud_primary_ip.edge_gateway[0].id)
    error_message = "The resumed VM must use the retained address."
  }

  assert {
    condition     = tailscale_tailnet_key.edge_gateway[0].ephemeral
    error_message = "New session gateways should enroll as ephemeral Tailscale nodes."
  }
}

run "withdraw_dns_without_releasing_address" {
  command = apply
  variables {
    enabled                  = false
    retain_gateway_resources = true
    publish_dns              = false
  }
  assert {
    condition     = length(hcloud_primary_ip.edge_gateway) == 1 && length(cloudflare_record.public_services) == 0 && length(hcloud_server.edge_gateway) == 0
    error_message = "DNS draining must keep the address while removing records and compute."
  }
}

run "release_all_ephemeral_resources" {
  command = apply
  variables {
    enabled                  = false
    retain_gateway_resources = false
    publish_dns              = false
  }
  assert {
    condition     = length(hcloud_primary_ip.edge_gateway) == 0 && length(hcloud_firewall.edge_gateway) == 0 && length(hcloud_ssh_key.operator) == 0 && length(terraform_data.bootstrap_revision) == 0
    error_message = "An idle ephemeral gateway must retain no cloud infrastructure."
  }
  assert {
    condition     = output.public_ipv4 == null && length(output.public_forwards) == 0 && length(output.public_hostnames) == 0
    error_message = "Absent endpoints must have safe null/empty outputs."
  }
}

run "start_ephemeral_gateway_and_publish_dns" {
  command = apply
  variables {
    enabled                  = true
    retain_gateway_resources = false
    publish_dns              = true
    public_dns_ttl           = 60
  }
  assert {
    condition     = length(hcloud_server.edge_gateway) == 1 && length(hcloud_primary_ip.edge_gateway) == 1 && length(cloudflare_record.public_services) == 1 && length(tailscale_tailnet_key.edge_gateway) == 1
    error_message = "Starting must allocate an address, compute, fresh key and DNS together."
  }
  assert {
    condition     = alltrue([for r in cloudflare_record.public_services : r.ttl == 60 && !r.proxied && r.content == output.public_ipv4])
    error_message = "Each game hostname must follow the current unproxied IPv4 with a short TTL."
  }
}

run "second_ephemeral_stop_releases_everything" {
  command = apply
  variables {
    enabled                  = false
    retain_gateway_resources = false
    publish_dns              = false
  }
  assert {
    condition     = length(hcloud_server.edge_gateway) == 0 && length(hcloud_primary_ip.edge_gateway) == 0 && length(cloudflare_record.public_services) == 0 && length(tailscale_tailnet_key.edge_gateway) == 0
    error_message = "Repeated start/stop cycles must not leave paid resources or stale DNS."
  }
}
