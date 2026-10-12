# Postfix for Games

LabOps owns this internal, outbound-only relay. Games connects to
`relay.mail.svc:587`, verifies the public certificate name
`smtp.games.lab.bingo`, and authenticates as `games@games.lab.bingo`.
There is no public SMTP Service, ingress or tunnel route. SMTP submission
requires STARTTLS and authentication even if NetworkPolicy is not enforced.

## Ownership and rebuild order

1. Restore local-path storage, cert-manager and the existing
   `letsencrypt-cloudflare` ClusterIssuer, then the Bitwarden operator and its
   `argocd-system/bw-auth-token`. The namespace bootstrap copies and periodically
   refreshes only that token; controller retries handle partial startup failure.
2. Build/publish the public `ghcr.io/bingops-com/postfix:1.0.0` package through
   LabOps CI. The image pins upstream v5.1.0 Alpine by digest, installs current
   security updates, and removes the unused OAuth virtual environment. Local
   Cyrus SASL authentication remains enabled. CI tests and scans the exact image
   before pushing; HIGH/CRITICAL findings block publication. Bump
   `docker/postfix/VERSION` for a new production build and update the image
   reference together. The package owner must set GHCR visibility to public;
   verify an anonymous pull before synchronization.
3. Recover the existing `games-smtp-password` and `games-dkim-private-key`
   entries from Bitwarden Secrets Manager's `labprod` project. Their real UUIDs
   are tracked in [`smtp-secret.yaml`](smtp-secret.yaml) and
   [`dkim-secret.yaml`](dkim-secret.yaml); the password mapping is also tracked
   in Games. If replacement is necessary, the operator creates two independent
   secrets: a random SMTP password (at least 32 bytes, base64url;
   no colon, comma or whitespace), and the PEM RSA DKIM private key (2048 bits or
   more). The machine account needs read access; only the operator needs write
   access. Neither value belongs in Git, command arguments, chat or logs.
4. Configure the mappings with the two real UUIDs. The same password UUID maps to
   `games/games-smtp` and `mail/mail-smtp`; the private key maps only to
   `mail/mail-dkim`, key `games.lab.bingo.private`. No zero UUID is deployed.
   Follow [the Games helper](../../../workloads/games/configure-smtp.py):

```sh
python3 apps/workloads/games/configure-smtp.py SMTP_PASSWORD_UUID DKIM_PRIVATE_KEY_UUID
```

5. Supply the actual public IPv4 address used by cluster SMTP egress and the
   DKIM **public** key. On a trusted operator machine, generate the private key
   into a protected temporary directory, import it into Bitwarden through its
   secure UI, derive the public key, then securely remove the temporary private
   file. The following commands write files, never private material to stdout:

```sh
umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out games.lab.bingo.private
openssl pkey -in games.lab.bingo.private -pubout -outform DER -out games.lab.bingo.public.der
openssl base64 -A -in games.lab.bingo.public.der -out games.lab.bingo.public.txt
python3 apps/workloads/games/configure-smtp.py SMTP_PASSWORD_UUID DKIM_PRIVATE_KEY_UUID --egress-ip ACTUAL_PUBLIC_IPV4 --dkim-public-key-file games.lab.bingo.public.txt
```

The helper commits no private key or password. It validates nonzero UUIDs,
public IPv4 and an RSA public key, then writes the mappings and public metadata
in `terraform/cloudflare/games-mail-settings.tf`. Review and commit the
generated files. Until these inputs exist, missing Secret references prevent
the relay from starting and null DNS settings create no guessed records.

6. Review/apply Cloudflare DNS separately: unproxied `smtp.games.lab.bingo` A
   and SPF, `games1._domainkey.games.lab.bingo` DKIM, and
   `_dmarc.games.lab.bingo` DMARC. None conflicts with the website CNAME.
   DMARC starts at `p=none`; tighten after confirming alignment and delivery.
   DNS-01 can issue the SMTP certificate without exposing port 587.
7. After explicit deployment authorization, sync `mail-labprod`, then Games.
   Both Applications remain manual. Confirm the certificate, secrets and relay
   health before enabling real authentication mail.

## TLS, authentication and rotation

The certificate is generated and renewed by cert-manager. The wrapper detects
a public certificate change and reloads Postfix; projected Secret mounts use no
subPath. Games never disables certificate validation. Its
`GAMES_SMTP_SERVER_NAME` identifies the certificate while the TCP connection
stays inside the cluster.

The relay restriction is `permit_sasl_authenticated,reject`; private addresses
are not granted anonymous relay access. AUTH is hidden until TLS. Root is needed
by the multi-process upstream image, which drops privileges for Postfix/OpenDKIM.
The namespace uses baseline Pod Security, restricted capabilities, seccomp,
no service-account token and no privilege escalation.

For password rotation, update the same Bitwarden secret, wait for both mappings,
then restart Postfix and Games during an authorized maintenance window. Each
consumer loads environment credentials at startup. Test delivery before ending
the window. If lost, generate a new password; both consumers share the same
UUID so reconstruction requires no manual secret copy.

For DKIM rotation, generate/store a new key, publish its public DNS under a new
selector, update `DKIM_SELECTOR` and the mapping together, and restart the relay.
Keep the old public record for at least the maximum queue lifetime before
removing it. Recover lost private keys from Bitwarden or rotate them; Git
cannot recover secret values. TLS keys are generated state and reissued by
cert-manager after reconstruction.

## Queue, delivery and recovery

The 1 GiB `relay-spool` PVC survives pod replacement and is protected against
Argo CD pruning/deletion. Maximum queue/bounce lifetime is one hour, to limit
delivery of expired password-reset links. The queue contains sensitive mail
bodies; it is not exported to Git or logs. It is disposable after node/disk loss:
restore accounts from CNPG and request a fresh link rather than restoring
expired queued authentication mail. This is not a highly available mail server.

Direct delivery requires actual outbound TCP/25, an egress IP with usable
reputation, and provider-managed reverse DNS matching `smtp.games.lab.bingo`.
These are external prerequisites owned by the internet provider/operator;
Cloudflare cannot configure PTR for the provider's address. Verify them from
the cluster's egress path before public use. The configuration does not claim
that residential delivery will work. If direct delivery is rejected, Postfix
can keep its role and forward through an authenticated smarthost; model its
credential and SPF change in Git/Bitwarden before use.

## Verification

Offline and isolated checks (no cluster changes or external mail):

```sh
kubectl kustomize apps/platform/mail/labprod >/dev/null
docker build -t labops-postfix:check docker/postfix
python3 apps/platform/mail/tests/check.py labops-postfix:check
trivy image --image-src docker --scanners vuln --severity HIGH,CRITICAL --exit-code 1 labops-postfix:check
terraform -chdir=terraform/cloudflare fmt -check
```

The integration test uses synthetic credentials and keys on an internal Docker
network. It verifies plaintext rejection, certificate-name checking,
unauthenticated/wrong-password rejection, authenticated DKIM signing, certificate
renewal reload and queue survival after container replacement. No recipient
mail server is contacted; temporary containers, volumes and keys are removed.

Read-only checks after an authorized deployment:

```sh
kubectl --context labprod get deployment,pod,pvc,certificate,bitwardensecret -n mail
dig +short A smtp.games.lab.bingo
dig +short TXT smtp.games.lab.bingo
dig +short TXT games1._domainkey.games.lab.bingo
dig +short TXT _dmarc.games.lab.bingo
```

Send confirmation and recovery to a controlled test mailbox through Games,
then verify SPF/DKIM/DMARC in Authentication-Results and actual receipt. Never
print Secrets, private keys, queued messages or reset links. An actual delivery
test and NetworkPolicy enforcement proof remain required before production.

Reconstruction is documented here; UUIDs/public DNS live in Git and secret
recovery in Bitwarden. Bootstrap and the helper are idempotent, ownership and
dependency order are explicit, and verification does not disclose secrets.
The UUIDs are configured. Public mail DNS metadata remains unset; machine-account
access to both entries and secret values still need runtime validation without
disclosure. Direct delivery, policy enforcement and production acceptance remain
required before public use.
