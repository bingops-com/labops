# homeops-dev

`ghcr.io/bingops-com/homeops-dev:0.1.2` recreates the operator's development tools for the retained `bingops/lab` Coder workspace. It targets Linux/amd64. `/opt/homeops` points to `/home/coder/projects`, keeping the existing project path while storing user files on the retained home PVC. The template keeps the published 0.1.1 digest until 0.1.2 is published and reviewed for adoption; this image change alone does not replace a running workspace.

## Tools and reproducibility

| Tools | Source / version selection |
| --- | --- |
| Codex CLI | `@openai/codex` 0.162.1, matching the observed operator CLI; npm lock records integrity. |
| Claude Code | Native Linux binary 2.1.287, selected from Anthropic's stable channel; the lock records the release manifest's SHA-256. Background updates are disabled for this image-managed installation, including native SSH sessions. |
| Go / Node / npm | Existing pinned workspace bases: Go 1.26.9 and Node 24. |
| Terraform | 1.10.5, matching the operator host and the repository minimum. |
| kubectl / Helm | 1.36.1 / 3.19.4, matching the cluster and repository CI. `kubectl kustomize` provides rendering. |
| talosctl / clusterctl | 1.13.3 / 1.12.9, matching the operator clients. |
| yq / Actionlint / TFLint | 4.45.1 / 1.7.7 / 0.52.0, matching the operator or repository checks. |
| Ansible / Python checks | Stable ansible-core 2.19.2 instead of the host's development snapshot; ansible-lint, yamllint, pytest, requests and proxmoxer have a hashed dependency lock. `community.general` 11.0.0 matches the installed collection. |
| PostgreSQL clients | 18.4 from the pinned upstream image, matching CNPG; psql, pg_dump and pg_restore are on PATH. No server is launched by the image. |
| Coder / GitHub / Docker | Pinned Coder 2.36.7 plus distribution Git, gh and Docker tools. Docker needs an explicitly configured remote engine; there is no Docker socket, privileged daemon or automatic infrastructure action. |
| Operator delivery tools | Task 3.52.0, kubeseal 0.29.0 and Michael Sauter's Crane 3.6.0 match the existing PC; verified upstream binaries use the lock. Trivy 0.66.0 is copied from a digest-pinned official image because its old GitHub release artifacts are no longer available. AWS CLI comes from signed Debian packages. |
| Browser and common tools | Native Chromium for existing Playwright projects; scientific Python, OpenSSH, tmux, jq, ripgrep, ShellCheck, rsync, DNS/network clients, rclone and Restic. |

Go, Node, Coder and PostgreSQL bases are digest-pinned. `tools.lock.json` records exact upstream downloads and SHA-256 values. The installer verifies bytes before installing a selected binary; it never extracts entire archives. Python dependencies use `--require-hashes`, and npm uses `npm ci`. Distribution packages come from the pinned Debian image's signed package sources; rebuilding may receive package updates, so a new published image digest must be reviewed before adoption. Increment `VERSION` for image changes.

The narrow `.dockerignore` allows only explicit build inputs. No kubeconfig, Talos config, Git credential, Codex/Claude auth cache, private key, project, Terraform state or `.tfvars` is an image input.

## Runtime and access

The image runs as `coder`, UID/GID 1000, without sudo or password login. The existing workspace startup script serves native SSH on pod port 2222 / private NodePort 30222 using the supplied iSH public key. Its persistent host key, projects and user configuration survive replacement. The development Pod has no automatically mounted Kubernetes ServiceAccount token.

The operator explicitly provisions existing `labmgmt` and `labprod` client access with `hacks/provision-homeops-dev.py` after the workspace is ready. It streams credentials through Kubernetes exec, writes mode-0600 generated files under the retained home, preserves existing default configs and never prints credential output. No cluster or role is created. These are the operator's existing permissions, including administrator access where present; this workspace remains reserved for trusted operator code. The retired `labtest` context is excluded.

The image and template start in the real `/home/coder` directory. `/opt/homeops` remains a project-path symlink, but using it as the OCI working directory failed before process startup when the retained home was mounted. CI now exercises that actual mounted-home layout. Optional enrollment also selects the Proxmox SSH key/known host, CLI sessions, AWS files and the three HomeOps stacks' ignored inputs. Local Terraform state transfer requires an explicit primary-runner confirmation; Coder is the selected primary and subsequent operations must not use the old PC's stale copy. The owning runbook gives the recovery and non-sensitive access checks.

Codex CLI runs on the remote Linux workspace, not inside iSH. First sign-in is account-specific; the persisted `.codex` directory prevents reconfiguration on ordinary restarts. The startup script seeds only file-based auth storage when no user configuration exists. See [official Codex authentication](https://learn.chatgpt.com/docs/auth) for device-code login from a headless machine. Authentik login to Coder and OpenAI login to Codex are separate identities.

Claude Code also runs remotely. Its Linux login cache is `~/.claude/.credentials.json`; personal settings and history live under `~/.claude`, with additional state in `~/.claude.json`. All are on the retained home volume. Startup creates the private directory without replacing sessions or settings. Sign in once with `claude auth login` and follow its browser instructions; see [official Claude authentication](https://code.claude.com/docs/en/authentication). Account changes and provider-side token revocation remain personal operations. Neither image publication nor Kubernetes/Talos credential enrollment signs the user out. Only exported shell variables disappear with their shell; use the persisted account login rather than relying on a temporary environment variable.

Bubblewrap is installed. Codex's inner sandbox also requires kernel/container namespace and seccomp support; see [official container guidance](https://learn.chatgpt.com/docs/agent-approvals-security). CI records whether it works under a restricted container without relaxing its profile. The image does not automatically disable Codex sandboxing or approval checks. Actual authenticated Codex execution remains runtime acceptance; if namespace operations are blocked, review a compatible runtime profile or explicitly choose the documented container-isolation mode before relying on it.

## Delivery and verification

The existing Docker workflow builds this context in PRs and publishes `VERSION` after an authorized merge. The initial template references that release; first reconciliation may wait for image publication. Verify anonymous access and pin its published digest before completing runtime acceptance. The previous `coder-workspace` digest remains in Git history for rollback. A failed initial workspace start is retried with the active template; healthy or intentionally stopped workspaces are preserved. Adoption in a healthy workspace is an explicit Coder update.

CI exercises a real non-root SSH login, checks that fake personal account settings and projects survive restart with the retained home and unchanged SSH host identity, then runs `homeops-dev-check` through SSH. That command reports tool versions and imports scientific packages without contacting production. Credential rotation is tested with fake clients and disposable directories; real operator access and iSH routing require verification after delivery.

The owning [Coder runbook](../../apps/workloads/coder/README.md) documents publication, personal setup, credential recovery, backups and single-node limitations.
