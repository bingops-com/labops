# ROM stack

The `rom` workload is the blue/green successor of the `romm` namespace. It
combines RomM 5.3.1, ROMarr 0.9.0, Prowlarr 2.6.5.5623 and qBittorrent 5.2.4.
Only legally obtained or freely distributable ROMs may be indexed or
downloaded. Git deliberately contains no indexer or content-source
configuration.

RomM is published at `https://rom.lab.bingo` and uses the Authentik OIDC
client. ROMarr is published at `https://romarr.lab.bingo` through the Authentik
proxy provider. The `rom-admins` group contains only `bingops`
(`therealbingops@gmail.com`) and is the only privileged group mapped by either
application. Prowlarr and qBittorrent have cluster-internal Services only, so
they have no public login surface and no separate SSO provider.

## Storage and credentials

All four applications mount the 200 Gi `rom-data` local-path PVC. RomM owns
the whole `/romm` tree. ROMarr writes to `downloads` and `library/roms`, while
Prowlarr, qBittorrent and ROMarr keep configuration below `configs`. A pinned,
idempotent init script creates those paths and seeds the Prowlarr API key and
qBittorrent WebUI password only when their configuration does not already
exist. Both are derived from the CNPG-generated `rom-postgresql-app` password;
the plaintext value is consumed from the Secret at runtime and is never stored
in Git or logs. Rotation requires deleting the two generated configuration
files before restarting the workloads, otherwise their persisted credentials
remain authoritative.

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

## Blue/green migration

Kubernetes cannot rename a namespace or PVC. The old `romm` Application,
namespace, URL and volume therefore remain intact as the rollback source. The
new `rom-labprod` Application has automated sync explicitly disabled during
the migration.

After an authorized merge:

1. Wait for `romm-files-r2-backup` in the old namespace, or create one Job from
   that CronJob after quiescing uploads. Verify only its completion status.
2. Manually synchronize `rom-labprod`. Its sync-wave `-1` restore Job refuses
   to mark the new PVC as restored when the R2 source is empty.
3. Verify the CNPG recovery, all four Deployments, both public logins, a file
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
curl --fail --silent --show-error https://romarr.lab.bingo/outpost.goauthentik.io/ping >/dev/null
```

Use an incognito session and a non-privileged test identity to confirm that
ROMarr is denied and does not acquire administrator access. Sign in as
`bingops` and confirm administrator access in RomM and ROMarr. Configure and
test only lawful Prowlarr indexers through a controlled port-forward; those
runtime choices are generated state backed up with the PVC, not Git inputs.
