# GitOps application delivery

There is one workload environment, `labprod`. Every application has one
production overlay at `apps/workloads/<app>/clusters/labprod` and one Argo CD
Application at `apps/gitops/clusters/labprod/<app>.yaml`.

## Synchronization policy

All active Applications and the bootstrap root declare `automated.prune: true`
and `automated.selfHeal: true`. Argo applies reviewed desired-state changes from
`master`, corrects drift and prunes resources removed from the declared state.
Declare the same policy when adding an Application to the active root. Dormant
manifests excluded from its Kustomization are not activated by this policy.

The "last sync" timestamp records an applied operation, not the latest Git
comparison. It can remain old while an application is Synced and Healthy. A
failed sync or a comparison error still needs diagnosis; automatic mode does
not establish backup, SSO or isolation acceptance.

Merging an application repository alone does not advance pinned LabOps images
or chart commits. Publish first, then update the paired pins in a reviewed
LabOps PR. Restore/cutover procedures must suspend automatic synchronization
through a reviewed change to the affected Application declaration before
temporary changes, then restore the policy after recovered state is ready.
Disabling only a live child Application is insufficient: the root's self-healing
would restore the declaration from Git.

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
| ROM stack (RomM, ROMarr, Prowlarr, qBittorrent) | `rom-postgresql` (CloudNativePG) for RomM; the other services do not require a relational database. | RomM OIDC required; `rom-admins`, only `bingops`. Every authenticated user may use the Authentik-protected request portal, which has no administrative routes. Native ROMarr, Prowlarr and qBittorrent interfaces remain internal. | Database to the `romm` R2 prefix; shared PVC to `rom-files` with 30-day changed-object retention. |
| Gatus | None; seven-day SQLite history is disposable. | Not applicable; no exposed UI. | Loss resets history and is accepted. |
| Status | None; a JSON file on its PVC holds 90 days of availability derived from Gatus. | Not applicable; public, read-only page with no login and no privileged function. | Loss resets the figures of the page and is accepted. |
| Slots | `slots-postgresql` (CloudNativePG). | Not applicable; pseudonymous player accounts have no privileged role and there is no operator UI. | Database to the `slots` R2 prefix. |
| Games | `games-postgresql` (CloudNativePG). | Player accounts are separate; the operator panel requires Authentik, exact `bingops` identity and `games-admins` membership. | WAL and daily backups to the `games` R2 prefix, including administrator action history; offline recovery-code, isolation and runtime acceptance remain required. |
| Ghost (dormant; excluded from the GitOps root) | None of its own; schema `ghost` in the common `arcade` database (`games/arcade-postgresql`), accounts and sessions from its `identity` schema. | Not applicable; lab.bingo player accounts have no privileged role and there is no operator UI. | Covered by the `arcade` WAL archive and backups; runs older than seven days are disposable. See `apps/workloads/ghost/README.md`. |
| Mail (dormant; excluded from the GitOps root) | No database; Postfix queue on `relay-spool` PVC. | Internal authenticated submission only; no public SMTP endpoint. | Bitwarden owns SMTP/DKIM credentials; cert-manager reissues TLS. Queue survives pod replacement but is disposable after disk loss. See `apps/platform/mail/labprod/README.md`. |
| Portfolio | None; stateless public site. | Not applicable; no privileged UI. | Rebuild from Git and the immutable image. |
| Coder (acceptance in progress) | `coder-postgresql` (CloudNativePG). | Public OIDC PKCE client restricted to `coder-admins`, only `bingops`; automatically provisioned OIDC owner. Temporary local bootstrap identities are deleted. | WAL and daily backups to the `coder` R2 prefix; retained home to `coder-workspaces/bingops-lab` with 30-day changed-object history. Both restore acceptance checks are required. |
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
