resource "cloudflare_r2_bucket" "cnpg_backups" {
  for_each = toset(["labprod"])

  account_id = var.cloudflare_account_id
  name       = "bingops-cnpg-${each.key}"
  location   = "WEUR"
}
