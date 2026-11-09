# CKA on labprod

Private application source: https://github.com/bingops-com/cka.
Argo reads the deployment-only snapshot under apps/workloads/cka/labprod in
LabOps and pins both GHCR images in apps/gitops/clusters/labprod/cka.yaml.
Public hostname cka.lab.bingo routes through Cloudflare directly to cka/cka:80.
Simulations are public; application OIDC protects /labs and all lab APIs.
Authentik owns public PKCE client cka and group cka-lab-users (initially bingops).

Two separate Recreate Deployments run web and the private controller.
The web talks to cka-controller:8443 using a dedicated cert-manager CA and
mutual TLS. Only the client CN cka-web is accepted. Certificates rotate
through mounted Secrets without a controller restart. Rollout wave 0 replaces
the old monolithic web Pod before wave 1 starts the retained singleton
controller; a global state lock also prevents simultaneous writers.
Only the controller mounts cka-controller-inputs and the retained controller PVC.
The external Secret is bootstrapped from backed-up retained-home credentials by
the CKA helper; no plaintext secret is stored in either Git repository. This
external input has not yet been migrated into Bitwarden.

Before initial activation, stop and fence the retired Coder controller, adopt
its existing SQLite/Terraform state and write the migration marker. Never run
two independent states against the common image/pool/storage. The production
PVC is the sole active state owner; preserve retired private snapshots.
The [owning runbook](https://github.com/bingops-com/cka/blob/main/docs/production.md)
defines inputs, safe bootstrap, recovery and limitations. Local-path persistence
needs private retained-home snapshots for off-site recovery; no automatic
controller-volume off-site backup exists yet.

Verification: public /healthz returns 200; unauthenticated/spoofed lab APIs
return 401; /labs returns an ordinary 404 to unauthorized visitors;
/admin initiates Authentik SSO and admits only Bingops; private /healthz responds over the
mutually authenticated TLS endpoint. Positive login uses the learner's browser. Do not inspect secret
values, tokens or raw Terraform output in verification.

Private snapshots can be created with hacks/backup-cka-controller.py when no
lifecycle job is running. Hash-checked snapshots enter the existing daily
retained-home backup scope. This helper is operator-triggered, not a scheduled
controller-volume backup, and does not back up disposable guest disks.

## Private source and release manifests

CKA code, scenario preparation and worked solutions stay in the private CKA
repository. GitHub organization policy disables deploy keys, so Argo reads only
non-secret deployment manifests from the existing LabOps GitOps source. No new
Git credential, broad user PAT, policy relaxation or application secret is
required. CI publishes the two runtime images from the private source.
The existing `cka-web` and `cka-controller` GHCR packages are public and are
pulled anonymously. Repository privacy does not restrict access to image
contents, including controller preparation code. This release keeps those
packages; confidential image distribution requires new private packages and
durable registry pull credentials before changing the pinned image names.

For each release, run python3 hacks/package-cka-release.py --source /path/to/cka
--revision FULL_COMMIT_SHA, then pin both images to that same source commit in
the CKA Application. The helper reads seven fixed deploy/ files from that exact
local Git object, never uncommitted files, fault injection or solutions. Review
the snapshot and release.json checksums, render Kustomize, and publish the
LabOps release only after CI/image publication succeeds. Re-running the helper
at the same commit is deterministic; it performs no cluster operations.

When adopting this source from the earlier CKA-repository Application, apply
the reviewed apps/gitops/clusters/labprod/cka.yaml once during the authorized
rollout. The root Application deliberately respects ignored targetRevision
fields, so it can preserve the old CKA commit after the repository URL changes;
that commit does not exist in LabOps. The adoption sets targetRevision to the
declared master branch. Refresh CKA comparison afterward, verify the new image
revisions, then wait for the rollout. Do not confuse an old healthy Pod with a
completed deployment. This adoption needs no PVC or guest VM operation.

The snapshot is generated release state committed to Git. Rebuild requires
only LabOps, the pinned published images, existing Authentik inputs and the
existing controller Secret/PVC recovery described above. The private CKA source
is needed to develop a new release, not to reconcile the deployed manifests.
GitOps owns runtime configuration; CKA owns application code and upstream
manifest templates. Compare release.json hashes before the image rollout and
verify health, source/image revisions and anonymous SSO rejection afterward.

Study accounts use the canonical Arcade directory and shared profile contract.
Recover Arcade through its [owning runbook](../arcade/README.md) before web
account/profile/progress access. CNPG owns cka_app and its generated password;
hacks/bootstrap-cka-study.py reconciles the web-only URI and trusted database
CA. On a fresh initialization, apply db/001-study.sql from the pinned CKA source
with an operator connection, then the canonical/profile contracts as the arcade
owner, before activating web account access. Existing common backups restore
these contracts together; never rerun the historical source import.

Verified SSO always resolves to the same canonical study account before an old
password cookie is considered. Callback/session/logout retire that old cookie;
provider or profile outages cannot silently select another account. The SSO browser session uses encrypted PostgreSQL state after the account-services
migrations and recovered session key are activated. The first transition from
legacy memory sessions requires a new sign-in. SSO authorization remains mandatory
for VM operations; source and controller data stay retained. Public client/offline artifacts exclude the historical operator guide;
only legacy progress IDs remain. The source CI verifies those artifacts and the
SSO UX on the standalone server. The private source README owns the full UX and
privacy review; publisher/contact and retention/erasure prerequisites must be
completed before claiming full regulatory compliance.

## Account-services release

The account-services release adds verified-email sign-in and recovery, public
pseudonymous gaming profiles, data-rights requests, bounded retention and encrypted
persistent SSO. Public profile DTOs exclude personal free-text fields and private labs.
Its [account-services runbook](https://github.com/bingops-com/cka/blob/main/docs/account-privacy.md)
owns activation order, additive 003/004 migrations, Resend sender/domain checks,
secret recovery and rotation, public privacy settings, erasure/restore procedures
and verification. It supersedes the memory-only/no-new-migration assumptions
above only when that release is activated.

The new web template consumes `cka/cka-account-services` and `cka/cka-privacy`;
the private input is bootstrapped by `hacks/bootstrap-cka-account-services.py`.
Run it with `--apply` after restoring the named Resend vault entry and the private
`.runtime/cka-account-services/session-key` from the retained-home backup.
A first activation generates that key with mode 0600. The helper creates only an
absent Secret, compares repeat runs privately and refuses a differing existing
Secret; never rotate it to work around a failed restore. Both this recovery file
and private logical rehearsal dumps belong to the established home backup scope.
The `bws` CLI must be installed; this activation used official CLI 2.1.0 on
Linux amd64 (binary SHA-256 `e6982cfac1094d9bbcc981101a277739b116da14cba9afb0bf556d1c2bf4153c`).
Recover the CLI through [Bitwarden’s official distribution](https://bitwarden.com/help/secrets-manager-cli/),
verify its published artifact checksum, and use `--bws /trusted/path/bws` to
select the reviewed binary without exposing the machine token. The helper reads only the existing
`argocd-system/bw-auth-token` and the named sending-key entry. The referenced Resend sending key is in the existing Bitwarden
project; the dedicated SSO encryption key remains a recovery prerequisite.
The owner verified the `cka.lab.bingo` sender domain; a Resend simulator send
from `accounts@cka.lab.bingo` was accepted on 2026-11-09. The sending key and separate retained session key were bootstrapped for this
release; values are never placed in the deployment snapshot. Migrations 003/004 add confirmation and email recovery; 004
gates existing unverified KubeQuest accounts, so deploy working mail first.
The owning runbook also records the separate Games offline-code cutover gap. Do not grant the application a broader Resend management
key merely to list domains. Its privacy CronJob starts suspended pending review.
For SQL activation, create a completed CNPG plugin Backup of arcade-postgresql,
then run `hacks/migrate-cka-account-services.py --source /path/to/cka --revision SHA
--backup NAME --target rehearsal --apply`. It restores an actual private logical
snapshot with its actual ACLs into a disposable loopback PostgreSQL, restores
the observed ownership of the three legacy 002 objects, applies 002/003/004 twice
and checks account/progress preservation. The legacy policy table and its two
functions may belong to postgres from the historical reset activation. The
transaction adopts only those exact objects into arcade, rejects any unexpected
owner, and then executes the application migrations as arcade. It also verifies
that cka_app can no longer execute either offline recovery capability. A private receipt records this source and
backup. With the same parameters and `--target production --apply`, it checks
that backup is completed/recent and atomically applies the same immutable SQL
as arcade, with short lock/statement timeouts and preservation guards. It never
executes reset-progress.sql, deletes a shared account or starts a lab VM.
Rollback retains additive tables and must not use a stale identity restore.
The privacy CronJob stays suspended; new registration stays closed while the
real legal configuration is missing. Existing accounts can verify an email and
use mail recovery independently. No DNS or backup-retention change is involved. The retained historical account copies
also belong in the operator's erasure/restore inventory.

Reconstruction checks for this release: Git supplies code, immutable SQL and
bootstrap helpers; the Resend value comes from the named vault entry and the
session key from retained-home backup, independently of PostgreSQL. Repeated
bootstrap compares privately and never silently rotates; repeated migration is
transactional and preserves accounts/progress. KubeQuest owns application/SQL,
LabOps owns input recovery, canonical backup and GitOps rollout. Verification
uses completed-backup status, a restored-data rehearsal receipt, schema flags,
exact image/source revisions and public health/access rejection, without secrets.
