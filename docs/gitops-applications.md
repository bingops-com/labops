# Deliver an application through GitOps

This is the operator runbook for adding a workload to `labtest` and `labprod`.
The workflow keeps one shared base and explicit cluster overlays. Git-backed
Applications on both clusters follow `master` as their stable state. Feature
branches are integrated temporarily into `labtest` through `deploy.sh`.

## Ownership and naming

For an application named `<app>`, Git owns these resources:

| Path | Purpose |
| --- | --- |
| `apps/workloads/<app>/base` | Namespace, Deployment, Service and shared policy |
| `apps/workloads/<app>/clusters/labtest` | Test hostname, public DNS-01 certificate and test image |
| `apps/workloads/<app>/clusters/labprod` | Production hostname, public CA and immutable image |
| `apps/gitops/clusters/labtest/<app>.yaml` | Permanent test Application following `master` |
| `apps/gitops/clusters/labprod/<app>.yaml` | Permanent production Argo CD Application |

The promotion order is: push `feature/*`, deploy that branch temporarily to
`labtest`, validate it, restore the override, then merge the reviewed feature
into `master`. Do not merge an unvalidated feature into `master`.

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

- `labtest`: `<app>.test.lab.bingo`, issuer `letsencrypt-cloudflare`, and the local/Tailscale
  allowlist when the service is private;
- `labprod`: `<app>.lab.bingo`, issuer `letsencrypt-cloudflare`, and an
  immutable image tag or digest;
- never use `latest` for a promoted production image;
- remove a test-only allowlist explicitly in production only when the service
  is intended to be public.

Kubernetes secret values never belong in Git. Declare `labtest` credentials as
BitwardenSecret UUID mappings and keep their values in the Bitwarden `labtest`
project. `labprod` remains temporarily on SealedSecrets until its migration is
validated. Plaintext, machine tokens, kubeconfigs, Terraform state and generated
certificates never belong in Git.

## 2. Add both environment Applications

Copy the structure of `apps/gitops/clusters/labtest/portfolio.yaml`, then set:

- `metadata.name` to `<app>-labtest`;
- `spec.source.targetRevision` to `master`;
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

## 4. Iterate from a feature branch

Push the feature branch, then point the existing test Application at it. This
is an intentional live labtest operation, but it does not merge or deploy to
production:

```sh
git push --set-upstream origin feature/my-change
./hacks/deploy.sh diff test --app <app>
./hacks/deploy.sh deploy test --app <app>
```

Each later push to the same branch reconciles automatically. Inspect the active
revision at any time, then restore the integration branch when finished:

```sh
./hacks/deploy.sh status test --app <app>
./hacks/deploy.sh restore test --app <app>
```

`--app` is optional for every subcommand. Omit it to diff, deploy, inspect or
restore every Git-backed Application in the selected environment. Add
`--revision <branch>` to `diff` or `deploy` to override the current branch.
`diff` shows only the live-to-desired Kubernetes changes, with object paths,
green additions and red deletions. `deploy` repeats that preview and requires
explicit confirmation before changing any Application revision.

Only one revision can occupy an application's shared labtest namespace at a
time. Coordinate the override with other operators and do not use it for
platform Applications. The root ignores only child `targetRevision` drift;
repository, path, namespace, policy and all other fields remain self-healed.
Enabling this workflow on an existing cluster requires one reviewed reapply of
the imperative root after this policy reaches `master`:

```sh
kubectl --context labtest apply -f apps/gitops/bootstrap/labtest.yaml
```

This updates only the root Application policy; subsequent feature overrides use
the helper and do not require another bootstrap apply.

## 5. Validate on labtest and merge to master

Commit and push the feature branch, use `deploy.sh` to integrate it temporarily
into `labtest`, then verify that `<app>-labtest` is `Synced` and `Healthy` and
test `https://<app>.test.lab.bingo` from the LAN or Tailscale. Verify it with
the normal system trust store and without `-k`; DNS-01 certificates do not make
the private hostname publicly reachable. Do not display private keys or Secret
content.

After validation, restore labtest to its declared baseline and open a reviewed
pull request from the feature branch to `master`:

```sh
./hacks/deploy.sh restore test --app <app>
```

Merging into `master` authorizes normal GitOps reconciliation on both clusters.

Platform changes, including DNS, cert-manager, Traefik and Argo CD itself, are
tested through the same branch. Apply a required Terraform test-side change
only after reviewing its plan; a Git merge does not authorize Terraform apply.

## 6. Verify production

Pin the production overlay to the exact image tag or digest validated on
`labtest` before merging the reviewed feature into `master`.
`<app>-labprod` follows `master`; the merge is the production deployment
authorization and must happen only after the feature override passed labtest.

Verify that the Application, Deployment, Service, Ingress, Certificate and
CertificateRequest are healthy. For a public application, verify HTTPS from
outside the lab. For a private application, verify that an allowed client can
connect and a client outside the allowlist cannot.

An exceptional manual production test displays the applicable diff first and
requires an exact confirmation. Test deployments use the same safety gate. The
current branch is used when no revision is supplied:

```sh
./hacks/deploy.sh diff prod --app <app>
./hacks/deploy.sh deploy prod --app <app>
./hacks/deploy.sh status prod --app <app>
./hacks/deploy.sh restore prod --app <app>
```

The override is temporary and auditable on the child Application. Always run
`restore prod` after the test; normal production delivery remains a reviewed
merge into `master` after labtest validation.

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

For a feature test failure, restore labtest to `master`, correct the feature
branch and redeploy it through the helper. For a production failure, revert on
`master`; both clusters then reconcile the previous declared state. Keep the
failed image immutable for post-incident analysis.

## Remove an application

Removal is destructive and must be reviewed for persistent data first. Identify
PVCs, databases, DNS records, tunnel routes, SealedSecrets and external
credentials owned by the application. Back up data according to its owning
runbook.

Test the removal from a feature branch with `deploy.sh`, including its pruning
impact, before merging the removal of both Applications into `master`. Delete
the shared workload directory only when neither environment references it. Remove
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
