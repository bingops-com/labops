# Ghost

Ghost is a set of four short daily arcade games at `https://ghost.lab.bingo`:
the same course for everyone each day, raced against the ghosts (replays) of
the other players. Anyone can play; publishing a ghost needs an account. Argo
CD combines the Helm chart and immutable application commit from the public
`bingops-com/ghost` repository with the production values and prerequisite
resources in this directory. The GHCR package is public because the pod has no
registry credential. Ghost follows the automatic synchronization policy of
every active Application.

Like Games and Slots, Ghost has its own database and its own pseudonymous
player accounts. It also has the same opt-in shared-accounts mode
(`database.sharedAccounts`), off in production; see
[Shared accounts](#shared-accounts).

## Acceptance gate

- Database: `ghost-postgresql`, a one-instance CloudNativePG cluster on
  `local-path`, database and owner `ghost`, kept on uninstall. The application
  consumes CNPG's generated `uri` credential and creates its tables (`users`,
  `sessions`, `runs`) at startup.
- Backup: continuous WAL archival and a daily backup (03:45) use the
  `ghost-postgresql` ObjectStore, the shared `bingops-cnpg-labprod` bucket and
  the dedicated `ghost` prefix. The namespace-local `ghost-r2-credentials`
  mapping reuses the existing bucket-scoped R2 key pair of Games and Slots from
  Bitwarden; the token bootstrap copies `bw-auth-token` into the namespace.
- Authentik and administrators: not applicable. Player accounts are
  pseudonymous game identities with no privileged role; there is no operator UI.
- Other durable data: none. The container is read-only. Runs older than seven
  days are pruned by the application; accounts are the only lasting data.
- Network: the chart's NetworkPolicy allows Traefik in on TCP/3779, DNS out and
  TCP/5432 to `ghost-postgresql` only. The observed Flannel installation does
  not enforce NetworkPolicy; do not claim isolation from the rendered YAML.

No new external input: the R2 key and Bitwarden machine token already exist
(recover and rotate them as documented in the
[CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md)); CNPG generates
the database password. The Bitwarden token bootstrap is idempotent and the
BitwardenSecret and CNPG controllers retry once their dependencies exist.
The public name `ghost.lab.bingo` is declared in `terraform/cloudflare/locals.tf`
(CNAME, applied by Terraform) and routed by the tunnel in
`apps/cloudflare/bingops/values.yaml`.

## Release

The Application `apps/gitops/clusters/labprod/ghost.yaml` and
`clusters/labprod/values.yaml` pin the same commit of `bingops-com/ghost`
(chart and `sha-<commit>` image). To release: merge to `master` in
`bingops-com/ghost`, wait for its `CI` workflow to publish the image, verify
anonymous Linux/amd64 pull access to the new tag, then move both pins in one
LabOps PR. Merging that PR deploys. A database schema only moves forward: roll
back to a release that knows the current `schema_migrations` version.

## Verify

Offline, before merging:

```sh
kubectl kustomize apps/workloads/ghost/clusters/labprod >/dev/null
helm template ghost /path/to/ghost/chart --namespace ghost --values apps/workloads/ghost/clusters/labprod/values.yaml >/dev/null
bash /path/to/ghost/chart/tests/check.sh
```

After synchronization, read-only (no Secret data):

```sh
kubectl --context labprod get application ghost-labprod -n argocd-system
kubectl --context labprod get deployment,pod,cluster,scheduledbackup,backup -n ghost
curl -fsS https://ghost.lab.bingo/healthz
curl -fsS https://ghost.lab.bingo/livez
```

Confirm the CNPG cluster is ready, WAL archival succeeds and one `Backup`
completes, then create an account, publish a run and see it on the board from
another browser.

## Recovery and rollback

Application rollback is a Git revert of the pin change. Database recovery
follows the [CNPG runbook](../../../docs/infrastructure/cloudnative-pg.md): pause
automatic synchronization through a reviewed change to `ghost.yaml`, restore
into a new cluster from `ghost-postgresql-g1` with a new archive generation,
and never change the bootstrap of an existing cluster or overwrite earlier
archives. A restore can bring back sessions that were closed after the
recovery point; they still expire by date. CNPG is protected by Helm keep; do
not delete the namespace, PVC or R2 archives to roll back application code.

## Shared accounts

Ghost can use the common lab.bingo accounts of Games and Slots, prepared by
[Arcade](../arcade/README.md) and not in production yet. In that mode it reads
`identity.users`, opens and closes its sessions in `identity.sessions` (cookie
`ghost_session`, host-only), keeps its runs in a `ghost` schema, creates no
account, and refuses to start unless `identity.schema_version` is 1.

The switch follows the arcade cutover of Games and Slots, in its own reviewed
change: set `database.sharedAccounts: true`, `database.existingSecret.name:
arcade-database` and `networkPolicy.databaseTo` to the `arcade-postgresql`
pods of the `games` namespace, keeping `database.cnpg.enabled: true` so that
Argo does not prune `ghost-postgresql`. The arcade reconciler copies
`ghost/arcade-database` once `clusters/labprod/arcade-credentials.yaml` is
present (it already is). Ghost's own accounts are not merged: its players sign
in with their lab.bingo account and the boards in progress (seven days at
most) restart. Retiring `ghost-postgresql` afterwards is a separate, explicitly
approved change.

Reproducibility: every input is in Git, Bitwarden (existing R2 key and token)
or generated by CNPG. Ownership: LabOps owns this overlay, backups and recovery;
the Ghost repository owns the chart, image and schema.
