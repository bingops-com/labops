# Operator helpers

- `cluster-setup.sh` installs client access for the fixed `labmgmt` management
  cluster and sole `labprod` workload cluster.
- `capi-init.sh` installs the pinned providers on `labmgmt`.
- `bootstrap-bitwarden.sh labprod` creates namespace-local operator tokens
  from `BWS_LABPROD_ACCESS_TOKEN` without printing it.
- `deploy.sh` diffs, temporarily deploys, reports or restores production Argo
  CD Applications. Deployment asks for explicit confirmation.
- `setup-coder-workspace.sh` imports the pinned Coder template and creates the
  persistent `bingops/lab` workspace after SSO login. It requires a short-lived
  `CODER_SESSION_TOKEN`, never prints it, and performs live Coder operations.
  See [the Coder runbook](../apps/workloads/coder/README.md).
- `provision-homeops-dev.py` enrolls existing `labmgmt`/`labprod` operator
  kubeconfigs and an optionally supplied Talos config into the retained Coder
  home after its Pod is ready. It streams private content through exec, writes
  0600 generated files, preserves existing default configs and never prints
  credentials. This is personal access enrollment, not a cluster/role creation.
  Re-run it after client credential rotation; the cluster-only invocation
  preserves a still-valid selected context and does not overwrite personal
  Claude/Codex sessions. See the owning Coder runbook.
  Optional flags enroll the selected Proxmox SSH key/host trust, GitHub/Codex
  sessions, AWS files and the three Terraform stacks' ignored inputs. State
  transfer explicitly selects Coder as primary; never run Terraform against an
  independent stale state copy on the old PC. Differing existing private files
  are preserved by refusing the operation before writes.
  `--shell-aliases` privately transfers the source `~/.bash_aliases` and appends
  interactive Bash loading hooks without replacing profiles or copying shell
  history/environment. Personal changes then belong to the retained Coder home.
- `retire-lost-kube-vms.sh` is reserved for the documented total-disk-loss
  recovery and must receive the exact approved VM IDs.
- `purge-r2-bucket.py` reports whether an R2 bucket contains objects and purges
  it only when `--purge` and an exact `--confirm-bucket` value are both given.
  It consumes the ignored Cloudflare Terraform credential without printing the
  token or object names.
- `link-game-accounts.py` is run by each player, not with collected player
  passwords. It verifies both Games/Slots logins and saves a private proof for
  the reviewed account migration.
- `arcade-pg-services.py` generates mode-0600 libpq service/password files for
  the two disposable restored copies and the new Arcade destination. It reads
  only the three named generated Secrets, never source-primary credentials;
  see [Arcade](../apps/workloads/arcade/README.md) for authorization, ports,
  least privileges, credential recovery and cleanup.

Examples:

```sh
./hacks/cluster-setup.sh --management-only
./hacks/cluster-setup.sh
./hacks/deploy.sh status prod
./hacks/purge-r2-bucket.py bingops-cnpg-labtest
```

Kubeconfigs and Talos configs are sensitive generated artifacts installed with
mode 0600. Do not commit them or paste their contents into logs.

The helper seeds the platform bootstrap namespaces. Project Zomboid then
inherits token creation and rotation from `argocd-system` through its
GitOps-managed, least-privilege CronJob; do not inject the token into
`pz-server` manually.

### CKA controller adoption

Run python3 hacks/migrate-cka-controller.py once from the retained Coder home,
after the CKA Pod exists and before activating the controller. It requires an
empty lab, fences/stops the old local controller, retains a private snapshot,
and verifies the copied Terraform/SQLite files before writing the production
migration marker. It refuses an existing target or a repeated fenced transfer.
A partial copy requires operator reconciliation, never automatic overwrite.
See apps/workloads/cka/README.md for ownership and recovery.

### CKA private recovery snapshot

Run python3 hacks/backup-cka-controller.py after a lab lifecycle operation has
finished and before infrastructure maintenance. It copies SQLite online backup,
Terraform state and current guest connection identities into the ignored
retained-home backup scope (`.runtime/production-backups`, ignored at the
repository root; CKA_BACKUP_DIRECTORY can override it), checks hashes internally and refuses a concurrent
lifecycle change. Snapshot files are sensitive and must never be printed or
committed. No VM disk or operator credential is included. Recovery must fence
the active writer and reconcile live VM identities before restoring state.

### CKA deployment-only release snapshot

Run python3 hacks/package-cka-release.py --source /path/to/cka --revision
FULL_COMMIT_SHA to refresh the seven declared Kubernetes manifests and source
checksums in apps/workloads/cka/labprod. It uses immutable local Git objects,
performs no deployment and exports no source code, solutions or credentials.
See the CKA README for image pinning, ownership and reconstruction order.

### CKA durable study progress

After the Arcade cluster is provisioned with the cka_app managed role, run
python3 hacks/bootstrap-cka-study.py --apply. It creates/adopts the generated
role password and reconciles only cka/cka-database with the TLS URI and CA.
It prints no credential and does not migrate data or restart applications.
CNPG owns the role; Arcade backups own identity and CKA progress recovery.
Apply the CKA db/001-study.sql migration through an operator connection before
activating the web configuration. Regenerate credentials only through the
owning helper, reconcile CNPG and roll the web after an authorized rotation.

### Arcade conservation check

After staging restored copies and applying preserve-collisions.sql, run
python3 hacks/verify-arcade-preservation.py with PGSERVICEFILE/PGPASSFILE and
ARCADE_GAMES_RESTORE_SERVICE, ARCADE_SLOTS_RESTORE_SERVICE and
ARCADE_TARGET_SERVICE. It compares original identity fields and both game
statistics tables without logging rows; only aggregate account counts appear.
Never point restore services at a live source primary.

### Retain accepted Arcade migration copies

After isolated common-backup restoration is accepted and both game Deployments
are healthy in shared mode, run python3 hacks/hibernate-arcade-copies.py --apply.
Only six fixed rehearsal/restore copies are stopped; CRs/PVCs and source/archive
data stay intact. The helper checks readiness and the completed common backup,
is idempotent and cannot target the three production/source clusters. These
operator-generated migration copies remain outside GitOps. The Arcade runbook
owns their resume procedure; deletion requires separate explicit targets.

### Arcade canonical accounts and profiles

`python3 hacks/unify-arcade-accounts.py --target rehearsal` is a read-only
preflight of the retained common restore clone. `--apply` executes the two
idempotent upgrades and compares original credentials, independent balances,
references and archives without printing records. Production requires
`--target production --backup NAME --apply`, a fresh completed common backup
and all three web writers frozen by GitOps. The CKA controller stays running.
SQL capabilities are owned by arcade, not postgres. Source data and PVCs stay
retained. See the current Arcade runbook for the authorized policy, maintenance,
SSO claim boundary, backup restoration and reopening order.

`python3 hacks/verify-arcade-unified-restore.py --backup NAME --apply` checks a
fresh common logical dump in a new randomly named database on the already
retained common restore clone while web writes are frozen. Only that newly
created verification database is dropped afterward. Rows, passwords and dump
contents never appear in output or files. This is not a new Barman physical
recovery test; disk headroom and the Arcade runbook govern that separate step.
