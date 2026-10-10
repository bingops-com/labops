# ROM stack

The `rom` workload is the blue/green successor of the `romm` namespace. It
combines RomM 5.3.1, ROMarr 0.9.0, Prowlarr 2.6.5.5623 and qBittorrent 5.2.4,
plus a request-only web portal.
Only legally obtained or freely distributable ROMs may be indexed or
downloaded. Git deliberately contains no indexer or content-source
configuration.

RomM is published at `https://rom.lab.bingo` and uses the Authentik OIDC
client. The `rom-admins` group contains only `bingops`
(`therealbingops@gmail.com`) and is the only group mapped to RomM's
administrator role. ROMarr, Prowlarr and qBittorrent have cluster-internal
Services only, so they have no public login surface or SSO provider. ROMarr's
API is reachable only inside the cluster at
`http://romarr.rom.svc.cluster.local:6868` and requires its seeded API key.
The bilingual one-click catalogue is published at
`https://rom-requests.lab.bingo` through an Authentik proxy and is available
to every authenticated Authentik user. It exposes only the platform list,
interactive search and release-grab operations; it cannot read or change
ROMarr, Prowlarr or qBittorrent settings. The portal injects ROMarr's API key
server-side, so neither the browser nor Authentik receives it. ROMarr has no
multi-user authorization model, which is why its native UI remains private.
Its pod disables Kubernetes service-link environment variables because the
generated `ROMARR_PORT=tcp://...` value would override the image's numeric
`ROMARR_PORT` setting and prevent startup.
Their LinuxServer S6 entrypoints start as root only long enough to switch to
UID/GID 1000; their containers drop every capability except the ownership and
UID/GID-switch capabilities required for that transition.

ROMarr imports completed downloads into the shared `library/roms` tree. RomM's
filesystem watcher is enabled declaratively with a two-minute debounce and
performs a quick scan when those files arrive. This removes the need for a
RomM Client API Token or an administrator-owned `tasks.run` credential. The
request portal is stateless and uses the already-pinned Python runtime image;
Git and the runtime Secret reconstruct it completely.

The PostSync `rom-catalog-bootstrap` Job installs and enables four curated
ROM Hub plugins: `homebrew` (GB/GBC/GBA/NES), `libretro-content`,
`scummvm-freeware`, and `universal-db` (3DS/DS homebrew). These catalogues are
limited to homebrew, freely distributable content, or freeware; they do not
provide commercial ROM sets. The same idempotent Job configures ROMarr's
Direct HTTP client with `/downloads/sites` as its landing directory. A user
therefore searches at `rom-requests.lab.bingo`, clicks a result once, and sees
the imported title appear at `rom.lab.bingo` after ROMarr completes the
download and RomM's watcher scans it. Prowlarr and qBittorrent remain available
for operator-configured lawful sources but are not required by these default
catalogues.

## Storage and credentials

All four applications mount the 200 Gi `rom-data` local-path PVC. RomM owns
the whole `/romm` tree. ROMarr writes to `downloads` and `library/roms`, while
Prowlarr, qBittorrent and ROMarr keep configuration below `configs`. A pinned,
idempotent init script creates those paths and seeds the Prowlarr API key and
qBittorrent WebUI password only when their configuration does not already
exist. Those credentials and ROMarr's pinned API key are derived from the
CNPG-generated `rom-postgresql-app` password; the plaintext value is consumed
from the Secret at runtime and is never stored in Git or logs. Rotation
requires deleting the two generated Prowlarr and qBittorrent configuration
files before restarting those workloads; ROMarr reads its key from the Secret
at every start.

The installed plugin code and ROMarr client configuration are generated state
below `configs/romarr` on `rom-data`. They are reconstructed from the pinned
ROMarr image plus the declarative PostSync Job and are also included in the R2
file backup. The bootstrap only logs plugin slugs and status; it never emits
the API key or client configuration.

RomM uses the operator-managed CloudNativePG cluster `rom-postgresql`. The
first bootstrap restores database `romm` and owner `romm` from Barman server
`romm-postgresql-g1`, then archives the new incarnation as
`rom-postgresql-g2`. CNPG generates `rom-postgresql-app` and updates the
restored role password during promotion.

The shared PVC is synchronized daily to
`s3://bingops-cnpg-labprod/rom-files/current`; overwritten and deleted objects
are retained below `rom-files/archive` for 30 days. The database has its own
daily Barman backup and 14-day retention under the `romm` prefix. Both use the
existing bucket-scoped R2 credential delivered from Bitwarden. R2 server-side
encryption is used; there is no additional client-side encryption key to
recover.

The sync-wave `-2` bootstrap Job copies the Bitwarden machine token into the
namespace before the wave `-1` `BitwardenSecret` is created. Argo CD waits for
that one-time Job to complete, preventing R2 consumers and CNPG recovery from
starting before `rom-r2-credentials` can be materialized. The five-minute
CronJob keeps the token current after bootstrap and rotation.

## Retirement of the former namespace

Kubernetes cannot rename a namespace or PVC. The `rom-labprod` restore,
database, backup and availability gates passed, so it is the automated
production stack. The former `romm-labprod` Application was given the Argo CD
resources finalizer in a separate, successfully reconciled phase before its
removal. Deleting that Application therefore cascaded through namespace `romm`
instead of leaving orphaned resources.

The migration was accepted with these non-sensitive checks:

1. The R2 restore Job and a later `rom-files-r2-backup` Job completed.
2. All five Deployments became available and `rom-postgresql` reported Ready,
   ContinuousArchiving and LastBackupSucceeded.
3. The public route and certificate target only `rom.lab.bingo`; ROMarr remains
   an internal ClusterIP service.

The public tunnel and OIDC redirect for `romm.lab.bingo`, Application
`romm-labprod`, namespace `romm`, PVCs `romm-data` and
`romm-postgresql-1`, the old database and every remaining namespaced object
were retired after explicit confirmation. The R2 file archive and Barman backup
remain the recovery source.

Repeating the R2 export is safe. The restore Job is idempotent because it
writes `.r2-migration-restored` only after a successful copy. Remove that
marker only when deliberately repeating a full restore into a reviewed empty
target PVC.

## Verification

Render locally without contacting the cluster:

```sh
kubectl kustomize apps/workloads/rom/clusters/labprod >/dev/null
```

After authorized reconciliation, verify without displaying Secret values:

```sh
kubectl --context labprod get application -n argocd-system rom-labprod
```

```sh
kubectl --context labprod get deployment,pod,pvc,job,cronjob,cluster,scheduledbackup -n rom
```

```sh
kubectl --context labprod get job rom-catalog-bootstrap -n rom
```

```sh
kubectl --context labprod get namespace romm --ignore-not-found
```

```sh
curl --fail --silent --show-error https://rom.lab.bingo/api/heartbeat >/dev/null
```

```sh
kubectl --context labprod get service romarr -n rom -o jsonpath='{.spec.type}{"\n"}'
```

Confirm that the command reports `ClusterIP` and that no Ingress targets
ROMarr.

```sh
curl --head --silent --show-error https://rom-requests.lab.bingo
```

Confirm that an unauthenticated request is redirected to Authentik. Use an
incognito session and a non-privileged test identity to search and request a
freely distributable test file, then verify that it appears in RomM after the
watcher delay without a manual scan. Confirm the same identity cannot reach the
native ROMarr UI or acquire administrator access in RomM; sign in as `bingops`
and confirm administrator access. Configure and test only lawful Prowlarr
indexers through controlled port-forwards; those optional runtime choices are
generated state backed up with the PVC, not Git inputs.
