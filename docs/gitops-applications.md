# Deliver an application through GitOps

This is the operator runbook for adding a workload to `labtest` and `labprod`.
The workflow keeps one shared base, explicit cluster overlays, an ephemeral
feature preview on `labtest`, and a permanent production Application following
`master` on `labprod`.

## Ownership and naming

For an application named `<app>`, Git owns these resources:

| Path | Purpose |
| --- | --- |
| `apps/workloads/<app>/base` | Namespace, Deployment, Service and shared policy |
| `apps/workloads/<app>/clusters/labtest` | Test hostname, local CA and preview image |
| `apps/workloads/<app>/clusters/labprod` | Production hostname, public CA and immutable image |
| `apps/gitops/clusters/labprod/<app>.yaml` | Permanent production Argo CD Application |

Do not create a permanent workload Application under the `labtest` root. The
current workflow deliberately activates one feature branch at a time with
`hacks/gitops-preview.sh`. Platform services continue to follow `master`.

Use `<app>.test.bingops.com` on test and `<app>.prod.bingops.com` in production
unless the application has an explicitly owned top-level name. Test DNS is a
private wildcard. Production's `*.prod.bingops.com` DNS and Cloudflare Tunnel
route already forward to Traefik, so ordinary applications need no individual
DNS record or tunnel rule. A name such as `<app>.bingops.com` is exceptional:
declare its DNS and tunnel route in the Cloudflare Terraform/application values
and document the ownership change.

## 1. Create the workload manifests

Create the base with a Namespace, Deployment, Service and Ingress. Use the
application name consistently for the namespace, workload labels, Service and
Ingress. The base Ingress must use Traefik and refer to a placeholder hostname
such as `<app>.invalid`; each overlay must replace every rule and TLS hostname.

Keep environment differences in the overlays:

- `labtest`: `<app>.test.bingops.com`, issuer `labtest-ca`, and the local/Tailscale
  allowlist when the service is private;
- `labprod`: `<app>.prod.bingops.com`, issuer `letsencrypt-cloudflare`, and an
  immutable image tag or digest;
- never use `latest` for a promoted production image;
- remove a test-only allowlist explicitly in production only when the service
  is intended to be public.

Kubernetes Secrets committed to Git must be SealedSecrets. Seal the same input
independently for each cluster because their sealing keys differ. Plaintext,
kubeconfigs, Terraform state and generated certificates never belong in Git.

## 2. Add the production Application

Copy the structure of `apps/gitops/clusters/labprod/portfolio.yaml`, then set:

- `metadata.name` to `<app>-labprod`;
- `spec.source.targetRevision` to `master`;
- `spec.source.path` to `apps/workloads/<app>/clusters/labprod`;
- `spec.destination.namespace` to `<app>`;
- sync wave `0`, automated pruning and self-healing.

Add `<app>.yaml` to `apps/gitops/clusters/labprod/kustomization.yaml`. Do not add
the workload to the `labtest` kustomization.

## 3. Validate locally

Set the application name once for the commands below:

```sh
APP_NAME=myapp
```

Render both overlays without contacting a cluster:

```sh
kubectl kustomize "apps/workloads/${APP_NAME}/clusters/labtest" >/dev/null
```

```sh
kubectl kustomize "apps/workloads/${APP_NAME}/clusters/labprod" >/dev/null
```

Render both app-of-apps definitions:

```sh
kubectl kustomize apps/gitops/clusters/labtest >/dev/null
```

```sh
kubectl kustomize apps/gitops/clusters/labprod >/dev/null
```

Run `yamllint` on the new first-party YAML when it is available. Inspect the
rendered image, hostname, issuer, namespace and allowlist before committing.
These checks are offline and do not authorize an apply or synchronization.

## 4. Preview on labtest

Commit the manifests on a feature branch and push that branch. Then activate
the preview from the repository root:

```sh
FEATURE_BRANCH=feature/myapp
```

```sh
./hacks/gitops-preview.sh up "${APP_NAME}" "${FEATURE_BRANCH}"
```

The helper creates or updates `<app>-preview` in `argocd-system`. The
Application follows the remote feature branch directly and reconciles
`apps/workloads/<app>/clusters/labtest`. Re-running the command switches the
active revision. Only one branch can own the stable test hostname at a time.

Verify in Argo CD that `<app>-preview` is `Synced` and `Healthy`, then test
`https://<app>.test.bingops.com` from the LAN or Tailscale. The client must trust
the labtest root CA. Verify the certificate hostname without displaying any
private key or Secret content.

## 5. Promote to production

Pin the production overlay to the exact tested image tag or digest. Merge the
feature branch into `master` through the normal repository review process.
`<app>-labprod` follows only `master`; automated sync then deploys the committed
production overlay. A push can trigger deployment, so it must be intentional.

Verify that the Application, Deployment, Service, Ingress, Certificate and
CertificateRequest are healthy. For a public application, verify HTTPS from
outside the lab. For a private application, verify that an allowed client can
connect and a client outside the allowlist cannot.

After promotion, remove the test preview when it is no longer needed:

```sh
./hacks/gitops-preview.sh down "${APP_NAME}"
```

This command removes the preview Application and prunes the resources it owns.

## Rollback

Rollback by reverting the Git commit that changed the production overlay or by
committing the previously known-good immutable image reference. Do not use an
ad-hoc `kubectl set image`, Argo CD parameter override or manual Helm upgrade;
self-healing would overwrite it and Git would no longer describe recovery.

Validate the revert locally, review it, then merge it to `master`. Argo CD
reconciles the previous declared state. Keep the failed image immutable for
post-incident analysis.

## Remove an application

Removal is destructive and must be reviewed for persistent data first. Identify
PVCs, databases, DNS records, tunnel routes, SealedSecrets and external
credentials owned by the application. Back up data according to its owning
runbook.

Remove the production Application from the labprod kustomization and delete its
manifest and workload directory in the same reviewed change. Remove exceptional
DNS or tunnel declarations only if no other consumer uses them. Argo CD pruning
removes managed Kubernetes objects after the change reaches `master`; it must
not be used as an implicit data-retention policy.

## Reconstruction checklist

- A new operator can reconstruct the workload from the base, overlays and
  production Application without chat history.
- Immutable images and sealed credentials are available from their owning
  registries and encrypted recovery locations.
- Reapplying the same Git revision is idempotent after partial failure.
- Argo CD owns Kubernetes workloads; Terraform owns external DNS and tunnels.
- Health, DNS and TLS checks do not reveal credential or private-key material.
