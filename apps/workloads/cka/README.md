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
