# Isolated Gaming as a Service acceptance

These manifests are intentionally outside the production Argo root. They are
the declared inputs for the user-authorized isolated acceptance run, not an
adoption of the active Project Zomboid StatefulSet or existing edge gateway.
The controller/CRD/runtime source is on the `pz-server` repository's
`feat/gaming-as-a-service` branch; its `gaas/README.md` owns the lifecycle design.

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
- `world-seed*.yaml` restore a known production snapshot into `emptyDir`,
  verify SQLite integrity and seed two separate test repositories. They never
  mount the production PVC. `gaas-pz-*.yaml` reference these repositories and
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
   these two GameRooms. Start one room, test its public UDP endpoint, start a
   second, suspend the first and confirm the gateway remains, then suspend
   the second. Require a current verified backup receipt for each world.
   Resume and verify the retained IP and world. The final desired state in
   the two manifests is Suspended. Do not put this test into an auto-sync root.
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
