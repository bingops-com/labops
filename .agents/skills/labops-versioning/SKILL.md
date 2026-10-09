---
name: labops-versioning
description: Update or audit pinned versions in LabOps, including container images, Helm charts, Kubernetes components, Terraform providers, Talos, and external Git sources. Use for dependency upgrades, version drift, or release pinning.
metadata:
  short-description: Manage LabOps version pins
---

# LabOps versioning

Read `AGENTS.md` and the owning subsystem README. Run `git status --short`,
preserve unrelated changes, then locate every declaration of the component and
its version before editing.

Determine what the pin controls and who reconciles it. Prefer immutable image
digests or release/commit tags; never replace a stable pin with `latest` or an
equally floating reference. Preserve `master` only where it is the repository's
explicit GitOps production-revision convention, not as an application artifact
version.

Check official upstream release notes and compatibility documentation when an
upgrade is requested. Account for CRD/controller ordering, schema migrations,
supported Kubernetes/Talos versions, chart application versions, database
migrations, and rollback constraints. Do not change adjacent pins merely to
make versions uniform.

Update every repository-owned declaration that must move atomically, including
documentation that names the old version. If the upgrade changes bootstrap,
recovery, external prerequisites or dependency order, update `docs/rebuild.md`.
Do not download dependencies, refresh Terraform state, plan against live
systems, deploy, or push without the required authorization.

Run the narrowest offline validation appropriate to the changed files and
report the exact pin before and after, compatibility evidence, checks not run,
and expected reconciliation or migration impact.
