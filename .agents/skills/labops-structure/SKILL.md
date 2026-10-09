---
name: labops-structure
description: Structure or onboard LabOps infrastructure and GitOps applications while preserving repository ownership boundaries. Use when adding, moving, or substantially reshaping a component in this repository.
metadata:
  short-description: Structure LabOps changes
---

# LabOps structure

Start by reading the repository `AGENTS.md`, the closest subsystem README, and
`docs/gitops-applications.md` for application work. Inspect the existing tree
before choosing a location; preserve established names and the single
`labprod` workload environment.

Route ownership deliberately:

- Terraform owns Proxmox infrastructure and `labmgmt`, plus Cloudflare DNS,
  tunnels and R2 buckets.
- CAPI owns the sole workload cluster, `labprod`.
- Argo CD owns in-cluster platform components and workloads.
- Workload manifests belong under `apps/workloads/<app>/base` with the explicit
  `clusters/labprod` overlay. The matching Argo CD `Application` belongs under
  `apps/gitops/clusters/labprod` and must be included by its kustomization.
- Shared controllers and cluster services belong under `apps/platform` unless
  an established chart-owned location already exists.

For a new application, classify all three concerns in its README and in the
inventory in `docs/gitops-applications.md`: database, Authentik access, and
durable-data recovery. Use CloudNativePG plus Barman/R2 when PostgreSQL is
needed. Use a tracked Authentik provider/application and a dedicated privileged
group for interactive or administrative access. That group must contain only
`bingops` (`therealbingops@gmail.com`). Back up irreplaceable non-database data
to R2; otherwise document why the data is reproducible or disposable.

Identify any required DNS, tunnel, certificate, Bitwarden mapping, monitoring,
portal or rebuild-order change. Keep secret values and generated state out of
Git. Editing configuration never authorizes applying, syncing, or pushing it.

Validate only the affected manifests with offline render/lint commands. Record
the runtime checks needed after an authorized deployment; do not claim that a
render proves database connectivity, SSO authorization, or backup restoration.
