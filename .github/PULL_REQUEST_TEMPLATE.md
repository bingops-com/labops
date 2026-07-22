## Outcome

<!-- State the operator-visible result, not a list of edited files. -->

## Scope discovered from the change

<!-- Keep only the rows that apply. Use the PR Files tab as the source. -->

| Area | Changed ownership or behavior |
| --- | --- |
| Terraform (`terraform/`) | |
| CAPI / Talos (`capi/`, `terraform/proxmox/`) | |
| Ansible (`ansible/`) | |
| GitOps / Argo CD (`apps/gitops/`) | |
| Platform (`apps/platform/`) | |
| Workloads / charts / images | |
| CI, helpers, documentation | |

## Environment and operational impact

- Environments: <!-- labmgmt / labtest / labprod / external service / none -->
- Lifecycle owner: <!-- Terraform / CAPI / Argo CD / external prerequisite -->
- Persistent data affected: <!-- PVC, PostgreSQL, R2, Terraform state, none -->
- External systems affected: <!-- Proxmox, Cloudflare, GitHub, Bitwarden, none -->
- Expected reconciliation after merge: <!-- Describe GitOps/CI consequence or none. -->
- Rollback: <!-- Revert, restore revision, documented recovery procedure. -->

## Validation evidence

<!-- Record commands/checks actually run and their result. Do not paste secrets or sensitive output. -->

| Check | Result |
| --- | --- |
| Offline render, lint, format or syntax checks | |
| `labtest` validation and exact revision | |
| Health or non-sensitive functional verification | |
| Checks intentionally not run | |

## Reproducibility and secrets

- [ ] A new operator can rebuild this change without chat history or shell history.
- [ ] Every non-Git input is classified and its recovery/rotation procedure is documented.
- [ ] Secret values, kubeconfigs, Terraform state and generated credentials are absent from the diff.
- [ ] The operation is idempotent after partial failure or an already-existing resource.
- [ ] Lifecycle ownership and dependency order remain unambiguous.
- [ ] Verification does not disclose sensitive output.

Unrecoverable or manual prerequisites: <!-- Name purpose, owner, minimum permissions, storage, rotation, consumers and verification; otherwise "none". -->

Documentation updated: <!-- Link the owning README/runbook, or explain why no documentation change is required. -->

## Delivery authorization

<!-- Checking a box records what happened; it does not authorize a future live operation. -->

- [ ] No live infrastructure or cluster state was changed.
- [ ] Any temporary live `labtest` change is described above and restored or intentionally retained until merge.
- [ ] Nothing was applied to `labprod` or `labmgmt` outside normal post-merge GitOps reconciliation.
- [ ] This PR is ready for the `deploy/labtest` shared-slot label when applicable.

## Related work

<!-- Use "Closes #123", "Relates to #123", or "None". -->
