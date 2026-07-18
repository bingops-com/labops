# LabOps agent instructions

## Scope and purpose

This repository is the source of truth for a home-lab infrastructure and its
GitOps-managed workloads. It contains Terraform, Ansible, Kubernetes/Kustomize,
Helm, Argo CD, Talos, Proxmox, Cloudflare, and Cluster API configuration.

These instructions apply to the whole repository. A more deeply nested
`AGENTS.md` may add or override instructions for its subtree.

## Repository map

- `terraform/proxmox/`: Proxmox resources and the Talos management cluster
  (`labmgmt`). Terraform owns the management cluster, not the CAPI workload
  clusters.
- `terraform/cloudflare/`: Cloudflare DNS and tunnel infrastructure.
- `capi/`: Cluster API configuration for `labprod` and `labtest`.
- `apps/`: Kustomize bases and cluster overlays reconciled through GitOps.
- `apps/gitops/`: Argo CD projects and applications.
- `charts/`: locally maintained application Helm charts.
- `ansible/`: host bootstrap and configuration roles.
- `hacks/`: operator helper scripts; some consume sensitive Terraform and
  Kubernetes outputs and write user-level client configuration.
- `docs/`: operator and infrastructure documentation.

Read the closest relevant README before changing a subsystem. In particular,
read `terraform/proxmox/README.md`, `capi/README.md`, and `hacks/README.md`
before work involving their respective lifecycles.

## Safety boundary

- Treat production, preproduction, management clusters, Proxmox, Cloudflare,
  DNS, tunnels, persistent storage, and Terraform state as live infrastructure.
- Editing configuration does not authorize applying or deploying it.
- Do not run state-changing infrastructure or cluster commands unless the user
  explicitly requests that action. This includes `terraform apply`,
  `terraform destroy`, `terraform import`, `terraform state` mutations,
  `kubectl apply`, `kubectl delete`, `kubectl patch`, `helm install/upgrade`,
  `argocd app sync`, `clusterctl init/move/delete`, and Ansible playbooks without
  `--check`.
- Do not push, merge, or open a pull request unless explicitly requested. A push
  may trigger GitOps reconciliation and therefore constitutes a deployment.
- Plans and dry runs are not automatically harmless: they may contact live
  systems, refresh state, execute data sources, or expose sensitive output.
  Ask before running them when credentials or a live endpoint are involved.
- Never destroy or replace a cluster, VM, disk, resource pool, DNS record,
  tunnel, namespace, persistent volume, or secret without explicit confirmation
  of the exact target and expected impact.
- Never delete `labmgmt` while it owns workload clusters. A management-cluster
  replacement requires a documented `clusterctl move` procedure first.
- Keep lifecycle ownership separate: Terraform owns `labmgmt`; CAPI owns
  `labprod` and `labtest`. Do not add the workload clusters to the Proxmox
  Terraform `clusters` map.

## Secrets and sensitive data

- Never print, copy into chat, commit, or include in patches any credentials,
  tokens, private keys, kubeconfigs, talosconfigs, Terraform state, unsealed
  Kubernetes Secrets, or sensitive command output.
- Do not inspect secret-bearing files unless the task genuinely requires it.
  Known sensitive locations include `*.tfvars`, `*.auto.tfvars`, Terraform
  state, `terraform/cloudflare/credentials`, kubeconfigs, talosconfigs, and
  local environment files.
- Keep real credentials in ignored files or environment variables. Examples and
  documentation must use unmistakably fake values.
- Kubernetes secrets committed to Git must be encrypted/sealed. Do not replace a
  SealedSecret with a plaintext Secret.
- Before handing off a change, check that newly added files do not contain
  secrets or generated client configuration. Do not weaken `.gitignore`
  protections without explicit justification.

## Working practices

- Start with `git status --short`. The worktree may contain user changes; keep
  them intact and do not revert, overwrite, reformat, or include unrelated work.
- Inspect before editing and keep changes narrowly scoped to the request.
- Preserve existing names, directory layout, cluster/environment separation,
  and pinned versions unless the task requires a change.
- Prefer declarative changes. Do not make an ad-hoc live fix when the repository
  should remain the source of truth.
- Production and preproduction overlays must remain explicit. Do not copy a
  preproduction value into production without verifying its operational impact.
- Do not edit vendored/generated Helm chart contents under `apps/**/charts/`
  unless the task specifically targets the vendored chart. Prefer the owning
  values file, Kustomize overlay, or locally maintained chart under `charts/`.
- Update the relevant README or runbook when changing lifecycle ownership,
  prerequisites, operator commands, addresses, IDs, or recovery procedures.
- Diagnose requests authorize read-only investigation and an explanation, not a
  fix. Review requests authorize findings, not repository changes.

## Validation

Run only checks relevant to the files changed. Prefer offline, read-only checks;
do not install dependencies or download chart/provider artifacts without
permission.

- Terraform: run `terraform fmt -check` on the affected stack. Run
  `terraform validate` only when that stack is already initialized and doing so
  will not require network access. Do not run a plan against live infrastructure
  without permission.
- YAML: run `yamllint` on changed first-party YAML when available. Exclude
  vendored chart content unless it was intentionally changed.
- Kustomize: render the affected base/overlay with `kustomize build` or
  `kubectl kustomize` when available. A render is validation only; never pipe it
  into `kubectl apply`.
- Helm: run `helm lint` and/or `helm template` for changed locally maintained
  charts when dependencies are already present.
- Ansible: use syntax/lint checks where available. A check-mode playbook still
  contacts hosts, so ask before running it against inventory.
- Shell: run `bash -n` for changed Bash scripts and `shellcheck` when available.

If a check cannot be run safely or a required tool/dependency is unavailable,
report that clearly instead of substituting a live operation.

## Completion report

Summarize the files changed, validation performed, validation not performed,
and any operational consequence or manual follow-up. Explicitly state whether
anything was applied, deployed, pushed, or otherwise changed outside the local
worktree.
