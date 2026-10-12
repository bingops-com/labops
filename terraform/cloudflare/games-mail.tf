# Postfix direct delivery. The website CNAME is separate from these mail names.
locals {
  games_mail_dns_records = local.games_mail == null ? {} : {
    spf = {
      name    = "smtp.games"
      content = "v=spf1 a -all"
    }
    dkim = {
      name    = "${local.games_mail.dkim_selector}._domainkey.games"
      content = "v=DKIM1; k=rsa; p=${local.games_mail.dkim_public_key}"
    }
    dmarc = {
      name    = "_dmarc.games"
      content = "v=DMARC1; p=none; adkim=s; aspf=r"
    }
  }
}

resource "cloudflare_record" "games_mail_host" {
  count = local.games_mail == null ? 0 : 1

  zone_id = var.cloudflare_lab_zone_id
  name    = "smtp.games"
  type    = "A"
  content = local.games_mail.egress_ipv4
  proxied = false
  ttl     = 3600
}

resource "cloudflare_record" "games_mail" {
  for_each = local.games_mail_dns_records

  zone_id = var.cloudflare_lab_zone_id
  name    = each.value.name
  type    = "TXT"
  content = each.value.content
  proxied = false
  ttl     = 3600
}
