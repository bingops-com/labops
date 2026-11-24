# Retired Gaming as a Service acceptance environment

The dated acceptance environment was retired following the production
handoff. `config.yaml` disables cloud execution, `controller.yaml` keeps the
acceptance controller at zero replicas, and `gitops.yaml` follows the main
branch without automatic synchronization. These files remain outside the
production auto-sync root. Apply them only as the reviewed retirement/bootstrap
operation; never reapply the older feature-branch bootstrap over production.

Only the disposable cloud stack `gaas-test-edge-20261122` is in retirement
scope: IPv4 `91.98.196.54` / primary IP `164378290`, DNS
`pz-gaas-20261122.bingops.com`, its test firewall and test operator SSH key,
and its Terraform-only bootstrap marker. The VM was already removed by the
verified final test suspension. The separate production IPv4
`188.245.252.46` / primary IP `154062800` is retained.

## Retained data and external inputs

Both test GameRooms stay Suspended. Their world PVCs, encrypted R2 world
repositories (`gaas-world-20261122` and `gaas-world-20261122-two`), credentials,
and historical acceptance receipts remain retained. The binary artifact
repository `gaas-releases-20261122` is also used by production and must never
be removed as test cleanup. No namespace, world PVC, GameRoom finalizer or
production resource is deleted by this retirement.
The [2026-11-24 receipt](retirement/receipt-20261124.json) records the exact
saved-plan scope, cloud checks, preserved PVC identities and verified encrypted
before/after bundles. A repeated apply verified the already-retired state
without recreating cloud resources. Its two terminal recovery-check Jobs were
removed after the receipts were retained.

The test backend stays in namespace `gaas-state`, suffix
`gaas-test-20261122-edge`. After successful retirement it has its original
lineage and no managed cloud resources. Its encrypted before/after bundles
remain in R2 repository `gaas-state-backups-20261122`. Recover provider and R2
credentials/passwords through the existing Bitwarden mappings in `access.yaml`
and the PZ workload runbook; no secret value belongs in Git or output.

Terraform exclusively owns the dated cloud resources. The retired test
controller must remain stopped throughout manual maintenance. The acceptance
Argo Application owns only the suspended test-room manifests; production
applications, controller and backend have separate ownership.

## Checked retirement procedure

1. Commit and apply the disabled gateway ConfigMap from `config.yaml`, the
   stopped test controller and `gitops.yaml`. Wait for the controller Pod to
   terminate. Confirm both rooms have current Suspended status, a verified
   shutdown backup where applicable, and no active test writer/cloud Job.
2. Create `retirement/state-before.yaml`, wait for success and read only its
   `GAAS_STATE_RECOVERY_JSON` receipt. It verifies a complete encrypted backend
   backup by restoring/comparing a file; it never installs state in Kubernetes.
3. Run the dated helper against the existing backend:

   ```sh
   python3 terraform/edge-gateway/retire-acceptance.py plan \
     --provider-mirror /protected/path/to/provider-mirror
   python3 terraform/edge-gateway/retire-acceptance.py apply
   python3 terraform/edge-gateway/retire-acceptance.py verify
   ```

   Use the three public provider ZIPs matching the pinned module lock. The
   existing operator images contain that mirror under `/opt/terraform/providers`;
   it can be extracted read-only from the pinned controller image. An existing
   local verified mirror is reusable. Terraform initialization has no registry
   fallback. The helper fetches no credentials from files: it reads only the
   existing test credential Secret into memory.

   The helper extracts tracked module source `f03dc668b3f092e570b8168af07e0b234b8015fc`
   (retained by tag `gaas-gateway-module-v1`) into ignored private storage. A
   shallow checkout must fetch that public commit first. It configures only the
   existing test Kubernetes backend; a saved destroy plan must contain only the
   exact dated resource IDs/names. Production identifiers, VM deletion,
   unrelated resources, creates and replacements are rejected. Provider output,
   plans, state and kubeconfig stay private under
   `.runtime/gaas-test-retire-20261124`, never in Git or chat.
4. Create `retirement/state-after.yaml` after Terraform is idle. Require a
   restored bundle matching the empty test backend, unchanged lineage and zero
   managed instances. Verify the test cloud objects and DNS are absent, the
   production IP remains reserved and all wanted world PVC UIDs remain equal.
5. Record the bounded plan, backup and final verification receipts in the dated
   retirement report. Delete only the named terminal recovery-check Jobs after
   their receipts are retained. Keep the empty backend and wanted worlds.

The helper uses a local process lock and Terraform's backend Lease. Failed
checks stop before applying a changed plan. If apply is interrupted, retain
its private checkpoint and inspect the existing state/cloud inventory before
retrying. `apply` recognizes an already-empty, verified retired stack without
recreating it; `verify` is read-only. A stale plan/state mismatch requires a new
verified backend backup and reviewed plan. Do not clear errors by deleting state.
The ordinary production worker's retained-resource protections are unchanged.

## Recovery and future tests

The older Jobs and manifests in this directory document the 2026-11-22 isolated
acceptance run; they are not an active deployment root. Its historical results
are in `bingops-com/pz-server/operations/gaas-acceptance-20261122.json`.
[Production ownership and recovery](../production/README.md) supersede the old
production-adoption blockers and Portal proposal.

A future test requires an explicitly reviewed new disposable configuration,
its own backend/IDs and a known world seed. Do not enable the old feature-branch
controller or apply an empty backend over existing cloud resources. The retained
worlds and R2 artifacts can be reused after identity/integrity verification.
To recover the retired backend, stop all its writers, restore the selected R2
bundle in protected memory, validate namespace/suffix/lineage and reconcile
actual cloud inventory before installing it. Restoring a historical pre-retirement
bundle does not justify recreating its already-deleted IP/DNS.

A new operator can follow this runbook without chat history. Git owns the
configuration and lifecycle order; Bitwarden/R2 own the sensitive recovery
inputs. Bounded receipts, metadata and the helper's cloud checks provide
verification without exposing secrets. Live backend restoration is a separate
reviewed action; these Jobs test recovery to a file only.
