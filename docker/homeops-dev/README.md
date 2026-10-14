# homeops-dev

`ghcr.io/bingops-com/homeops-dev:0.1.0` recreates the operator's development tools for the retained `bingops/lab` Coder workspace. It targets Linux/amd64. `/opt/homeops` points to `/home/coder/projects`, keeping the existing project path while storing user files on the retained home PVC.

## Tools and reproducibility

| Tools | Source / version selection |
| --- | --- |
| Codex CLI | `@openai/codex` 0.162.1, matching the observed operator CLI; npm lock records integrity. |
| Go / Node / npm | Existing pinned workspace bases: Go 1.26.9 and Node 24. |
| Terraform | 1.10.5, matching the operator host and the repository minimum. |
| kubectl / Helm | 1.36.1 / 3.19.4, matching the cluster and repository CI. `kubectl kustomize` provides rendering. |
| talosctl / clusterctl | 1.13.3 / 1.12.9, matching the operator clients. |
| yq / Actionlint / TFLint | 4.45.1 / 1.7.7 / 0.52.0, matching the operator or repository checks. |
| Ansible / Python checks | Stable ansible-core 2.19.2 instead of the host's development snapshot; ansible-lint, yamllint, pytest, requests and proxmoxer have a hashed dependency lock. `community.general` 11.0.0 matches the installed collection. |
| PostgreSQL clients | 18.4 from the pinned upstream image, matching CNPG; psql, pg_dump and pg_restore are on PATH. No server is launched by the image. |
| Coder / GitHub / Docker | Pinned Coder 2.36.7 plus distribution Git, gh and Docker tools. Docker needs an explicitly configured remote engine; there is no Docker socket, privileged daemon or automatic infrastructure action. |
| Browser and common tools | Native Chromium for existing Playwright projects; scientific Python, OpenSSH, tmux, jq, ripgrep, ShellCheck, rsync, DNS/network clients, rclone and Restic. |

Go, Node, Coder and PostgreSQL bases are digest-pinned. `tools.lock.json` records exact upstream downloads and SHA-256 values. The installer verifies bytes before installing a selected binary; it never extracts entire archives. Python dependencies use `--require-hashes`, and npm uses `npm ci`. Distribution packages come from the pinned Debian image's signed package sources; rebuilding may receive package updates, so a new published image digest must be reviewed before adoption. Increment `VERSION` for image changes.

The narrow `.dockerignore` allows only explicit build inputs. No kubeconfig, Talos config, Git credential, Codex auth cache, private key, project, Terraform state or `.tfvars` is an image input.

## Runtime and access

The image runs as `coder`, UID/GID 1000, without sudo or password login. The existing workspace startup script serves native SSH on pod port 2222 / private NodePort 30222 using the supplied iSH public key. Its persistent host key, projects and user configuration survive replacement. The development Pod has no automatically mounted Kubernetes ServiceAccount token.

The operator explicitly provisions existing `labmgmt` and `labprod` client access with `hacks/provision-homeops-dev.py` after the workspace is ready. It streams credentials through Kubernetes exec, writes mode-0600 generated files under the retained home, preserves existing default configs and never prints credential output. No cluster or role is created. These are the operator's existing permissions, including administrator access where present; this workspace remains reserved for trusted operator code. The retired `labtest` context is excluded.

Codex CLI runs on the remote Linux workspace, not inside iSH. First sign-in is account-specific; the persisted `.codex` directory prevents reconfiguration on ordinary restarts. The startup script seeds only file-based auth storage when no user configuration exists. See [official Codex authentication](https://learn.chatgpt.com/docs/auth) for device-code login from a headless machine. Authentik login to Coder and OpenAI login to Codex are separate identities.

Bubblewrap is installed. Codex's inner sandbox also requires kernel/container namespace and seccomp support; see [official container guidance](https://learn.chatgpt.com/docs/agent-approvals-security). CI records whether it works under a restricted container without relaxing its profile. The image does not automatically disable Codex sandboxing or approval checks. Actual authenticated Codex execution remains runtime acceptance; if namespace operations are blocked, review a compatible runtime profile or explicitly choose the documented container-isolation mode before relying on it.

## Delivery and verification

The existing Docker workflow builds this context in PRs and publishes `VERSION` after an authorized merge. The initial template references that release; first reconciliation may wait for image publication. Verify anonymous access and pin its published digest before completing runtime acceptance. The previous `coder-workspace` digest remains in Git history for rollback. A failed initial workspace start is retried with the active template; healthy or intentionally stopped workspaces are preserved. Adoption in a healthy workspace is an explicit Coder update.

CI exercises a real non-root SSH login and runs `homeops-dev-check` through it. That command reports tool versions and imports scientific packages without contacting production. Credentials are tested using fake clients and disposable directories; real operator access and iSH routing require verification after delivery.

The owning [Coder runbook](../../apps/workloads/coder/README.md) documents publication, personal setup, credential recovery, backups and single-node limitations.
