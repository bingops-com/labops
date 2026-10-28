# homeops-dev

`ghcr.io/bingops-com/homeops-dev` recreates the operator's development tools for the retained `bingops/lab` Coder workspace. The candidate release is declared in `VERSION`; the template currently pins the published 0.1.3 digest until a reviewed replacement is published. It targets Linux/amd64. `/opt/homeops` points to `/home/coder/projects`, keeping the existing project path while storing user files on the retained home PVC. After GitOps reconciliation and automatic template import, an existing workspace requires an explicit Coder update; image publication alone does not replace it.

## Tools and reproducibility

| Tools | Source / version selection |
| --- | --- |
| Codex CLI | `@openai/codex` 0.165.0; npm lock records integrity, and Renovate follows subsequent releases. |
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
| Browser and common tools | Native Chromium with fontconfig, DejaVu, Liberation and Noto Color Emoji for existing Playwright projects; scientific Python, OpenSSH, screen, tmux, jq, ripgrep, ShellCheck, rsync, DNS/network clients, rclone and Restic. |

Go, Node, Coder and PostgreSQL bases are digest-pinned. `tools.lock.json` records exact upstream downloads and SHA-256 values. The installer verifies bytes before installing a selected binary; it never extracts entire archives. Python dependencies use `--require-hashes`, and npm uses `npm ci`. Distribution packages come from the pinned Debian image's signed package sources; rebuilding may receive package updates, so a new published image digest must be reviewed before adoption. Increment `VERSION` for image changes.

The narrow `.dockerignore` allows only explicit build inputs. No kubeconfig, Talos config, Git credential, Codex/Claude auth cache, private key, project, Terraform state or `.tfvars` is an image input.

### GitOps maintenance

Renovate enables npm maintenance only for `docker/homeops-dev/package.json`, keeping Codex and its lockfile together. Review the dependency PR, increment `VERSION` for the image change, and run the image/SSH acceptance checks before merging. Other tools retain the version/checksum contracts above; npm maintenance does not update `tools.lock.json` or the hashed Python lock.

After publication, a dedicated Renovate manager follows the published `homeops-dev:latest` digest and proposes an update to the digest-only image reference in the Terraform template. The template always remains pinned to immutable bytes. Review and merge that PR, let Argo CD reconcile the template ConfigMap and the existing setup job activate it, then select **Update** in Coder. That last step interrupts running processes/SSH and preserves the retained home. There is no automatic restart of an active workspace.

No manual npm installation inside the running container is needed. Rolling back means restoring the previous digest in Git, reconciling and adopting it through Coder. Existing provider accounts and backup recovery are owned by the Coder runbook; this maintenance adds no credential or external account.

## Runtime and access

### GitOps tool settings

The template directory owns shared, non-sensitive tool settings. Argo CD projects them into both `coder-lab-template` ConfigMaps. The workspace mounts only the selected keys read-only at the standard system paths:

| Source under `apps/workloads/coder/base/template/` | Runtime path | Settings |
| --- | --- | --- |
| `codex.toml` | `/etc/codex/config.toml` | `sandbox_mode = "danger-full-access"`, `approval_policy = "never"`, file-based account storage and startup update checks disabled because Renovate/image releases own updates. |
| `claude.json` | `/etc/claude-code/managed-settings.json` | Image-managed installation with `DISABLE_AUTOUPDATER=1`; no Claude permission bypass is configured. |
| `tmux.conf` | `/etc/tmux.conf` | `tmux-256color`, plain borders/status labels and a 10,000-line history. |

This is the operator-selected Codex container-isolation mode from the [official container guidance](https://learn.chatgpt.com/docs/agent-approvals-security). Codex has access to the mounted home, including operator credentials, and the Pod's network access. The existing non-root UID, seccomp, dropped capabilities and namespace policy remain the outer boundary. Use this dedicated workspace for trusted operator repositories.

Codex's system file provides defaults: explicit user/project/CLI settings can override them, as documented in [configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic). Verify effective permissions in `/status` after starting a new session; a resumed thread can retain its previous permissions. Personal Codex/Claude account caches and preferences stay on the retained home. Startup does not replace them. Claude's managed environment setting has its documented managed-settings precedence, while `~/.tmux.conf` can override tmux's system defaults.

All three files participate in the bootstrap definition hash and template import. Their content checksum annotates the Pod template, so a settings-only edit produces a new active Coder template and a replacement Pod when the owner selects **Update**. The ConfigMap subpath mounts intentionally take effect on that replacement. No image rebuild, manual Pod edit or node setting is needed for a tool-settings-only change. Roll back the source files in Git and adopt the reconciled template again.

The image runs as `coder`, UID/GID 1000, without sudo or password login. The existing workspace startup script serves native SSH on pod port 2222 / private NodePort 30222 using the supplied iSH public key. Its persistent host key, projects and user configuration survive replacement. The development Pod has no automatically mounted Kubernetes ServiceAccount token.

The workspace also requires Dev's `coder-workspace-gallery` ConfigMap and its `server.py` key. Reconcile `dev-labprod` before adopting the template. Startup supervises port 4175 and retries a failed gallery worker after two seconds; the disposable Kubernetes acceptance test verifies recovery without a Pod restart. The owning Coder runbook documents transient recovery for an older workspace that lacks the mount.

The operator explicitly provisions existing `labmgmt` and `labprod` client access with `hacks/provision-homeops-dev.py` after the workspace is ready. It streams credentials through Kubernetes exec, writes mode-0600 generated files under the retained home, preserves existing default configs and never prints credential output. No cluster or role is created. These are the operator's existing permissions, including administrator access where present; this workspace remains reserved for trusted operator code. The retired `labtest` context is excluded.

The image and template start in the real `/home/coder` directory. `/opt/homeops` remains a project-path symlink, but using it as the OCI working directory failed before process startup when the retained home was mounted. CI now exercises that actual mounted-home layout. Optional enrollment also selects the Proxmox SSH key/known host, CLI sessions, AWS files and the three HomeOps stacks' ignored inputs. Local Terraform state transfer requires an explicit primary-runner confirmation; Coder is the selected primary and subsequent operations must not use the old PC's stale copy. The owning runbook gives the recovery and non-sensitive access checks.

Native SSH supplies `LANG=C.UTF-8` and `LC_CTYPE=C.UTF-8`, even when the client does not forward locale variables. Existing personal shell profiles can override them. `homeops-dev-check` verifies the effective UTF-8 character map and checks that the image's monospace, browser and emoji fonts resolve to the installed families. These image fonts serve Chromium and local rendering tools.

Terminal glyphs use the SSH client's own font. For missing prompt icons, the operator can install a monospaced Nerd Font on iOS and select it in iSH's Appearance / Font settings, following the [iSH font instructions](https://github.com/ish-app/ish/wiki/Fonts-in-iSH). This non-sensitive device preference needs no credential and survives workspace reconstruction. Plain `command ls --color=auto` avoids an icon-bearing personal alias without changing the saved alias file.

Codex CLI runs on the remote Linux workspace, not inside iSH. First sign-in is account-specific; the persisted `.codex` directory prevents reconfiguration on ordinary restarts. The startup script seeds only file-based auth storage when no user configuration exists. See [official Codex authentication](https://learn.chatgpt.com/docs/auth) for device-code login from a headless machine. Authentik login to Coder and OpenAI login to Codex are separate identities.

Claude Code also runs remotely. Its Linux login cache is `~/.claude/.credentials.json`; personal settings and history live under `~/.claude`, with additional state in `~/.claude.json`. All are on the retained home volume. Startup creates the private directory without replacing sessions or settings. Sign in once with `claude auth login` and follow its browser instructions; see [official Claude authentication](https://code.claude.com/docs/en/authentication). Account changes and provider-side token revocation remain personal operations. Neither image publication nor Kubernetes/Talos credential enrollment signs the user out. Only exported shell variables disappear with their shell; use the persisted account login rather than relying on a temporary environment variable.

Bubblewrap remains installed for tools that use it, but the declared Codex defaults use the outer Pod isolation and do not request a nested sandbox. CI mounts the same shared settings, reads the effective Codex configuration through its local app-server and executes a synthetic command using those defaults, without an account or model request. This fails acceptance if permissions revert or command execution is broken.

Read-only checks on 2026-10-28 found `user.max_user_namespaces=0` both in the workspace and through the Talos API on `labprod`; `unshare --user --map-root-user true` fails. The workspace also uses `RuntimeDefault` seccomp in a `restricted` Pod Security namespace. These remain compatible with the selected full-access Codex mode. An optional future nested-sandbox design would need to address host namespace limits, syscall filtering and mount behavior; an image rebuild alone cannot enable it. Do not replace the single CAPI-owned control plane to experiment with that alternative. The following diagnostics reveal no credentials but are expected to fail under the current host restrictions:

```sh
cat /proc/sys/user/max_user_namespaces
unshare --user --map-root-user true
codex sandbox -- /usr/bin/true
```

## Delivery and verification

The existing Docker workflow builds and loads this context in PRs and on merge. Before publishing any HomeOps tag it runs the real non-root SSH acceptance script, including `homeops-dev-check` for tool versions, UTF-8 and font resolution. A failed check prevents publication. After an authorized merge, the verified image is published with `VERSION`, source-SHA, timestamp and `latest` tags. First reconciliation may wait for image publication. Verify anonymous access and review the Renovate digest update before completing runtime acceptance. The previous `coder-workspace` digest remains in Git history for rollback. A failed initial workspace start is retried with the active template; healthy or intentionally stopped workspaces are preserved. Adoption in a healthy workspace is an explicit Coder update.

CI exercises a real non-root SSH login, checks that fake personal account settings and projects survive restart with the retained home and unchanged SSH host identity, then runs `homeops-dev-check` through SSH. That command reports tool versions and imports scientific packages without contacting production. The tool-settings check verifies effective full-access defaults and executes a real Codex command without a model; the disposable Kubernetes test exercises the same mounted configuration. A settings-only edit must change the bootstrap hash and import a new active template without rebuilding a healthy workspace. Credential rotation is tested with fake clients and disposable directories; real operator access and iSH routing require verification after delivery.

The owning [Coder runbook](../../apps/workloads/coder/README.md) documents publication, personal setup, credential recovery, backups and single-node limitations.

| Reconstruction question | Answer |
| --- | --- |
| Rebuild without chat history? | Image inputs, npm integrity lock, shared tool settings, image/SSH CI and GitOps adoption are declared here and in the Coder runbook. The selected Codex mode works with the retained host restrictions. |
| Inputs outside Git? | Existing provider accounts and retained-home backup recovery stay in the Coder runbook. Optional iSH font selection belongs to the operator's device and requires no secret. |
| Repeated operation or partial failure? | Builds use locked inputs; startup preserves personal configuration. Shared settings are mounted read-only and participate in the template hash. Import and adoption can be retried without replacing the retained home. |
| Ownership and order? | Renovate proposes source changes; CI builds/publishes; Renovate proposes the published digest; Argo CD reconciles; Coder imports and the owner adopts the template. |
| Safe verification? | Shell/configuration checks, image font checks and synthetic SSH sessions; no real token, model request or infrastructure mutation is needed. |
