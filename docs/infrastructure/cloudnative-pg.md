# CloudNativePG and R2 backups

CloudNativePG, Barman Cloud and the PostgreSQL resources run only on
`labprod`. Terraform owns `bingops-cnpg-labprod`; Bitwarden owns the database
passwords and the bucket-scoped S3 access key.

The production cluster is `authentik-labprod-postgresql` in namespace
`authentik`. WAL archiving and scheduled base backups use the tracked
ObjectStore and ScheduledBackup resources. The R2 Secret must expose
`ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`.

Rebuild order is R2 bucket, external bucket token, Bitwarden mapping,
CloudNativePG operator, Barman Cloud plugin, ObjectStore, database cluster and
ScheduledBackup. The Barman Cloud Argo CD Application retries its sync because
its cert-manager webhook dependency can still be starting when the child
Application is first reconciled. CloudNativePG and Barman Cloud use server-side
diff so Kubernetes fields newer than the bundled Argo CD schema do not block
self-healing after a partial bootstrap.

Prometheus scrapes the database exporter through the tracked PodMonitor
(`pod-monitor.yaml`); the portal's PostgreSQL widget reads size, connections
and archiving age from it.

## Archive folder and database incarnations

The cluster archives to `s3://bingops-cnpg-labprod/authentik/<serverName>`,
where `serverName` is the plugin parameter set in
`apps/platform/postgresql/labprod/cluster.yaml`. Barman refuses to archive into
a folder written by another incarnation of the database: WAL archiving then
fails with `Expected empty archive`, the cluster reports
`ContinuousArchiving=False` and every Backup stays in phase `started`.

Whenever the cluster is recreated with `initdb` (an empty database rather than
a restore), bump the `serverName` suffix (`-g2`, `-g3`, …) in the same change.
The earlier folders are kept and remain the source for a restore of the
previous incarnation: `authentik-labprod-postgresql` (no suffix) holds the
backups up to 2026-09-10.

Verify recovery without reading Secrets:

```sh
kubectl --context labprod get applications -n argocd-system barman-cloud-labprod cloudnative-pg-labprod postgresql-labprod authentik-labprod
kubectl --context labprod get certificates -n cnpg-system
kubectl --context labprod get clusters.postgresql.cnpg.io -n authentik authentik-labprod-postgresql
kubectl --context labprod get deployments -n authentik
kubectl --context labprod get clusters.postgresql.cnpg.io -n authentik authentik-labprod-postgresql -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'
kubectl --context labprod get backups.postgresql.cnpg.io -n authentik
```

`ContinuousArchiving` and `LastBackupSucceeded` must be `True`, and the latest
Backup must be `completed`. The Sauvegardes widget of the portal
(`https://lab.bingo`) shows the same state.

The Barman client and server certificates must be ready, PostgreSQL must report
one ready instance and a primary, and both Authentik deployments must be
available. Before relying on the backup, also verify a completed backup and a
disposable restore without exposing application data or credentials.

The retired `bingops-cnpg-labtest` bucket may be deleted only after explicit
confirmation that its historical backups are no longer required.
