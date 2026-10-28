# Full infrastructure rebuild

## Ownership

- Terraform owns Proxmox networking, Cloudflare, Tailscale DNS and `labmgmt`.
- CAPI on `labmgmt` owns the sole workload cluster `labprod`.
- Argo CD owns all platform services and workloads on `labprod`.
- Bitwarden owns plaintext application credentials; Git owns their mappings.

## Inputs outside Git

Required recoverable inputs are the Proxmox Terraform and CAPMOX API tokens,
the Tailscale OAuth client, the Cloudflare infrastructure and cert-manager
tokens, the generated tunnel credential, one R2 S3 key restricted to
`bingops-cnpg-labprod`, one R2 S3 key restricted to `bingops-pz-labprod`, the
Project Zomboid Restic repository password, and the `labprod` Bitwarden machine
token. The `bingops` Authentik password is also external to Git and belongs in
the operator's password manager; the Bitwarden-delivered Authentik bootstrap
credential is its recovery source after an empty-database rebuild. Keep all
these inputs in the owning password manager or ignored credential file and
rotate them at their provider if lost. Terraform state, kubeconfigs and Talos
configs are sensitive generated state, not documentation.

## Dependency order

1. Restore operator credentials, Proxmox networking and Tailscale routing.
2. Recreate Terraform-owned `labmgmt`; verify Talos and Kubernetes APIs.
3. Initialize pinned CAPI providers and create `labprod`.
4. Install local clients, then bootstrap Argo CD and its production root.
5. Inject the `labprod` Bitwarden machine token into the bootstrap namespaces
   and wait for mappings. Workload token synchronizers, including Project
   Zomboid, then create their namespace-local copy automatically.
6. Apply reviewed Cloudflare DNS, tunnel and the production R2 buckets.
7. Reconcile storage, CloudNativePG and Barman Cloud; verify backup and restore.
8. Reconcile Authentik, observability and workloads; verify Synced/Healthy.
   After an empty Authentik database initialization, use the bootstrap account
   to set or reset the password of the blueprint-owned `bingops` identity, then
   verify that `bingops` is the sole member of every relying-application
   privileged group. Store the password only in the operator's password
   manager; the reset is safe to repeat after a partial failure.
   RomM's OIDC client is public PKCE and adds no external credential. Its CNPG
   archive and the ROM stack file backup reuse the existing bucket-scoped R2
   key. Restore `rom-data` from `rom-files/current`, then restore the database
   from the documented Barman generation. See `apps/workloads/rom/README.md`.
   RomM and the restricted one-click catalogue are published. The catalogue
   route is `rom-requests.lab.bingo`, its Authentik proxy is open to every
   authenticated identity. It uses the ROM Hub code and generated plugin state
   from the pinned ROMarr image, while keeping source URLs server-side. ROMarr,
   Prowlarr and qBittorrent remain internal ClusterIP services. RomM's filesystem watcher
   imports completed downloads without a Client API Token or manual scan. A PostSync Job
   idempotently installs the curated homebrew/freeware ROM Hub plugins; their
   generated state is stored on the R2-backed `rom-data` PVC.
   RomM's enabled metadata providers are separate from that download catalogue.
   Before reconciling RomM, recover its ScreenScraper account username and
   password from the two Bitwarden secrets referenced by the `labprod` overlay.
   The namespace token bootstrap must precede their Bitwarden mapping. The
   [ROM runbook](../apps/workloads/rom/README.md#screenscraper-credentials)
   owns account creation, recovery, rotation and safe provider verification.
   Wait for the PostSync LaunchBox import into its disposable Valkey cache;
   repeat a full ROM application sync after an independent cache loss, as documented in
   `apps/workloads/rom/README.md`.
   The completed blue/green migration left `rom` as the automated production
   stack. The former `romm-labprod` Application, namespace and local volumes
   were retired after explicit confirmation; R2 and Barman remain the recovery
   sources documented in `apps/workloads/rom/README.md`.
   Slots depends on the public `bingops-com/slots` repository and its public
   GHCR image. Reconcile it only after the image tag pinned in
   `apps/workloads/slots/clusters/labprod/values.yaml` exists. Its PostgreSQL
   archive reuses the existing bucket-scoped R2 key under the dedicated
   `slots` prefix; verify WAL archival and one completed backup before opening
   ranked play. See `apps/workloads/slots/README.md`.
   Games follows the automatic synchronization policy of every active
   Application. Recover its bucket-scoped R2 key from Bitwarden and publish the
   pinned Games commit image before reconciling its production declaration.
   Reconcile Authentik's `games-admin` blueprint after the existing `bingops`
   identity, then verify its strict Games callback and dedicated `games-admins`
   group. The public PKCE client needs no additional secret. Review the declared
   Cloudflare TCP/443 egress peers before enabling administrator access.
   For a Games upgrade, merge Games and wait for image publication before
   finalizing its LabOps deployment PR. The `Published Games release` check
   verifies that chart/image pins match a merged commit with a public Linux/amd64
   image. Candidate pins in a draft PR are not a published release. The owning
   runbook documents the repeatable read-only check and schema-compatible rollback.
   Accounts use pseudonyms, passwords and offline single-use recovery codes;
   no SMTP, SMS, mail DNS or Postfix deployment is needed. Recovery-code hashes
   live in PostgreSQL and follow the same backup/restore lifecycle as accounts.
   Network isolation remains a separate acceptance requirement. The current
   Flannel installation has no policy controller; review its addition separately
   before relying on isolation. Automatic sync does not demonstrate enforcement.
   Verify recovery
   codes, backup and isolated restore before public use. Existing accounts
   create their own codes from “Mon compte” using their current password.
   Ownership and repeatable setup: `apps/workloads/games/README.md`.
   Common Games/Slots accounts are prepared but not activated by the GitOps
   root. The reviewed candidate keeps the original clusters while introducing
   `games/arcade-postgresql` and the `arcade` R2 prefix. First migration requires
   proof of both passwords for collisions; reconstruction after cutover restores
   the common backup instead. Ownership, maintenance write freeze, generated
   credential recovery and the recovery overlay are in
   `apps/workloads/arcade/README.md`. Never enable shared mode before the common
   database is restored/prepared, or retire source storage during a cutover.
   Ghost depends on the public `bingops-com/ghost` repository and its public
   GHCR image, pinned with its chart in `apps/gitops/clusters/labprod/ghost.yaml`.
   Its PostgreSQL archive reuses the existing bucket-scoped R2 key under the
   dedicated `ghost` prefix; verify WAL archival and one completed backup. See
   `apps/workloads/ghost/README.md`.
9. Reconcile the private DNS zone `lab.bingo`, Gatus and the LabOps Portal;
   verify `https://lab.bingo` through LAN or Tailscale without publishing it
   through the public Cloudflare Tunnel. The portal image is built from
   `docker/portal`, which clones the `master` branch of `bingops-com/portal`;
   that repository, its public GHCR image and the dispatch token are external
   prerequisites listed in `docker/portal/README.md`. The layout saved from
   the browser lives only on the `portal-data` PVC and is not restored: the
   portal starts from `apps/workloads/portal/base/portal.yaml`. The public
   status page `https://status.lab.bingo` follows Gatus, which it reads
   in-cluster: its image is built from `docker/status` with the external
   prerequisites listed in `docker/status/README.md`, its DNS record comes
   from `terraform/cloudflare` and its route from the Cloudflare Tunnel
   values. Its history lives only on the `status-data` PVC and is not
   restored: after a rebuild the page starts again without past days. If an
   existing unreadable history prevents startup, use the authorized quarantine
   procedure in `apps/workloads/status/README.md` before verifying availability.
   If the workload is healthy but its public name returns `NXDOMAIN`, use the
   Terraform DNS recovery procedure in `docs/infrastructure/cloudflare.md`;
   reconciling the tunnel Application does not create DNS records.
   Coder also depends on this private DNS zone, Authentik, CloudNativePG and
   the published workspace image. Restore its Barman database generation and
   retained home before starting recovered workspaces; keep file backups
   suspended until restoration is verified. The public OIDC client adds no
   secret, and Coder reuses the existing bucket-scoped R2 key through
   Bitwarden mappings. Its automatic setup provisions only the `bingops`
   OIDC owner and imports the Git-tracked template without a persistent setup
   password. Update its bootstrap generation after database-only recovery,
   then perform isolated database/file restore checks.
   The `homeops-dev` image supplies Codex, Claude (from 0.1.2) and HomeOps clients. Publish the reviewed
   image before completing workspace acceptance, then re-enroll the trusted
   operator's `labmgmt`/`labprod` client configs with `provision-homeops-dev.py`
   if they were not recovered with the home. First Codex/Claude login belongs to the
   operator accounts and stays outside Git/images. Their user-owned auth/config
   files persist under the home and are never replaced by startup or cluster-only
   access refresh. Recover a lost or revoked login by signing into its provider
   again. Optional `--shell-aliases` enrollment restores personal Bash aliases
   from the owner's private source file if they were not recovered with the home;
   it preserves existing profiles and adds interactive loading hooks. A failed initial workspace
   start retries against the active template without replacing its retained home.
   Terraform must complete before Coder can authorize the workspace agent;
   the Deployment does not wait for agent-dependent SSH readiness during apply.
   Verify agent startup and Kubernetes readiness separately after provisioning.
   Coder is the selected primary Terraform workstation: after cloning LabOps,
   enroll its ignored API inputs and the current local states from the trusted
   source, with no simultaneous source Terraform operation. Retain the source
   snapshots privately for recovery and use only the workspace state afterward.
   Selected Proxmox SSH, CLI sessions and AWS files are separate sensitive
   inputs, never image layers. The real `/home/coder` startup directory avoids
   runc's failure on the project symlink while mounting the persistent home.
   Renovate proposes Codex npm/lockfile updates and the published workspace
   image digest; the operator reviews image releases and adopts the reconciled
   template through Coder. Native SSH supplies UTF-8 and image acceptance
   verifies browser/emoji fonts. iSH terminal font selection belongs to the
   client device. GitOps also declares shared Codex, Claude and tmux system
   settings in the Coder template. Their checksum participates in template
   import and Pod adoption. Codex defaults to full access with no approvals,
   using the existing restricted Pod as its isolation boundary; it therefore
   does not require nested user namespaces on Talos. Personal account files
   stay on the retained home. The [image runbook](../docker/homeops-dev/README.md)
   owns the setting paths, precedence, non-sensitive tests and rollback.
   See [the Coder runbook](../apps/workloads/coder/README.md) for ordering,
   external inputs, private iSH access, the development dashboard and read-only
   image gallery at `dev.lab.bingo`. The separate `dev-labprod` Application follows
   `bingops-com/dev` for its Deployment and agent ConfigMap. Applications use `PORT.dev.lab.bingo` through
   the authenticated alias gateway. Reconcile Dev's required gallery ConfigMap
   before adopting the Coder template; startup supervises its port 4175 worker.
   Adopt that mount for live port inventory; no new credentials are needed. Also observe the
   single-node availability limit. Restore/start the RPG process in the retained
   workspace separately; the dynamic proxy does not launch project servers.
   Reconcile the private wildcard DNS and DNS-01 certificate before validating
   previews; adopt the gallery mount/startup via a Coder workspace update.
10. Create the bucket-scoped Project Zomboid R2 token in Bitwarden, reconcile
    its mappings and the workload, then verify a Restic snapshot and a
    disposable restore before retiring the Build 41 VM.

For total VM-disk loss, follow the Proxmox recovery procedure. Never replace
`labmgmt` while it owns `labprod` unless CAPI objects have first been moved.

## Retirement of the former test environment

Retire in this order: confirm the test database backup retention decision,
delete the `labtest` CAPI Cluster while `labmgmt` is available, verify VM 152
and CAPI objects are gone, empty `bingops-cnpg-labtest` with the explicitly
destructive procedure in the [Cloudflare runbook](infrastructure/cloudflare.md),
apply a new reviewed Cloudflare plan to remove the bucket, and apply the
reviewed Tailscale DNS plan to remove `test.lab.bingo`. Remove obsolete
Bitwarden and external R2 credentials only after all consumers are gone.

The operations are idempotent when an already-absent cluster, DNS route or
bucket is treated as absent. Safe verification is based on resource existence,
node readiness and Argo CD health; never print state, kubeconfigs or Secrets.
