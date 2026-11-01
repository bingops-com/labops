# Public service directory

`https://lab.bingo` is the public, read-only entry point to the lab's web
services. The private operational portal now lives at
`https://portal.lab.bingo`; see [its runbook](../portal/README.md).

## Ownership and content

`hub-labprod` reconciles `clusters/labprod` from LabOps `master`. The entire
site is in `base/site`: HTML is the service catalogue, CSS owns presentation,
and optional JavaScript adds search, access filters and an explicit theme
preference. All service links work without JavaScript. Light is the initial
theme; a visitor can save a dark preference in browser local storage.

The visual direction uses pearl `#eef1f6`, graphite `#202938`, navy `#17356d`,
teal `#126b66`, violet `#6852aa` and a cool border `#d7dfea`. Onest identifies
services and titles; IBM Plex Sans handles descriptions and controls. Fonts
and their OFL licences are served locally. The single navy quick-access panel
highlights Notes and Portal; the catalogue uses quiet, grouped rows rather
than repeated promotional cards. Search and access filters drive interaction;
motion is limited to the initial reveal and respects reduced-motion settings.
The initial plan of equal application tiles was replaced by these rows to
make a fourteen-service directory quicker to scan on desktop and mobile.

Edit the actual links, `data-access`, descriptions and searchable
`data-keywords` together. Access classifications are descriptive, not an
authorization mechanism: public services can require their own account, SSO
services use LabOps identity, and private services require LAN/Tailscale.
The directory does not contact linked services, test VPN connectivity, expose
health metrics or promise current availability; it links to Status instead.

Caddy 2.11.7 is pinned by digest. It serves ConfigMaps on port 8080 as UID 1000
with a read-only root filesystem, dropped capabilities and no ServiceAccount
token. Hashed ConfigMap names roll the Deployment when content changes.
The official Caddy binary carries a privileged-port file capability. Startup
copies it without that extended attribute into the bounded temporary volume,
then executes the copy on unprivileged port 8080; no capability is added back.
CI checks this with the same nonroot, read-only and capability-free settings.
The static site uses no CDN, analytics, third-party fonts or browser API calls.
The Content Security Policy permits only local scripts/styles/fonts/images;
the Caddy admin API is disabled. `/healthz` is a simple readiness endpoint.

## Address, access and state

Terraform `cloudflare_record.lab_tunnel_routes["lab.bingo"]` owns the new,
proxied apex CNAME, explicitly using `@` as its record name. Existing tunnel
identity and credentials remain unchanged. Argo CD owns the Cloudflare Tunnel
route to `hub.hub.svc.cluster.local:80`, the separate public Traefik Ingress
and its DNS-01 certificate. The private DNS apex still resolves to the
Traefik VIP, which now serves this same directory. A dedicated private
`portal.lab.bingo` CoreDNS zone resolves the retained portal to that VIP.
Tailscale's existing `lab.bingo` split-DNS parent covers both names.

There is no public DNS record or tunnel route for `portal.lab.bingo`. Its
Traefik LAN/tailnet allowlist remains enabled; its OIDC editing callback and
runtime public URL move together. No private portal API, Kubernetes credential,
Prometheus response or saved layout is copied into the public site. Only the
requested service names, public-facing URLs and descriptions are published.

Database, persistent data, application SSO, privileged group and backup are
not applicable to the directory: there is no writable application or PVC.
Git contains all content and licences; temporary Caddy volumes are disposable.
Browser theme preference is intentionally disposable. Rebuild requires no new
external input. Existing Cloudflare/cert-manager credentials are owned,
recovered and rotated through [the Cloudflare runbook](../../../docs/infrastructure/cloudflare.md)
and Bitwarden bootstrap. The pinned public Docker Hub Caddy image is the only
runtime artifact dependency. Reconciliation after a partial failure is
idempotent and does not mutate portal data.

## Rebuild and cutover

Reconcile the existing private DNS, Traefik, cert-manager, Authentik and tunnel
platform, then the hub and portal Applications. Wait for hub readiness and
the certificate before creating the public apex CNAME through a fresh, saved,
reviewed Terraform plan using the existing state. Targeting only the new apex
record must show one create and no unrelated changes. Do not initialize an
independent state or point the public tunnel at the private portal Service.
The normal GitOps cutover briefly changes the portal origin while its new
certificate and Authentik blueprint reconcile; existing editors sign in again.
`portal-data` and saved layouts remain intact throughout.

Roll back via a coordinated Git revert and Terraform plan: retire the public
apex DNS/tunnel route before restoring a private portal on that hostname.
Never expose the former portal through the public tunnel during rollback.
The directory itself can be rebuilt or rolled back without restoring storage.

## Verification

```sh
kubectl kustomize apps/workloads/hub/clusters/labprod >/dev/null
python3 -m unittest discover -s apps/workloads/hub/tests -v
kubectl --context labprod -n argocd-system get application hub-labprod portal-labprod
kubectl --context labprod -n hub get deployment,ingress,certificate
dig @1.1.1.1 lab.bingo A
dig @192.168.10.160 portal.lab.bingo A
curl --fail --silent --output /dev/null --write-out '%{http_code}\n' https://lab.bingo/healthz
# Only from LAN or Tailscale:
curl --fail --silent --output /dev/null --write-out '%{http_code}\n' https://portal.lab.bingo/healthz
```

Require Synced/Healthy Applications, ready TLS certificates, public directory
HTTP 200 and portal health on the private route. Public resolvers must not
resolve the portal. Verify the native portal login redirects back to
`https://portal.lab.bingo/auth/callback`. Existing notes and other service SSO
policies remain owned by their applications. Test keyboard search/filter/reset,
no-JavaScript links, light/dark mode and widths 320, 390, 768 and 1440 px.
Never print session cookies, private layouts or credential-bearing responses.
