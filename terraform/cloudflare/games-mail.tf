# Public DNS metadata supplied by Resend for mail.games.lab.bingo.
# Fill this map from the domain verification screen before deploying Games.
# Example shape (no invented records): key = { type, name, content, priority }.
locals {
  games_mail_dns_records = {}
}

resource "cloudflare_record" "games_mail" {
  for_each = local.games_mail_dns_records

  zone_id  = var.cloudflare_lab_zone_id
  name     = each.value.name
  type     = each.value.type
  content  = each.value.content
  priority = try(each.value.priority, null)
  proxied  = false
  ttl      = 3600
}
