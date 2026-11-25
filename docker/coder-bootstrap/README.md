# Coder bootstrap image

> Archived on 2026-11-25 after verified migration and deletion of the old
> `coder` and `coder-workspaces` namespaces. The instructions below describe
> the former environment and must not be used to deploy production. Image
> builds and dependency updates are disabled. Use the [native VM runbook](../../terraform/dev-vm/README.md)
> for `dev.lab.bingo`, current ownership and retained-backup recovery.

This image combines the pinned official Coder CLI with Python's standard library. Its build verifies that the official database recovery/bootstrap command is available. The existing Docker workflow publishes the versioned release to GHCR after merge. The manifest references that initial release; pin its published digest before completing runtime acceptance. Changes to the image require a new `VERSION`.

The application CronJob supplies the script, the generated CNPG application connection, a short-lived Kubernetes identity and a retained home. No credential is baked into the image. The script uses the official CLI and API, retains no local Coder password, and revokes its temporary access after setup. See [the Coder runbook](../../apps/workloads/coder/README.md).
