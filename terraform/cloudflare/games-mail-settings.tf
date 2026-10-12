# Public metadata only. Populate with configure-smtp.py after verifying egress
# and storing the DKIM private key in Bitwarden. Null creates no mail records.
locals {
  games_mail = null
}
