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
ScheduledBackup. Before relying on the backup, verify a completed backup and a
disposable restore without exposing application data or credentials.

The retired `bingops-cnpg-labtest` bucket may be deleted only after explicit
confirmation that its historical backups are no longer required.
