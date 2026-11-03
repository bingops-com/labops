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
return 401; /labs redirects to Authentik; private /healthz responds over the
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

Study accounts use the common Arcade database after the preserve-collisions
migration. CNPG owns cka_app and its generated password;
hacks/bootstrap-cka-study.py reconciles the web-only URI and trusted database
CA. Apply db/001-study.sql from the pinned CKA source with an operator
connection before restarting the web. Recover Arcade before web account
login/progress. SSO remains mandatory for VM operations.
