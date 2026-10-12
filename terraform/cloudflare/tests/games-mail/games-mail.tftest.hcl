mock_provider "cloudflare" {}

run "disabled_mail_has_no_records" {
  command = plan

  assert {
    condition     = length(cloudflare_record.games_mail_host) == 0 && length(cloudflare_record.games_mail) == 0
    error_message = "Disabled mail must plan successfully without any mail DNS records."
  }
}

run "enabled_mail_preserves_legacy_records" {
  command = plan

  variables {
    games_mail = {
      egress_ipv4     = "192.0.2.10"
      dkim_selector   = "test"
      dkim_public_key = "TEST_PUBLIC_KEY"
    }
  }

  assert {
    condition     = length(cloudflare_record.games_mail_host) == 1 && cloudflare_record.games_mail_host[0].content == "192.0.2.10"
    error_message = "Enabled mail must keep its existing counted A-record address."
  }

  assert {
    condition     = length(cloudflare_record.games_mail) == 3 && cloudflare_record.games_mail["dkim"].name == "test._domainkey.games" && cloudflare_record.games_mail["dkim"].content == "v=DKIM1; k=rsa; p=TEST_PUBLIC_KEY"
    error_message = "Enabled mail must retain the SPF, DKIM and DMARC records."
  }
}
