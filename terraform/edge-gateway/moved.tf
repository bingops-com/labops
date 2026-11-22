# Preserve the current VM and bootstrap-key addresses when enabling lifecycle
# control. These declarations must remain until all retained states migrated.
moved {
  from = hcloud_server.edge_gateway
  to   = hcloud_server.edge_gateway[0]
}

moved {
  from = tailscale_tailnet_key.edge_gateway
  to   = tailscale_tailnet_key.edge_gateway[0]
}
