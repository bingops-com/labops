# LabOps documentation

## Start here

- [Full infrastructure rebuild](rebuild.md): ownership, external prerequisites,
  dependency order and recovery gates.
- [Cloudflare infrastructure](infrastructure/cloudflare.md): DNS and tunnel
  configuration.
- [Talos on Proxmox](../terraform/proxmox/README.md): Terraform-owned management
  cluster.
- [Cluster API](../capi/README.md): CAPI-owned workload clusters.
- [GitOps applications](../apps/README.md): Argo CD, previews, DNS and workloads.
- [Application delivery workflow](gitops-applications.md): create, preview,
  promote, roll back and remove workloads through the current GitOps model.
- [Operator helpers](../hacks/README.md): client configuration and lifecycle
  scripts.

## Agent instructions

Repository-wide behavior belongs in [`AGENTS.md`](../AGENTS.md). Add a nested
`AGENTS.md` only when a subtree needs extra rules; it applies to files below that
directory. Use the prompt itself for a one-off requirement that should not
become repository policy.

Do not use chat history as a runbook. When a prompt reveals a reconstruction
prerequisite, capture it in the owning README and update the rebuild runbook if
it changes dependency order or cross-system recovery.
