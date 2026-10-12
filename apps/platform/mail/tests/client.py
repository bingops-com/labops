#!/usr/bin/env python3
"""Synthetic SMTP client, run on the isolated Docker test network."""
import hashlib
import os
import smtplib
import ssl

address = os.environ["SMTP_TEST_ADDRESS"]
password = os.environ["SMTPD_SASL_USERS"].split(":", 1)[1]


def connect(verified=True):
    client = smtplib.SMTP(address, 587, timeout=10)
    client.ehlo()
    if verified:
        client._host = "smtp.games.lab.bingo"
    try:
        client.starttls(context=ssl.create_default_context(cafile="/test/ca.crt"))
    except Exception:
        client.close()
        raise
    client.ehlo()
    return client


if os.environ["SMTP_TEST_MODE"] == "fingerprint":
    with connect() as client:
        print(hashlib.sha256(client.sock.getpeercert(binary_form=True)).hexdigest())
else:
    with smtplib.SMTP(address, 587, timeout=10) as client:
        client.ehlo()
        assert not client.has_extn("auth"), "AUTH advertised before TLS"
        assert client.mail("bounces@smtp.games.lab.bingo")[0] == 530, "plaintext mail accepted"
    print("PASS: plaintext submission rejected, AUTH hidden before TLS", flush=True)
    try:
        connect(verified=False)
    except ssl.SSLCertVerificationError:
        pass
    else:
        raise AssertionError("wrong certificate hostname accepted")
    with connect() as client:
        client.mail("bounces@smtp.games.lab.bingo")
        assert client.rcpt("recipient@example.invalid")[0] >= 500, "anonymous relay accepted"
    with connect() as client:
        try:
            client.login("games@games.lab.bingo", "incorrect-synthetic-password")
        except smtplib.SMTPAuthenticationError:
            pass
        else:
            raise AssertionError("incorrect password accepted")
    print("PASS: verified STARTTLS, anonymous and incorrect-password relay rejected", flush=True)
    with connect() as client:
        client.login("games@games.lab.bingo", password)
        client.mail("sender@unrelated.invalid")
        assert client.rcpt("recipient@example.invalid")[0] >= 500, "unrelated sender domain accepted"
        client.rset()
        client.sendmail("bounces@smtp.games.lab.bingo", ["recipient@example.invalid"],
                        "From: noreply@games.lab.bingo\r\nTo: recipient@example.invalid\r\n"
                        "Subject: Synthetic SMTP test\r\n\r\nSynthetic test, no real reset link.\r\n")
    print("PASS: authenticated SMTP submission", flush=True)
