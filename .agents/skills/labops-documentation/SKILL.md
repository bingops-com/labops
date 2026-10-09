---
name: labops-documentation
description: Create or reconcile LabOps runbooks and subsystem documentation with the declarative source of truth. Use when configuration changes affect ownership, prerequisites, recovery, operator commands, or application behavior.
metadata:
  short-description: Maintain LabOps runbooks
---

# LabOps documentation

Read `AGENTS.md`, `docs/README.md`, the closest subsystem README and the actual
configuration being documented. Treat manifests and code as evidence; do not
turn chat history, shell history, runtime output or assumptions into a second
source of truth.

Update the closest owning README for local behavior. Update `docs/rebuild.md`
only when reconstruction order, a cross-system dependency, an external input or
a recovery gate changes. Link to the owning runbook instead of copying long
procedures, and remove stale instructions when replacing a workflow.

For every non-Git input, document its classification, purpose, owner, minimum
permissions, safe storage location, creation/rotation procedure, consumers,
recovery source and a non-sensitive verification method. Never include a real
secret, private key, kubeconfig, Terraform state or unsealed Kubernetes Secret.

Operator commands must be copyable on one physical line. Mark commands that
contact live systems and do not present a state-changing command as ordinary
validation. Prefer verification that reports resource status without exposing
Secret values.

Before finishing, compare the documentation with the local diff and answer:
can a new operator rebuild it without chat history, are unrecoverable inputs
and recovery documented, is retry behavior clear, are ownership and ordering
unambiguous, and is verification safe? Report any remaining gap precisely.
