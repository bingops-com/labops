# ROM stack

The `rom` workload is the blue/green successor of the `romm` namespace. It
combines RomM 5.3.1, ROMarr 0.9.0, Prowlarr 2.6.5.5623 and qBittorrent 5.2.4.
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
Their LinuxServer S6 entrypoints start as root only long enough to switch to
UID/GID 1000; their containers drop every capability except the ownership and
UID/GID-switch capabilities required for that transition.

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

## Blue/green migration

Kubernetes cannot rename a namespace or PVC. The old `romm` Application,
namespace, URL and volume therefore remain intact as the rollback source. The
new `rom-labprod` Application has automated sync explicitly disabled during
the migration.

After an authorized merge:

1. Wait for `romm-files-r2-backup` in the old namespace, or create one Job from
   that CronJob after quiescing uploads. Verify only its completion status.
2. If a previous synchronization is still running, terminate that stale Argo CD
   operation, then manually synchronize `rom-labprod`. The PVC and restore Job
   are created together so `WaitForFirstConsumer` can bind the volume. The Job
   refuses to mark the PVC as restored when the R2 source is empty, and every
   data-consuming Deployment waits for `.r2-migration-restored`.
3. Verify the CNPG recovery, all four Deployments, the RomM public login, the
   internal-only ROMarr Service, a file
   scan, a completed PVC backup, and a disposable R2 restore.
4. Enable automated sync for `rom-labprod` in Git only after acceptance. Retire
   `romm-labprod`, `romm.lab.bingo`, namespace `romm`, its PVC and the old
   Barman generation only through a later change with explicit deletion
   authorization.

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
kubectl --context labprod get application -n argocd-system rom-labprod romm-labprod
```

```sh
kubectl --context labprod get deployment,pod,pvc,job,cronjob,cluster,scheduledbackup -n rom
```

```sh
kubectl --context labprod get cronjob,job -n romm
```

```sh
curl --fail --silent --show-error https://rom.lab.bingo/api/heartbeat >/dev/null
```

```sh
kubectl --context labprod get service romarr -n rom -o jsonpath='{.spec.type}{"\n"}'
```

Confirm that the command reports `ClusterIP` and that no Ingress targets
ROMarr. Use an incognito session and a non-privileged test identity to confirm
it does not acquire administrator access in RomM, then sign in as `bingops` and
confirm administrator access. Configure and test ROMarr and only lawful
Prowlarr indexers through controlled port-forwards; those runtime choices are
generated state backed up with the PVC, not Git inputs.
