# GitOps application delivery

There is one workload environment, `labprod`. Every application has one
production overlay at `apps/workloads/<app>/clusters/labprod` and one Argo CD
Application at `apps/gitops/clusters/labprod/<app>.yaml`.

## Application acceptance gate

Every new application must classify its database, authentication and durable
data before it is considered complete. "Not applicable" is valid only with a
short rationale in the application's README; do not add a database, login or
backup to a stateless service merely to satisfy the checklist.

| Concern | Required implementation | Post-reconciliation evidence |
| --- | --- | --- |
| Relational database | Use a CloudNativePG `Cluster`; consume its generated application credential rather than an in-chart database. | The application connects successfully through the CNPG read/write Service and the `Cluster` reports ready. |
| Database backup | Declare a Barman Cloud `ObjectStore` and `ScheduledBackup` targeting a unique prefix in `s3://bingops-cnpg-labprod`. Reuse the namespace-local, Bitwarden-delivered bucket credential. | A completed `Backup` exists and the CNPG/Barman status reports successful WAL archival without displaying Secret data. |
| Interactive or privileged access | Declare the Authentik provider, application and a dedicated privileged group in the tracked blueprint. Public, read-only or non-HTTP services may document why SSO is not applicable. | OIDC discovery and login work through trusted HTTPS. |
| Administrator assignment | Map the application's administrator role only to its privileged Authentik group. The group must contain only `bingops` (`therealbingops@gmail.com`). Disable or account for local bootstrap administrators. | `bingops` receives the administrator role and a non-privileged test identity does not. The group membership contains exactly `bingops`. |
| Non-database durable data | Back up irreplaceable PVC/object data to a dedicated, least-privilege Cloudflare R2 prefix or bucket. If data is reproducible or intentionally disposable, document that classification and the consequence of loss. | The latest backup is successful and a disposable restore has been tested; for disposable data, verify the documented rebuild path. |

The current application decisions are:

| Application | Database | Authentik / privileged identity | Durable-data recovery |
| --- | --- | --- | --- |
| Authentik | `authentik-labprod-postgresql` (CloudNativePG). | It is the identity provider, not an OIDC relying application; its own bootstrap administration is documented separately. | Database to the `authentik` R2 prefix. |
| Argo CD | None; desired state is stored in Git and Kubernetes. | Required; `argocd-admins`, only `bingops`. | Rebuild from Git; no application backup. |
| Grafana | No operator database; dashboards and data sources are declarative. | Required; `grafana-admins`, only `bingops`. | Rebuild from Git; metrics and logs follow their platform retention. |
| Portal | None; its PVC contains an exportable layout, sessions and derived status. | Required for editing; `portal-editors`, only `bingops`. | Commit exported layouts; loss of the remaining state is accepted. |
| ROM stack (RomM, ROMarr, Prowlarr, qBittorrent) | `rom-postgresql` (CloudNativePG) for RomM; the other services do not require a relational database. | RomM OIDC required; `rom-admins`, only `bingops`. ROMarr, Prowlarr and qBittorrent are cluster-internal and have no public interactive login. | Database to the `romm` R2 prefix; shared PVC to `rom-files` with 30-day changed-object retention. |
| Gatus | None; seven-day SQLite history is disposable. | Not applicable; no exposed UI. | Loss resets history and is accepted. |
| Status | None; a JSON file on its PVC holds 90 days of availability derived from Gatus. | Not applicable; public, read-only page with no login and no privileged function. | Loss resets the figures of the page and is accepted. |
| Portfolio | None; stateless public site. | Not applicable; no privileged UI. | Rebuild from Git and the immutable image. |
| Project Zomboid | None. | Not applicable; the game protocol does not use browser SSO. | Restic backup to the dedicated `bingops-pz-labprod` R2 bucket. |

Update this table in the same change whenever an application's classification
changes. Platform applications not listed here must document the same decisions
in their owning runbook.

Use immutable image tags or digests. Public hostnames must be added explicitly
to `terraform/cloudflare/locals.tf` and `apps/cloudflare/bingops/values.yaml`.
Private Argo CD and Grafana names and the LabOps Portal apex `lab.bingo` stay
on Tailscale split DNS. Secret
values belong in the Bitwarden `labprod` project; Git contains only UUID
mappings.

Validate locally before merging:

```sh
kubectl kustomize "apps/workloads/${APP_NAME}/clusters/labprod" >/dev/null
kubectl kustomize --enable-helm apps/gitops/clusters/labprod >/dev/null
```

An application delivered by a chart under `charts/` (currently Status) keeps
only its `clusters/labprod/values.yaml` under `apps/workloads/<app>`; its
Argo CD Application renders the chart from `master` with that file. Validate
it with `helm lint` and `helm template` as shown in its README instead of the
first command.

`master` is the declared production revision. A reviewed merge is the normal
deployment authorization. For an exceptional branch deployment, first push the
branch, inspect `./hacks/deploy.sh diff prod --revision <branch>`, then run
`./hacks/deploy.sh deploy prod --revision <branch>`; the helper asks for an
additional confirmation. Return to `master` with
`./hacks/deploy.sh restore prod`.

Verify without reading Secrets:

```sh
./hacks/deploy.sh status prod
kubectl --context labprod get applications -n argocd-system
```

For an application with CNPG, SSO or durable data, extend its README with
resource-specific, non-sensitive checks for the acceptance gate above. A render
alone does not prove connectivity, login authorization or backup usability;
perform those runtime checks only after the change has been deployed through an
authorized merge or an explicitly authorized live operation.

Rollback by reverting the production commit or restoring `master`, then wait
for Argo CD to report Synced and Healthy.
