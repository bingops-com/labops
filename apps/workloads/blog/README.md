# BingOps blog

The public, read-only static site is served by Caddy at
`https://blog.bingops.com`. Argo CD owns `blog-labprod`, rendering the local
`charts/blog` chart with `clusters/labprod/values.yaml`. The Deployment and
ClusterIP Service are both named `blog` in namespace `bingops`, preserving the
existing Cloudflare Tunnel destination `http://blog.bingops.svc.cluster.local:80`.
Terraform owns DNS and the tunnel infrastructure; Argo owns the tunnel routes.
Cloudflare terminates public TLS, so this service needs no Kubernetes Ingress
or additional certificate. See the [Cloudflare runbook](../../../docs/infrastructure/cloudflare.md)
for shared credential recovery and DNS ownership.

## Recovery and dependencies

- Database: none; Caddy serves files embedded in the image.
- Authentik: not applicable; public articles have no login or privileged UI.
- Durable data: none; no PVC, runtime edits or application credential. Pod
  replacement and repeated reconciliation are safe after partial failure.
- Declarative inputs: the chart, production values, immutable image digest,
  Application and existing tunnel route are tracked in Git. The production
  image is Linux/amd64; the node selector keeps it on compatible nodes.
- External artifact: the public GHCR package `bingops-com/blog`, owned by the
  GitHub organization maintainers. Preserve the pinned digest in GHCR. Pulling
  it needs no credential; publishing a replacement needs package-write access
  through the existing image workflow's GitHub token. The registry artifact
  is the recovery source for the deployed site.
- External source: maintainers own the public
  [`bingops-com/blog.bingops.com`](https://github.com/bingops-com/blog.bingops.com)
  repository. Recover source through that repository or an operator-maintained
  Git mirror. The [image build](../../../docker/blog/README.md) currently clones
  its moving `master` branch and installs dependencies at build time. If the
  pinned artifact is lost, rebuilding is not guaranteed to reproduce identical
  content: publish and review a replacement digest before reconciliation.
  No application secret needs creating or rotating.

Restore the shared DNS/tunnel and its Bitwarden-delivered credential first,
then reconcile `blog-labprod` once its public image exists. Restore Gatus and
Status afterward to expose the blog's availability. Neither a new database nor
data restoration is needed. Shared credentials remain owned by the LabOps
operator under the linked Cloudflare runbook.

## Validation and incident recovery

Offline checks do not contact the cluster or download chart dependencies:

```sh
helm lint charts/blog -f apps/workloads/blog/clusters/labprod/values.yaml
helm template blog charts/blog --namespace bingops -f apps/workloads/blog/clusters/labprod/values.yaml >/dev/null
kubectl kustomize apps/gitops/clusters/labprod >/dev/null
```

After an authorized deployment, verify status without reading Secrets:

```sh
kubectl --context labprod -n argocd-system get application blog-labprod
kubectl --context labprod -n bingops rollout status deployment/blog --timeout=120s
kubectl --context labprod -n bingops get deployment,service,endpointslice -l app=blog
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' https://blog.bingops.com
```

Expected results are a Synced/Healthy Application, a ready Deployment, a
Service endpoint and HTTP 200. Gatus checks the public HTTPS URL every minute;
Status lists it as `Blog`.

A public HTTP 502 with a healthy tunnel can mean its origin is missing. On
2026-10-28, the existing tunnel still targeted `blog.bingops`, but neither its
Service nor Deployment existed and no blog Application was included in the
GitOps root. Reconcile the tracked Application to restore that origin; changing
DNS or restarting the tunnel does not recreate it. Normal delivery is a
reviewed merge to `master`; editing local manifests alone does not restore the
live site. Never remove the workload while leaving its public tunnel route.
