resource "cloudflare_r2_bucket" "cnpg_backups" {
  for_each = toset(["labprod"])

  account_id = var.cloudflare_account_id
  name       = "bingops-cnpg-${each.key}"
  location   = "WEUR"
}

resource "cloudflare_r2_bucket" "pz_backups" {
  for_each = toset(["labprod"])

  account_id = var.cloudflare_account_id
  name       = "bingops-pz-${each.key}"
  location   = "WEUR"
}
