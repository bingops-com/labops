# Isolated Gaming as a Service acceptance

These manifests are intentionally outside the production Argo root. They are
the declared inputs for the user-authorized isolated acceptance run, not an
adoption of the active Project Zomboid StatefulSet or existing edge gateway.
The controller/CRD/runtime source is on the `pz-server` repository's
`feat/gaming-as-a-service` branch; its `gaas/README.md` owns the lifecycle design.
`gitops.yaml` bootstraps a separate acceptance AppProject/Application in
`argocd-system`. It follows only `rooms/` on `feat/gaas-lifecycle`, permits only
GameRooms in `pz-server` and cannot apply generated workloads or cluster
resources. Automatic pruning is disabled; accidental manifest removal cannot
delete a test GameRoom. The existing production Application remains separate.

## Inputs and ownership

- `access.yaml` declares the state namespace, controller/worker RBAC and
  Bitwarden mapping. Credential values are recovered by the existing Bitwarden
  operator using the namespace-local machine token; Git contains only UUIDs.
  The mapping uses the existing Hetzner project token, zone-specific Cloudflare
  token and edge-specific Tailscale auth-key OAuth client. Recover and rotate
  these at the owning provider/password manager; no new tokens were created.
- `config.yaml` pins the LabOps source commit and worker image by digest. It
  names `gaas-test-edge-20261122`, a separate Kubernetes backend suffix,
  DNS record `pz-gaas-20261122.bingops.com`, and two reserved UDP port pairs.
  The operator public key is test-only; its private half is not needed by the
  API-driven workflow. An authorized operator can generate a new key pair for
  a fresh test; changing the public key of a running gateway replaces its VM.
- `release-export.yaml` reads only `/data/server` from the existing production
  PVC, mounted read-only. It uploads the installed Steam binaries into the
  separate encrypted `gaas-releases-20261122` repository and checks all data.
  Its receipt identifies the Steam build and immutable snapshot. It must not
  be used as a world backup or read as proof of a completed game version update.
- `release-export-retry.yaml` retries that export after the observed node
  reboot, reusing existing Restic packs. It removes only stale locks in the
  dedicated binary repository; never run concurrent exports to that repository.
- `release-export-controlled.yaml` is the resumed attempt after inspection of
  the second host reboot. It caps CPU at 500m, uses one Go worker and nice 19,
  and keeps the same read-only source and deduplicated encrypted target. This
  is a bounded retry, not a fix or proof of host stability. No BIOS or hardware
  setting was changed. Require its final receipt after full data checking;
  a 100% file counter alone does not prove snapshot completion.
- `state-recoverycheck.yaml` reads only the isolated backend while its Lease is
  unlocked, saves a minimal Secret recovery bundle into the separate encrypted
  `gaas-state-backups-20261122` repository, restores it to memory-backed storage
  and compares its contents. It checks that the live backend resource version
  stayed unchanged. It does not write restored Secrets to Kubernetes or migrate
  the production backend. No state values are printed. Its short receipt is the
  safe verification output; the backup itself contains sensitive state.
- `controller.yaml` runs the pinned test controller. Its gateway reference is
  configured as `shared-test`, so it does not adopt the existing production
  StatefulSet or the existing gateway. It must not run alongside another writer
  of this test gateway outside the controller's Lease.
- `running-backup-check.yaml` is a bounded, one-shot copy of the second test
  room's CronJob template. Run only after its game is ready and before changing
  that room's desired state. It exercises the save/quit FIFO, shutdown marker,
  encrypted upload/integrity check and automatic game restart, using only the
  second test world's PVC/repository. Wait for completion and public A2S
  recovery before proceeding; do not run it against the production world.
- `retained-world-check.yaml` mounts only the second test world's retained PVC,
  read-only and without credentials. After deleting its original GameRoom, it
  verifies the exact deletion-operation receipt, saved world name and SQLite
  integrity. Its pinned request ID belongs to that original UID/generation;
  another run needs the new expected identity, not a weakened assertion.
  The deletion-marked object used generation 4; the pre-delete Git object was
  generation 3. The first check correctly rejected that wrong expected identity.
  The corrected expectation is corroborated by the completed deletion backup
  Job `gaas-c95c8abb-backupstoppe-f2cfca10f5a1085b` in cluster events.
- `world-seed*.yaml` restore a known production snapshot into `emptyDir`,
  verify SQLite integrity and seed two separate test repositories. They never
  mount the production PVC. `rooms/gaas-pz-*.yaml` reference these repositories and
  existing credential Secret names; each room has its own retained PVC.

Never point test backup retention at the production `/server` repository.
The original gateway state remains local in the original LabOps checkout;
this test backend is unrelated and cannot serve as a production state migration.

## Execution order and recovery

1. Install the reviewed CRD from `pz-server/gaas/config/gamerooms.crd.json`,
   then this directory's `access.yaml` and `config.yaml`. Confirm only the
   expected credential *key names* materialize, without reading values.
2. Run the export and seed Jobs. Wait for successful receipts and integrity
   checks. A large binary export can take an hour on the lab uplink; its
   declared deadline is two hours. Interrupted Restic uploads can be retried
   with a new Job name and deduplicate existing packs.
3. Fill the release catalogue from the verified full snapshot ID and immutable
   runtime-image digest. Keep catalogue keys immutable. The initial acceptance
   snapshot uses Steam build `26486687`; this is not a second game release.
4. Use the controller with `--apply` only for the `shared-test` gateway and
   these two GameRooms. Render `rooms/`, push its reviewed desired state to the
   feature branch, then bootstrap `gitops.yaml`. Subsequently change only the
   GameRoom manifests in Git; let the acceptance Argo Application apply them.
   Confirm both the Argo revision and the GameRoom's observed generation.
   Start one room, test its public UDP endpoint, start a
   second, suspend the first and confirm the gateway remains, then suspend
   the second. Require a current verified backup receipt for each world.
   Resume and verify the retained IP and world. The final desired state in
   the two manifests is Suspended. Do not put the broader acceptance directory
   into an auto-sync root: it contains one-shot Jobs and credential mappings.
   To test GameRoom deletion, keep the resumed first room running, remove only
   `gaas-pz-two` from `rooms/` and its Kustomization in Git, and wait until Argo
   has observed that revision. Pruning is deliberately disabled, so delete
   only that named test GameRoom as the reviewed deletion action. Its finalizer
   must obtain a fresh deletion backup before garbage collection. Confirm its
   generated workloads disappear while the world PVC keeps its original UID,
   the first endpoint stays online and the gateway VM is unchanged. Restore
   the second manifest as Suspended in Git; its new GameRoom UID must not
   replace or delete the retained world PVC. Never remove a finalizer to force
   this test through. Finish by suspending the first room and confirming the
   test VM is absent. Re-run the state recovery-file check only after Terraform
   is idle to retain a current encrypted backend bundle.
5. Check the active production StatefulSet and gateway independently. Changes
   to these resources require a separate reviewed ownership handoff and the
   production state recovery/migration in the edge-gateway runbook.

The Terraform worker uses backend Secret/Lease locking. If it fails, inspect
only the bounded failure status; do not print state or raw plans. Correct the
declared configuration and change `retryNonce` for a guarded retry. After a
controller restart, its ConfigMap remembers the pending worker Job and exact
original inputs. Never delete the state ConfigMap or backend to clear an error.

Route changes are prepared while this test gateway is suspended. The worker
allows replacement of its Terraform-only hash marker in that state; VM and
retained cloud-resource replacements remain forbidden. While a game is active,
changing routes is blocked until hot route updates exist. Both test routes are
therefore reserved before games start.

The worker image now includes the three public providers selected by the
module's pinned dependency lock. CI verified provider initialization without
networking or credentials. Changing only the worker image triggers a guarded
replan, without changing the gateway's Terraform inputs. Future provider-lock
changes require rebuilding the image against the matching module revision;
there is no runtime registry fallback. The initial image pull still requires
registry access, and Terraform still contacts the cloud APIs.

Suspension retains DNS, IPv4, firewall and SSH-key resources. The retained IP
still has a cost. Full disposal, if requested, must target only this named test
stack with a reviewed Terraform plan, preserve any wanted worlds and avoid the
production state. A complete lab rebuild does not recover this disposable test
backend automatically: recover its protected state first or reconcile its
existing cloud IDs explicitly before rerunning. Do not apply an empty backend
over retained resources. Production activation remains blocked on tested,
protected backend backup and restoration.

For recovery of the disposable test backend, stop the test controller and all
workers, recover the R2 credentials and Restic password through the existing
Bitwarden mapping, restore the verified state-bundle snapshot to protected
temporary storage, inspect only its expected Secret names/namespace, and apply
that bundle to `gaas-state` before resuming any Terraform work. Preserve its
lineage/IDs and discard the plaintext recovery file after use. A restore into
an active namespace requires a reviewed recovery action; the check above only
compares a restored file and does not prove live backend reinstallation. Never
use this test bundle to restore or adopt the production gateway.

The UX proposal is in `pz-server/gaas/portal-design.md`: the existing portal
writes typed changes to Git and reads observed status from Kubernetes/Argo CD.
No portal write integration or GitHub App is installed by these manifests.

The actual portal integration is now implemented and tested on
`bingops-com/portal:feat/game-room-portal`, documented in that repository's
`docs/gaming.md`. `portal-source.txt` pins its source commit for the isolated
image build; `portal-gaming-config.json` restricts it to these two test rooms.
`portal-rbac.yaml` prepares get-only access for the existing portal service
account. These files do not change its production Deployment or install a
GitHub App. Activation requires the dedicated App's public IDs and private-key
Bitwarden mapping, a namespace-local Bitwarden token synchronizer following
the existing PZ pattern, the mounted public config/Secret and the candidate
image. Preserve the production OIDC issuer/client/group and its session PVC.
Do not apply an older portal Deployment from this branch over its current
configuration. The existing layout may be customized on its PVC; do not
overwrite it to add the widget. Add the widget through its editor, or review
an intentional YAML layout change separately.

`portal-smoke.yaml` pins the candidate built from `portal-source.txt`, including
the Git-read cache. Its disposable Pod has no Kubernetes token or GitHub App
key, uses an explicitly invalid OIDC issuer, and expires after ten minutes.
Check `/healthz`, the public login requirement and the anonymous `/api/games`
401 response through a local port-forward. This checks image startup and
authentication enforcement; it does not test a real OIDC login or Git write.
Remove only this named Pod and its public ConfigMap after recording the result.

## First UI using GitHub Actions

`.github/workflows/game-room-state.yml` prepares a small manual form: choose
one of the two isolated rooms and Running/Suspended. It validates the target,
changes only `spec.state` and commits to the acceptance branch. No cloud or
Kubernetes credentials are provided to this workflow. Argo CD and the controller
execute the declared change; workflow success means Git was updated, not that
the game is ready. Use the GameRoom status/observed generation for completion.

The workflow is prepared on this feature branch, not enabled in the default
branch. GitHub requires the dispatch definition on the default branch before
the Actions UI/manual dispatch can be used. Publishing that definition needs
a reviewed merge; no main-branch merge was performed. Its targets remain the
isolated test rooms, even after the workflow definition is published. A future
production version must explicitly choose the operational branch and allowed
rooms after ownership handoff. Direct writes also require branch rules that
permit the workflow token; the workflow never bypasses protection or force
pushes. A concurrent Git edit can reject the push: reread the current state and
retry rather than overwrite it. Token-authored pushes do not start ordinary
push-triggered CI, so the bounded input validation runs before the commit.

References: [manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow),
[token-triggered events](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
