# Ghost retirement and retained data

Ghost is retired from `labprod`. The game Deployment, Service, Ingress and
NetworkPolicy are absent from desired state. Its Cloudflare Tunnel route,
public DNS declaration, Gatus endpoint, status-page entry and optional Arcade
credential access are removed. `ghost.lab.bingo` must no longer serve the game.

The `ghost-labprod` Application remains active solely to reconcile retained
recovery data from this LabOps directory. It no longer fetches the Ghost chart,
image or source repository. `bingops-com/ghost` is private; GitHub organization
owners manage visibility and collaborator access outside Kubernetes. No GitHub
credential is needed by this retained-data Application. The GHCR package is a
separate resource: repository privacy does not authorize deleting the package
or changing its existing visibility.

## Retention and ownership

LabOps directly owns `clusters/labprod/postgresql.yaml`: the existing
`ghost/ghost-postgresql` CloudNativePG Cluster, its daily ScheduledBackup and
PodMonitor. PostgreSQL stays running for recovery and continuing backups; this
retirement does not reclaim its CPU, memory or 1 GiB `local-path` volume. The
namespace and Cluster explicitly disable Argo pruning/deletion. Never delete
the namespace, Cluster, PVC, credentials or R2 archives as part of retiring the
game; final data destruction requires separate authorization.

The unchanged database and owner are `ghost`. Existing CNPG-generated
credentials stay in the namespace; no password is exported or committed. Its
ObjectStore still targets `s3://bingops-cnpg-labprod/ghost` with archive generation
`ghost-postgresql-g1`, continuous WAL archival, daily base backups at 03:45 and
14-day rolling retention. The Bitwarden token synchronizer and existing
bucket-scoped R2 mapping remain necessary for that backup pipeline. Keeping
daily backups prevents retirement from aging out the usable recovery window.

Non-Git inputs are the existing bucket-scoped R2 key, Bitwarden machine token,
CNPG-generated database credential, volume contents and Barman objects.
Creation, minimum permissions, storage, recovery and rotation of the shared
credentials are owned by the LabOps operator in the
[CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md). The namespace
bootstrap and Bitwarden mappings retry idempotently. The game source is
retained in the private GitHub repository; organization owners restore access
through GitHub membership rather than introducing a cluster credential.

## Delivery and DNS

A reviewed LabOps merge replaces the multi-source chart Application with a
single local Kustomize source. Argo prunes only application and Arcade-access
resources omitted from the new manifests, and continues managing the database
under the same name. Keep this Application in the GitOps root: removing the
Application alone could orphan a still-running game.

Argo CD owns tunnel, Gatus and status-page updates. Terraform separately owns
`cloudflare_record.lab_tunnel_routes["ghost.lab.bingo"]`; removing it from
`terraform/cloudflare/locals.tf` requires a fresh saved plan against the existing
state. Inspect a plan targeted at that exact record and apply only a deletion
of that record, with no tunnel, bucket or unrelated DNS changes. When using an
isolated checkout, reuse the existing provider inputs, provider cache and
explicit state path as documented in the
[Cloudflare runbook](../../../docs/infrastructure/cloudflare.md). Do not create
a second state or use an old saved plan. Removal is idempotent: skip a second
apply if a fresh plan has no changes.

## Verification

Offline:

```sh
kubectl kustomize apps/workloads/ghost/clusters/labprod >/dev/null
kubectl kustomize apps/gitops/clusters/labprod >/dev/null
terraform fmt -check terraform/cloudflare
```

After reconciliation, inspect only resource status (no Secret data):

```sh
kubectl --context labprod -n argocd-system get application ghost-labprod
kubectl --context labprod -n ghost get deployment,service,ingress,networkpolicy
kubectl --context labprod -n ghost get cluster,pvc,scheduledbackup,backup
kubectl --context labprod -n ghost get cluster ghost-postgresql -o jsonpath='{.status.conditions}'
gh repo view bingops-com/ghost --json nameWithOwner,visibility
curl --silent --output /dev/null --write-out '%{http_code}\n' https://ghost.lab.bingo/healthz
```

The game Deployment/Service/Ingress must be absent; CNPG services remain. The
Cluster and PVC retain their identities, WAL archival remains successful and
one fresh base backup completes. The public URL must not return the game or
its successful health endpoint. Verify authoritative DNS separately; resolver
caches may outlive DNS deletion. Repository visibility must be `PRIVATE` for an
authenticated owner and anonymous source access must fail.

## Recovery and rollback

Do not redeploy Ghost during an ordinary infrastructure rebuild. Before an
empty-cluster reconstruction, suspend reconciliation of `ghost-labprod` through
a reviewed Git change so that the retained `initdb` declaration cannot create
an empty replacement over the existing archive generation. Follow the
[CNPG restore procedure](../../../docs/infrastructure/cloudnative-pg.md) to
restore `ghost-postgresql-g1` into a replacement Cluster using bootstrap
recovery and a new archive generation; represent that recovery manifest in Git
before resuming reconciliation. Never reuse the existing archive generation
for a fresh `initdb` or overwrite its objects.

Restoring the game is a separate deployment decision. Reverting the retirement
commit restores the previous chart/image pins and public declarations, but
requires authenticated Argo access to the now-private Ghost repository (or a
new local chart source) before synchronization; a plain Git revert alone is
not a complete rollback. Keep the namespace/PVC and use a compatible schema
revision. Terraform restores DNS only after its reviewed plan is applied.
