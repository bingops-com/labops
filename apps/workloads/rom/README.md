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
to every authenticated Authentik user. It loads a browsable snapshot from all
seven curated sources on arrival and supports optional name and platform
filters. It exposes only the platform list, catalogue search and release-grab
operations; it cannot read or change
ROMarr, Prowlarr or qBittorrent settings. The portal invokes ROM Hub's pinned
search and import libraries server-side; the browser receives only short-lived,
opaque result identifiers and never receives source URLs or credentials. ROMarr
has no multi-user authorization model, which is why its native UI remains private.
Its pod disables Kubernetes service-link environment variables because the
generated `ROMARR_PORT=tcp://...` value would override the image's numeric
`ROMARR_PORT` setting and prevent startup.
Their LinuxServer S6 entrypoints start as root only long enough to switch to
UID/GID 1000; their containers drop every capability except the ownership and
UID/GID-switch capabilities required for that transition.

The request portal imports completed ROM Hub downloads into the shared
`library/roms` tree. RomM's
filesystem watcher is enabled declaratively with a two-minute debounce and
performs a quick scan when those files arrive. This removes the need for a
RomM Client API Token or an administrator-owned `tasks.run` credential. The
request portal persists only ROM Hub's generated plugin and job state on the
shared PVC and uses the already-pinned ROMarr image; Git and the bootstrap Job
reconstruct it completely.

The PostSync `rom-catalog-bootstrap` Job installs and enables seven curated
ROM Hub plugins: `aminet` (freely distributable Amiga packages), `demozoo`
(demoscene productions), `homebrew` (GB/GBC/GBA/NES), `if-archive`
(interactive fiction), `libretro-content`, `scummvm-freeware`, and
`universal-db` (3DS/DS homebrew). None requires an API credential. The source
archives publish author-distributed software, freeware or material permitted
for personal use; individual package terms still apply. Broad Archive.org and
No-Intro catalogues remain excluded because they mix those categories with
commercial titles. The portal runs each plugin in ROM Hub's required
seccomp sandbox, downloads a selected result into ROM Hub's job directory, and
atomically imports it into the shared `library/roms/<platform>` tree. A user
therefore searches at `rom-requests.lab.bingo`, clicks a result once, and sees
the imported title appear at `rom.lab.bingo` after RomM's watcher scans it.
RomM lists only imported local files, so a remote catalogue entry appears there
after its one-click download, not before. Interactive-fiction files and some
Demozoo platforms can be catalogued by RomM but have no compatible browser
player; the portal still imports them and the source remains visible.
Prowlarr and qBittorrent remain available
for operator-configured lawful sources but are not required by these default
catalogues.

## RomM metadata providers

`base/romm.yaml` enables LaunchBox, Steam, Demozoo, Pouët, CSDb and Flashpoint
alongside Hasheous. These providers require no user credential. Libretro is
always enabled in RomM 5.3.1 and supplies artwork. This metadata selection is
separate from the ROM Hub download catalogue at `rom-requests.lab.bingo`:
enabling a metadata provider adds descriptions and artwork to imported games.
Steam covers PC platforms; Demozoo, Pouët and CSDb cover demoscene productions.

LaunchBox's remote metadata lives in the internal Valkey cache. The idempotent
`base/metadata-bootstrap.yaml` PostSync Job checks its public metadata heartbeat
and queues RomM 5.3.1's own import task when necessary. It reuses RomM's pinned
image, low-priority queue and bootstrap job ID, waits for an active import,
and retries a failed attempt. RomM's startup rebuilds outdated stores but does
not initialize an entirely empty cache by itself.
The first import must finish before its metadata heartbeat succeeds;
enabling the provider alone does not mean its database is ready. The scheduled
refresh runs daily at `0 4 * * *` with RomM's `TZ=Europe/Paris`. Valkey reserves
256 MiB and may use up to 2 GiB for the imported metadata; its former 256 MiB
limit was sized for the smaller cache without LaunchBox.
Argo CD replaces the single Valkey instance in wave `-1`, before RomM in
wave `0`, then runs the PostSync bootstrap against the new cache. Valkey uses `Recreate`
to keep a single cache behind its Service during a rollout.

The cache is disposable generated state, with persistence disabled. Losing it
does not lose ROMs or PostgreSQL data. After an independent Valkey restart,
reconcile `rom-labprod` with an authorized full Argo CD sync to rerun the
PostSync bootstrap, then wait for LaunchBox's heartbeat. Selective resource
syncs do not run hooks. The daily refresh also reconstructs an empty cache.
The bootstrap makes no API-authentication request and reads no Secret; it
only accesses the internal cache and public metadata heartbeat. Its failed
Job remains visible for diagnosis; a full sync replaces it and safely retries.
If the import fails, the administrator can retry the **LaunchBox metadata
update** in RomM's administration tasks. Retries rebuild cache data and do not
download game binaries or change credentials. No extra bootstrap Secret or
manually generated database is needed for an empty rebuild.

IGDB and MobyGames still require separately supplied sensitive credentials;
this workload does not configure them. Their missing-key messages
do not mean the credential-free providers or the download catalogue are down.
See the [upstream metadata guide](https://docs.romm.app/latest/getting-started/metadata-providers/)
and the [pinned environment reference](https://github.com/rommapp/romm/blob/5.3.1/env.template).

After authorized reconciliation, these read-only checks contact live systems
and print only provider flags and health booleans:

```sh
curl -fsS https://rom.lab.bingo/api/heartbeat | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["METADATA_SOURCES"]); print("LaunchBox scheduled:",d["TASKS"]["ENABLE_SCHEDULED_UPDATE_LAUNCHBOX_METADATA"])'
curl -fsS https://rom.lab.bingo/api/heartbeat/metadata/launchbox
```

Verify enabled providers in the matching dialog after refreshing the page.
An enabled provider can still fail its health check because its upstream is
unreachable; a ready LaunchBox cache is specifically required for that source.

### ScreenScraper credentials

The `labprod` overlay connects ScreenScraper through
`screenscraper-secret.yaml`. Bitwarden Secrets Manager owns the sensitive
account inputs; Git owns only their identifiers and the Kubernetes references.
The Bitwarden controller materializes `rom-screenscraper-credentials`, and
RomM reads its `SCREENSCRAPER_USER` and `SCREENSCRAPER_PASSWORD` keys as
environment variables. The official pinned `rommapp/romm:5.3.1` image already
contains the application's ScreenScraper developer credentials; no developer
secret or API-key generation is required for this deployment.

The lab operator owns the external ScreenScraper account. Create a free account
at <https://www.screenscraper.fr/membreinscription.php> and verify it as required
by ScreenScraper. Store its username as `rom-screenscraper-user` and its
password as `rom-screenscraper-password` in the existing LabOps Bitwarden
project. The existing namespace machine account needs read access to that
project and these two secrets; no write or administrative Bitwarden permission
is needed. Record only the two secret UUIDs in `screenscraper-secret.yaml`.
Keep account recovery email access in the operator's password manager.

These credentials cannot be recovered from Git. Restore them from Bitwarden;
if the password is lost, reset it through ScreenScraper and update the same
Bitwarden secret. If either secret is recreated, update its UUID in the owning
manifest. During rotation, wait for a new successful Bitwarden synchronization
timestamp after the credential update, then increment
`labops.bingo/screenscraper-credentials-revision` in the
overlay and use the authorized GitOps delivery workflow. RomM reads these
variables only at startup, so updating Bitwarden alone does not update a running
process. Reusing the same secret IDs and revision after a partial failure is
safe; the controllers retry without modifying ROM files or PostgreSQL data.

Reconstruction order is the existing namespace token bootstrap, the
ScreenScraper Bitwarden mapping in wave `-1`, then RomM. Missing mapped keys
prevent its container from starting until the Secret becomes available. An
initial rollout or rotation replaces the single RomM instance and briefly
interrupts access. ScreenScraper enforces account quotas; a false provider
heartbeat can also mean account validation, an upstream outage or a quota
problem. Never diagnose by printing Secret values, process environment or
credential-bearing request URLs.

After authorized deployment, these read-only checks disclose only the
controller's readiness boolean, provider flags and metadata health:

```sh
kubectl --context labprod get bitwardensecret rom-screenscraper-credentials -n rom -o jsonpath='{.status.conditions[?(@.type=="SuccessfulSync")].status}{"\n"}{.status.lastSuccessfulSyncTime}{"\n"}'
curl -fsS https://rom.lab.bingo/api/heartbeat | python3 -c 'import json,sys; d=json.load(sys.stdin)["METADATA_SOURCES"]; print("ScreenScraper enabled:", d["SS_API_ENABLED"]); print("Developer credentials available:", d["SS_DEV_CREDENTIALS_SET"])'
curl -fsS https://rom.lab.bingo/api/heartbeat/metadata/ss
```

An enabled flag confirms configuration, not successful authentication; require
the provider health check before declaring the connection ready. Refresh RomM
and select ScreenScraper in a metadata scan of an existing ROM. This enriches
local games and does not search for or download missing ROM files. Roll back by
reverting this connector change through GitOps; keep the account and Bitwarden
values for recovery rather than deleting them as part of a rollback.

## Storage and credentials

The workloads share the 200 Gi `rom-data` local-path PVC. RomM owns
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

The installed plugin code and ROM Hub job state are generated state below
`configs/romarr/rom-hub` on `rom-data`. They are reconstructed from the pinned
ROMarr image plus the declarative PostSync Job and are also included in the R2
file backup. The bootstrap only logs plugin slugs and status; it never emits
the API key or plugin configuration.

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
incognito session and a non-privileged test identity to confirm the unfiltered
catalogue loads without entering a game name, request an explicitly
redistributable title and verify that it appears in RomM after the watcher
delay without a manual scan. Confirm the same identity cannot reach the
native ROMarr UI or acquire administrator access in RomM; sign in as `bingops`
and confirm administrator access. Configure and test only lawful Prowlarr
indexers through controlled port-forwards; those optional runtime choices are
generated state backed up with the PVC, not Git inputs.
