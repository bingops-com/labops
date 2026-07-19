# Deliver an application through GitOps

This is the operator runbook for adding a workload to `labtest` and `labprod`.
The workflow keeps one shared base and explicit cluster overlays. Git-backed
Applications on `labtest` follow `develop`; production Applications on
`labprod` follow `master`.

## Ownership and naming

For an application named `<app>`, Git owns these resources:

| Path | Purpose |
| --- | --- |
| `apps/workloads/<app>/base` | Namespace, Deployment, Service and shared policy |
| `apps/workloads/<app>/clusters/labtest` | Test hostname, local CA and test image |
| `apps/workloads/<app>/clusters/labprod` | Production hostname, public CA and immutable image |
| `apps/gitops/clusters/labtest/<app>.yaml` | Permanent test Application following `develop` |
| `apps/gitops/clusters/labprod/<app>.yaml` | Permanent production Argo CD Application |

The branch promotion order is `feature/*` to `develop`, validate on `labtest`,
then `develop` to `master`. Do not point a labtest Application at `master` or a
labprod Application at `develop`.

Use `<app>.test.lab.bingo` on test and `<app>.lab.bingo` in production. Test DNS
is a private wildcard. Production intentionally has no wildcard: every public
hostname must be added to `local.lab_tunnel_hostnames` in
`terraform/cloudflare/locals.tf` and to the cloudflared ingress list in
`apps/cloudflare/bingops/values.yaml`. This prevents a newly created Ingress,
especially an administrative one, from becoming public accidentally. The
portfolio is exceptional because it also owns `bingops.com` and
`www.bingops.com`.

The base tunnel and its `bingops.com` aliases are declared in the tracked
`terraform/cloudflare/routes.auto.tfvars`; credentials and identifiers remain
in ignored tfvars. Do not put hostnames back into a sensitive operator file.

## 1. Create the workload manifests

Create the base with a Namespace, Deployment, Service and Ingress. Use the
application name consistently for the namespace, workload labels, Service and
Ingress. The base Ingress must use Traefik and refer to a placeholder hostname
such as `<app>.invalid`; each overlay must replace every rule and TLS hostname.

Keep environment differences in the overlays:

- `labtest`: `<app>.test.lab.bingo`, issuer `labtest-ca`, and the local/Tailscale
  allowlist when the service is private;
- `labprod`: `<app>.lab.bingo`, issuer `letsencrypt-cloudflare`, and an
  immutable image tag or digest;
- never use `latest` for a promoted production image;
- remove a test-only allowlist explicitly in production only when the service
  is intended to be public.

Kubernetes Secrets committed to Git must be SealedSecrets. Seal the same input
independently for each cluster because their sealing keys differ. Plaintext,
kubeconfigs, Terraform state and generated certificates never belong in Git.

## 2. Add both environment Applications

Copy the structure of `apps/gitops/clusters/labtest/portfolio.yaml`, then set:

- `metadata.name` to `<app>-labtest`;
- `spec.source.targetRevision` to `develop`;
- `spec.source.path` to `apps/workloads/<app>/clusters/labtest`;
- `spec.destination.namespace` to `<app>`;
- sync wave `0`, automated pruning and self-healing.

Add `<app>.yaml` to `apps/gitops/clusters/labtest/kustomization.yaml`.

Copy the structure of `apps/gitops/clusters/labprod/portfolio.yaml`, then set:

- `metadata.name` to `<app>-labprod`;
- `spec.source.targetRevision` to `master`;
- `spec.source.path` to `apps/workloads/<app>/clusters/labprod`;
- `spec.destination.namespace` to `<app>`;
- sync wave `0`, automated pruning and self-healing.

Add `<app>.yaml` to `apps/gitops/clusters/labprod/kustomization.yaml`.

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

## 4. Promote to develop and validate on labtest

Commit the manifests on a feature branch, push it, and open a reviewed pull
request targeting `develop`. Merging that PR is the deployment authorization
for `labtest`: its root and Git-backed child Applications automatically
reconcile the new `develop` revision.

Verify in Argo CD that `<app>-labtest` is `Synced` and `Healthy`, then test
`https://<app>.test.lab.bingo` from the LAN or Tailscale. The client must trust
the labtest root CA. Verify the certificate hostname without displaying any
private key or Secret content.

Platform changes, including DNS, cert-manager, Traefik and Argo CD itself, are
tested through the same branch. Apply a required Terraform test-side change
only after reviewing its plan; a Git merge does not authorize Terraform apply.

## 5. Promote to production

Pin the production overlay to the exact image tag or digest validated on
`labtest`. Open a reviewed pull request from `develop` to `master`.
`<app>-labprod` follows only `master`; merging that PR is the production
deployment authorization. Direct feature-to-master promotion bypasses the test
gate and is not part of this workflow.

Verify that the Application, Deployment, Service, Ingress, Certificate and
CertificateRequest are healthy. For a public application, verify HTTPS from
outside the lab. For a private application, verify that an allowed client can
connect and a client outside the allowlist cannot.

For a new public production application, the promotion must include both the
explicit Cloudflare DNS hostname and the matching tunnel ingress rule. For a
private application such as Argo CD, omit both declarations and add only the
required exact split-DNS route. Cloudflare and Terraform must never infer
public exposure from the presence of a Kubernetes Ingress.

## Rollback

Rollback by reverting the Git commit that changed the production overlay or by
committing the previously known-good immutable image reference. Do not use an
ad-hoc `kubectl set image`, Argo CD parameter override or manual Helm upgrade;
self-healing would overwrite it and Git would no longer describe recovery.

For a test failure, revert on `develop` and validate labtest again. For a
production failure, revert on `master`, then merge the same correction back to
`develop` if it is not already present. Argo CD reconciles the previous
declared state. Keep the failed image immutable for post-incident analysis.

## Remove an application

Removal is destructive and must be reviewed for persistent data first. Identify
PVCs, databases, DNS records, tunnel routes, SealedSecrets and external
credentials owned by the application. Back up data according to its owning
runbook.

Remove the test Application from the labtest kustomization through `develop`
first. After validation, promote the removal to `master`, where the production
Application is removed from the labprod kustomization. Delete the shared
workload directory only when neither environment still references it. Remove
exceptional DNS or tunnel declarations only if no other consumer uses them.
Argo CD pruning must not be used as an implicit data-retention policy.

## Reconstruction checklist

- A new operator can reconstruct the workload from the base, overlays and
  production Application without chat history.
- Immutable images and sealed credentials are available from their owning
  registries and encrypted recovery locations.
- Reapplying the same Git revision is idempotent after partial failure.
- Argo CD owns Kubernetes workloads; Terraform owns external DNS and tunnels.
- Health, DNS and TLS checks do not reveal credential or private-key material.
