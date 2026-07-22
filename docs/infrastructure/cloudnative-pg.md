# CloudNativePG

CloudNativePG owns PostgreSQL clusters on `labtest` and `labprod`. Argo CD owns
the CloudNativePG operator, the Barman Cloud CNPG-I plugin and all database
resources. Terraform owns the two Cloudflare R2 buckets. Bitwarden Secrets
Manager owns database passwords and the environment-specific R2 S3 credentials.

The operator is pinned to chart `0.29.0` (CloudNativePG `1.30.0`) and the backup
plugin to chart `0.7.0` (Barman Cloud `0.13.0`). Both are installed in
`cnpg-system`; cert-manager must be healthy before the plugin starts. Each
database has its own `ObjectStore`, R2 path and credentials. WAL archiving is
continuous and base backups run daily. Test retains a seven-day recovery window
and production retains fourteen days.

## Storage and availability

Both workload clusters currently have one node and use Rancher's pinned
`local-path` provisioner. PostgreSQL therefore runs one instance per cluster.
This protects the process and automates database lifecycle, but it does not
provide node or disk high availability. R2 backups are the durable recovery
source after node or disk loss. Increase to at least three failure-domain-aware
nodes and use replicated storage before setting `instances` above one.

Never point two applications at the same PostgreSQL cluster by default. Add one
isolated CloudNativePG `Cluster`, database role, Bitwarden mapping and R2 prefix
per application and environment. Applications that do not use a relational
database need no PostgreSQL connection.

## External prerequisites

The Cloudflare infrastructure token needs `Workers R2 Storage Write` to create
the Terraform-owned buckets. For runtime backups, create one R2 Object Read &
Write token restricted to `bingops-cnpg-labtest` and another restricted to
`bingops-cnpg-labprod`. Their Access Key ID and Secret Access Key cannot be
recovered from Git and must be stored in the corresponding Bitwarden project.
The owning Cloudflare procedure is documented in
[`cloudflare.md`](cloudflare.md).

Database passwords are generated outside Git, stored in the matching Bitwarden
project, and mapped to Kubernetes Secrets by committed `BitwardenSecret`
resources. The CNPG bootstrap Secret must expose `username` and `password`; the
R2 Secret must expose `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`. Never commit a
plaintext Kubernetes Secret or paste these values into an operator command.

The test resources run as `cnpg-validation` in namespace `postgresql`, using
the `validation` R2 prefix. Production runs
`authentik-labprod-postgresql` in namespace `authentik`, using the `authentik`
prefix. These names are recovery identities: do not reuse either prefix for a
second source cluster.

## Deployment order

1. Apply the Terraform R2 bucket resources.
2. Create and store the two least-privilege R2 credentials in Bitwarden.
3. Commit their non-sensitive Bitwarden UUID mappings.
4. Reconcile the `postgresql` namespace on `labtest`, then re-run
   `hacks/bootstrap-bitwarden.sh labtest` so the namespace-local operator token
   exists. Re-running the helper is safe after partial failure.
5. Reconcile local-path storage, cert-manager, CloudNativePG and Barman Cloud.
6. Reconcile the `labtest` database and wait for `Cluster` readiness and WAL
   archive health.
7. Trigger a plugin backup, wait for completion, then perform a disposable
   restore into a differently named test cluster.
8. Only after that gate passes, reconcile the production database and repoint
   Authentik. The accepted migration policy is a new empty Authentik database;
   keep the previous StatefulSet PVC until the new login and OIDC flows pass.

## Safe verification

Verify only metadata and status: operator deployments are Available, the
`Cluster` reports Ready, its PVC is Bound, the `ObjectStore` reports no error,
WAL archiving succeeds, and `Backup` reaches `completed`. For recovery testing,
create a new cluster from the latest backup, confirm it becomes Ready, and then
remove only that explicitly named disposable restore. Do not print Secret YAML,
decoded values, connection strings, or backup payloads.

All operations are idempotent after partial failure: Terraform recreates only
missing buckets, Argo CD reconciles declared resources, Bitwarden refreshes
mapped Secrets, and CNPG recovery creates a new cluster rather than overwriting
the source. If an R2 key is lost, create a replacement, update Bitwarden, verify
a fresh backup, and revoke the old key.
