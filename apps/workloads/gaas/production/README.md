# Production Gaming as a Service

This component owns the GameRoom controller in `gaming`, the protected
Kubernetes Terraform backend in `gaming-state` (suffix `edge-gateway`), and the
GitOps intent in `rooms/pz-bingops.yaml`. It preserves the original public
`pz.bingops.com` endpoint, IPv4 `188.245.252.46` (Hetzner primary IP `154062800`)
and the existing gateway `labops-edge-01` during ownership adoption. Its initial
VM ID is `169230729`; later suspend/resume cycles intentionally change that ID.

The system Application owns the CRD, controller, public catalogue, mappings,
RBAC and retained preload PVC. The rooms Application owns GameRoom intent only.
The controller owns generated runtime objects; Terraform exclusively owns the
cloud gateway. Automatic pruning is disabled for both Applications. Namespaces
and the world PVC also carry `Prune=false`. Never remove world storage or the
retained address as implicit server cleanup.

## External inputs and reconstruction

Provider, R2 and game credentials use the existing LabOps Bitwarden project
and UUID mappings in `system/`. The namespace-specific token synchronizer copies
only `argocd-system/bw-auth-token`; no value is in Git or logs. Run its CronJob
once after bootstrap instead of waiting for the first five-minute schedule.
The public SSH key in `system/operator-key.yaml` is the existing gateway key,
recovered from the original Terraform state; replacing it changes boot inputs.
The pinned Terraform source SHA is retained by Git tag `gaas-gateway-module-v1`.

The catalogue promotes the verified Steam build `26486687` artifact in the
separate encrypted `gaas-releases-20261122` repository. Its full snapshot and
runtime-image digest are in `system/config.yaml`. Recover the R2 key/password
through Bitwarden before restoring worlds or state. A new Steam version needs
a separately verified immutable artifact and a new catalogue key. Never mutate
a catalogue key already used by a room. Runtime tags alone do not select Steam.

Restore the Terraform backend before enabling cloud workers after a rebuild.
`gaas-state-backup` regularly backs up its one state Secret into the separate
encrypted `gaas-production-state-backups` repository, restores the bundle to
memory and compares it. It refuses a locked/changing backend. Its receipt proves
a file restoration, not live state installation. To recover: stop the controller
and Terraform Jobs, restore the selected verified bundle into protected memory,
validate namespace/suffix/lineage and retained IP identity against the current
cloud inventory, then restore that Secret to `gaming-state` before resuming.
Discard plaintext temporary recovery files. Do not apply an empty backend over
retained cloud resources. Terraform's Lease serializes backend writers.

## Staged ownership handoff

Preparation starts with the room Suspended and gateway execution disabled.
That stage does not stop the active legacy server. Before activation:

1. Read the original local state only in protected storage. Back it up encrypted
   to the production-state repository; restore and compare its bytes/lineage.
   Require a refreshed saved plan showing all seven managed resources no-op,
   with only the singleton VM/key address moves. Never print provider diagnostics,
   state, plans or cloud-init. Preserve original VM/IP IDs throughout adoption.
   The checked one-time helper runs `python3 terraform/edge-gateway/adopt-state.py
   plan`, then `backup`, then `migrate`. It keeps plaintext files only under the
   ignored `.runtime/gaas-adoption-20261122`, obtains credentials through existing
   Secret references, fails on resource changes and records bounded receipts.
   The fixed original checkout path/VM ID deliberately make it an adoption tool,
   not a generic disaster-recovery overwrite command.
2. Stop other Terraform writers. Migrate that checked state to `gaming-state`,
   preserving lineage/IDs, then apply only the reviewed no-op address-move plan.
   Retire the original local execution state into protected recovery storage;
   it must not remain a second writer. Task init refuses an unconfigured backend.
3. Preload the pinned binary artifact into the separate retained world PVC.
   The operation receipt binds its world ID, full snapshot, repository and Steam
   build. A later controller request reuses those exact verified binaries and
   emits a fresh receipt; other artifacts require restoration.
4. Verify zero connected players. Commit the legacy Helm overrides:
   `replicaCount: 0`, `backup.enabled: false`, `service.type: ClusterIP`, the
   catalogue runtime digest and `steam.expectedBuildId: "26486687"`.
   The original StatefulSet and data PVC remain a rollback source. Wait for the
   game Pod and any backup writer to terminate before the final offline backup.
   The dated `cutover/final-backup-20261123.yaml` Job mounts only the original
   PVC read-only, adds a snapshot without pruning history, checks the complete
   repository, verifies a disposable restore and checks every SQLite database.
   Create it only after confirming no game or backup writer remains. Its bounded
   receipt provides the full snapshot to select for the handoff; a failed Job
   cannot authorize starting the new game.
5. Take a verified, restorable final snapshot of the original world. Enable
   production adoption only with the migrated backend present, select that full
   world snapshot in the GameRoom, and commit Running. The operator restores
   into the new PVC, requires a fresh backup before installation, verifies the
   exact build and starts the game on the original NodePorts/public endpoint.
6. Verify public UDP, current Argo revision/generation, retained IP and the
   original gateway VM identity. Only then exercise production suspension or
   resume. Each last-consumer stop requires a fresh verified backup before VM
   removal; IPv4/DNS and both wanted world volumes remain retained.

Rollback before acceptance: suspend the new room and wait for its writers to
finish, then restore the legacy Helm overrides and NodePorts in Git. Use the
original PVC and its pre-cutover build. If gameplay changed the new world,
explicitly select and restore its latest verified backup before reusing legacy
storage; do not silently discard progress or downgrade a newer save. Never run
two game processes or two backups against one world repository during handoff.
The legacy Application keeps its immutable runtime/build pins when changing
replicas back to one and Service type back to NodePort. Removing these pins
would let the legacy init container download a moving Steam branch on rollback.

## Owner UX

The Portal widget tracks Git/Argo and observed GameRoom generations. Without a
GitHub App it links to the `game-room-state.yml` GitHub form; the owner chooses
Running or Suspended and the workflow writes only that typed state, without
AI, a cloud credential or Kubernetes access. The branch must permit its normal,
non-force commit. Workflow success records intent; room status proves completion.

A dedicated App remains optional for integrated Portal command buttons and
version PRs. It needs Contents/PR write on LabOps only, explicit OIDC owner-group
access, and a Bitwarden private-key mapping. Do not reuse Codex/ARC credentials.
The Portal has get-only access to the configured room and Argo Application.
Adding another server still requires its reviewed GameRoom, route allocation
and immutable release; other game adapters and hot gateway-route changes are
not implemented. Existing route changes require the shared gateway suspended.

The 2026-11-22 preload was interrupted by a host reboot. The dated retry Job
reuses only its exact temporary binary directory, requires the original world
PVC binding and no loaded/running world, uses the same immutable snapshot and
Restic full restore verification, then atomically publishes the installation.
It does not mount the legacy PVC. If that staging directory is absent it uses
the normal installer. Review the UID, path and artifact for a different run.
