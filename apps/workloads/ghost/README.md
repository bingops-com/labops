# Ghost

**Dormant: prepared, not connected to the GitOps root, not deployed.** Ghost
runs only on the common lab.bingo database prepared by
[Arcade](../arcade/README.md), which is itself not in production yet. The
Application `apps/gitops/clusters/labprod/ghost.yaml` is deliberately absent
from that directory's `kustomization.yaml`.

Ghost is a set of four short daily arcade games at `https://ghost.lab.bingo`:
the same course for everyone each day, raced against the ghosts (replays) of
the other players. Anyone can play; publishing a ghost needs the lab.bingo
account shared with Games and Slots. Argo CD will combine the Helm chart and
immutable application commit from the public `bingops-com/ghost` repository
with the production values and the prerequisite resources in this directory.
The GHCR package must be public because the pod has no registry credential.

## Acceptance gate

- Database: none of its own. Ghost uses database `arcade` of the CNPG cluster
  `games/arcade-postgresql`. It reads `identity.users`, opens and closes its
  sessions in `identity.sessions` (cookie `ghost_session`, host-only), and
  keeps its runs in its own schema `ghost`, created and migrated at startup by
  the role `arcade` that owns the database. It refuses to start unless
  `identity.schema_version` is 1, and never creates, imports or changes an
  account. Password changes, recoveries and administrator revocations in Games
  therefore also end Ghost sessions.
- Credential: CNPG generates `games/arcade-postgresql-app`. The arcade
  reconciler (`games/arcade-credentials-sync`) copies its URI, hostname
  normalized, into `ghost/arcade-database` (key `uri`), as it does for Slots.
  The target Role in this namespace (`clusters/labprod/arcade-credentials.yaml`)
  allows Secret creation there and reads/patches of that one Secret only. No
  new secret, Bitwarden entry or R2 key is introduced.
- Backup: the arcade WAL archive and daily backup (prefix `arcade`) include the
  `ghost` schema. A restore of the common database brings the runs back with
  the accounts; runs older than seven days are pruned by the application, so
  their loss only resets the boards in progress.
- Authentik and administrators: not applicable. Player accounts are the
  pseudonymous lab.bingo identities; Ghost has no privileged role and no
  operator UI.
- Other durable data: none. The container is read-only and stateless.
- Network: the chart's NetworkPolicy allows Traefik in on TCP/3779, DNS out,
  and TCP/5432 to the `arcade-postgresql` pods of `games` only. The observed
  Flannel installation does not enforce NetworkPolicy; do not claim isolation
  from the rendered YAML.

## Activation

Requires, in order: the arcade cutover completed and accepted (common backup
and isolated restore verified), then the published Ghost image. Each step is a
reviewed LabOps change; merging one is a deployment.

1. The pinned pair is commit `583eb238c633938180d32a876a062ae9389fd0de` of
   `bingops-com/ghost`: its `CI` workflow passed and published
   `ghcr.io/bingops-com/ghost:sha-583eb238c633938180d32a876a062ae9389fd0de`, public, with a Linux/amd64 image.
   For a newer release, merge to `master`, wait for the `CI` workflow, verify
   anonymous Linux/amd64 pull access to the new tag, then move both pins
   together.
2. In one LabOps PR:
   - confirm that the pins in `apps/gitops/clusters/labprod/ghost.yaml` and
     `clusters/labprod/values.yaml` name the release to deploy;
   - add `https://github.com/bingops-com/ghost.git` to `sourceRepos` in
     `apps/gitops/clusters/labprod/project.yaml`, and `ghost.yaml` to
     `apps/gitops/clusters/labprod/kustomization.yaml`;
   - publish the name: `ghost.lab.bingo` in `terraform/cloudflare/locals.tf`
     and the tunnel ingress `http://ghost.ghost.svc.cluster.local:80` in
     `apps/cloudflare/bingops/values.yaml` (see
     `docs/infrastructure/cloudflare.md`; the Terraform apply is a separate,
     authorized operation);
   - monitor `https://ghost.lab.bingo/healthz` in
     `apps/workloads/gatus/base/config.yaml` (group `Public`) and list it in
     `apps/workloads/status/clusters/labprod/values.yaml`;
   - mark Ghost active in `docs/gitops-applications.md` and remove the dormant
     wording here.
3. After synchronization, wait for the reconciler to log
   `Reconciled ghost/arcade-database` (it logs `Skipped ghost/...` while the
   namespace or Role is missing), then for the Ghost pod to become ready.

The application owns the `ghost` schema migrations (`ghost.schema_migrations`);
an image rollback is valid only to a release that knows the current schema
version. The arcade migration and merge scripts do not touch `ghost`.

## Verify

Offline, before merging:

```sh
kubectl kustomize apps/workloads/ghost/clusters/labprod >/dev/null
kubectl kustomize apps/workloads/arcade/staging/labprod >/dev/null
helm template ghost /path/to/ghost/chart --namespace ghost --values apps/workloads/ghost/clusters/labprod/values.yaml >/dev/null
bash /path/to/ghost/chart/tests/check.sh
```

Post-activation, read-only (no Secret data):

```sh
kubectl --context labprod get application ghost-labprod -n argocd-system
kubectl --context labprod get deployment,pod,secret/arcade-database -n ghost
kubectl --context labprod get cronjob,job -n games
curl -fsS https://ghost.lab.bingo/healthz
curl -fsS https://ghost.lab.bingo/livez
```

Then sign in with a real lab.bingo account, publish one run, check it appears
on the board from another browser, change that account's password in Games and
confirm the Ghost session ends.

## Recovery and rollback

- Application: revert the pin change; the `ghost` schema stays in place.
- Database: follow the arcade runbook. Ghost shares its restore point with
  Games and Slots; it has no separate database restore.
- Credential rotation: after a CNPG password rotation, wait for the reconciler,
  then restart the Ghost Deployment (authorized operation) to refresh its
  environment.
- Retirement: remove the Application from the root (the namespace and Secret
  are pruned), then, in a separately approved change, `DROP SCHEMA ghost
  CASCADE` on the common database. Never touch the `identity` schema.

Reproducibility: every Ghost input is in Git or derived from the arcade
database and CNPG; no non-Git input is added. The reconciler is idempotent and
skips Ghost until its namespace exists. Ownership: LabOps owns this overlay and
the credential copy; the Ghost repository owns the chart, image and `ghost`
schema; the arcade runbook owns the database, its backups and recovery.
