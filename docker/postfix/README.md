# Postfix image

The pinned upstream Alpine image is rebuilt with current security updates.
The unused OAuth Python environment is removed; Cyrus SASL submission auth and
OpenDKIM remain. CI loads this exact image, runs isolated SMTP/queue tests,
blocks HIGH/CRITICAL vulnerabilities, then publishes it only after merge.

Bump VERSION and the Mail Deployment reference together for a new release;
keep published version tags immutable. GHCR must be public before an anonymous
cluster pull. No credentials are used at build time. Runtime ownership,
Bitwarden inputs, recovery and acceptance live in
[the Mail runbook](../../apps/platform/mail/labprod/README.md).
