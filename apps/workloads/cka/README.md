# CKA on labprod

Source and deployment manifests: https://github.com/bingops-com/cka.
Argo pins source and both GHCR images in apps/gitops/clusters/labprod/cka.yaml.
Public hostname cka.lab.bingo routes through Cloudflare directly to cka/cka:80.
Simulations are public; application OIDC protects /labs and all lab APIs.
Authentik owns public PKCE client cka and group cka-lab-users (initially bingops).

One Recreate Pod contains web and private controller sharing only a Unix socket.
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
return 401; /labs redirects to Authentik; private /healthz responds over the
Unix socket. Positive login uses the learner's browser. Do not inspect secret
values, tokens or raw Terraform output in verification.

Private snapshots can be created with hacks/backup-cka-controller.py when no
lifecycle job is running. Hash-checked snapshots enter the existing daily
retained-home backup scope. This helper is operator-triggered, not a scheduled
controller-volume backup, and does not back up disposable guest disks.

## Study account database and private Git source

CKA now has a prepared integration with the Arcade account database. The common
Games/Slots migration is still a separate prerequisite, owned by
[Arcade](../arcade/README.md); adding CKA does not authorize merging player
accounts or switching the two existing production applications. Source migration
SQL is db/001-study.sql in the private CKA repository. It requires the prepared
identity schema and creates only cka study tables/grants in one transaction.

The declared CNPG managed role cka_app is separate from the Arcade owner.
Run python3 hacks/bootstrap-cka-study.py --apply after the cluster and CKA
namespace exist. It generates games/cka-database-role once, reuses it on retry,
and creates/updates cka/cka-database with a verified TLS URI and the cluster CA.
It reads only the named Arcade CA/role Secrets and writes those two fixed CKA
credential names; operator permissions are get/create/patch Secrets in these
namespaces and get on the Arcade Cluster. It never connects to the database or
prints secret values. CNPG owns role/password reconciliation; the helper owns
the generated Secret material. The web alone consumes the URI and CA. After a
CA/password rotation, rerun it and authorize a web rollout to refresh mounts/env.
Lost role credentials can be regenerated and reconciled rather than recovered
from Git; data survives. CKA study data joins Arcade's existing WAL/R2 backup
and restore lifecycle. Run the schema migration with an operator DB role before
activating account login. No new bucket or database PVC is created by CKA.

The GitHub CKA repository was made private at the owner's request. The local
Application/AppProject declarations now use git@github.com:bingops-com/cka.git;
these local edits have not been applied or pushed. Existing unauthenticated
HTTPS GitOps reads cannot fetch that private source until access is activated.
Prepare the external repository credential with
python3 hacks/bootstrap-cka-repository.py --apply, then reconcile the reviewed
SSH source and AppProject together. This operation requires GitHub repository
administration to create a read-only deploy key and create/get on the single
argocd-system/cka-git-repository Secret. It does not push commits or deploy CKA.
Argo's managed GitHub host-key pin must exist; do not disable SSH host checking.

The deploy key is generated retained-home state under ~/.local/share/cka-gitops,
mode 0600, covered by the home backup. Re-running the helper adopts the same
key and refuses a differing named GitHub key or Kubernetes credential. Restore
that retained key to reconstruct access; if it is lost, remove only the named
labprod-argocd-cka-readonly GitHub deploy key and cka-git-repository Secret under
an authorized rotation, regenerate, and repeat bootstrap. No user PAT is copied.
Read-only verification is repository visibility, Argo comparison success,
application health and login rejection without credentials. Positive lab
acceptance requires the owner's Bingops SSO, independently of player login.

Reconstruction is defined by these runbooks and source SQL. Non-Git inputs are
generated role/deploy keys, Arcade backups and the existing Authentik inputs;
their recovery/rotation is specified above. Schema migration and credential
bootstrap are idempotent, partial SQL failures roll back, and conflicting
credentials are refused. Owners and activation order are explicit. Verification
uses health, revision conflicts and disposable fixtures without reading players,
passwords, sessions or private notes into operator output.
