# Coder development environment

Coder provides the private control plane at `https://coder.lab.bingo`. The `bingops/lab` workspace is intended for persistent experimentation, including the city simulator. Its native OpenSSH endpoint is `coder.lab.bingo:30222`, usable from iSH with the Tailscale iOS app connected.

## Ownership and deployment status

Argo CD owns the `coder-labprod` workload, the retained home PVC, SSH Service and dynamic development ingress, secret mappings and backup schedules. Coder's Terraform template owns only the workspace Deployment. Terraform's network stack owns tailnet DNS. Authentik owns identity and authorization. Bitwarden owns the R2 credential.

PRs #148 and #149 are merged and `homeops-dev:0.1.1` is public and digest-pinned. Runtime checks on 2026-10-14 confirm a Ready workspace, successful automatic setup, Authentik-only login, non-root settings, healthy PostgreSQL, continuous WAL archival, a completed database backup and a completed scheduled home backup. Restore acceptance remains pending. LabOps, Slots and City data and the selected operator inputs were transferred to the retained home. Read-only calls from the workspace verified both Kubernetes clusters, Talos, Proxmox SSH/passwordless sudo and GitHub; all three local Terraform state snapshots match the source. Coder is the primary Terraform runner. The declared template now pins the public 0.1.3 image, which includes Claude and screen. Adoption in the existing workspace requires GitOps reconciliation, automatic template import and an explicit Coder update; runtime acceptance of this image remains pending. A disposable Talos probe confirmed that Codex's filesystem sandbox cannot run with this Pod profile; deprecated Landlock still requires bubblewrap and is not a working fallback. No sandbox or approval bypass is configured.

## Components

| Component | Configuration |
| --- | --- |
| Control plane | Coder v2.36.7, one replica, private HTTPS ingress. |
| Database | Operator-managed `coder-postgresql`, PostgreSQL 18.4, generated `coder-postgresql-app` credential. |
| Database backup | Barman Cloud, WAL archival and daily full backup, `s3://bingops-cnpg-labprod/coder`, generation `coder-postgresql-g1`, 14-day retention. |
| Workspace | `bingops/lab`, Terraform-managed Deployment in `coder-workspaces`, 2 CPU and 4 GiB limits. |
| Home | GitOps-owned `coder-bingops-home`, 20 GiB local-path request, retained from Argo pruning/deletion. |
| SSH | Port 2222 in the pod, private NodePort 30222, public-key authentication only. |
| Development access | `https://dev.lab.bingo`, Coder wildcard port proxy at `*.dev.lab.bingo`, automatic DNS-01 TLS. |
| Image gallery | Read-only project image browser on workspace loopback port 4175, protected by the Coder application proxy. |
| Home backup | Every four hours in UTC to `coder-workspaces/bingops-lab/current`, changed/deleted objects archived for 30 days. |
| Tools | `homeops-dev`: Codex CLI, Terraform, kubectl/Helm, Talos/CAPI clients, Ansible, language/build/test tools, PostgreSQL 18 clients and native SSH. See the [image inventory](../../../docker/homeops-dev/README.md). |
| Automatic setup | A five-minute CronJob provisions the OIDC owner and template once, then preserves the existing workspace. |
| Monitoring | Coder ServiceMonitor, CNPG PodMonitor, Gatus health check and Portal links/backup inventory. |

The persistent home is independent of the workspace lifecycle. Stop, start or replacement must preserve it. The requested local-path size is not a disk quota; track actual node storage and usage.

The container filesystem outside `/home/coder` is replaceable. Keep projects under `~/projects` (also `/opt/homeops`) and personal account/cluster configuration under the home directory. `.codex`, `.claude`, `.claude.json`, `.kube`, `.talos`, `.ssh` and user shell profiles survive ordinary stop/start, Pod replacement and image updates. Coder's workspace Terraform never owns the home PVC; GitOps marks it `Delete=false,Prune=false`. These protections do not recover a deliberately deleted volume or a lost node disk: use the documented R2 restore procedure. A persisted session can still expire or be revoked by its provider.

## Private access

The existing Proxmox Tailscale router advertises `192.168.10.0/24`. Tailnet DNS already sends the `lab.bingo` zone to `192.168.10.160`, which also covers Coder. Private CoreDNS answers Coder with `192.168.10.151`. No additional Tailscale DNS route is necessary.

The Coder ingress permits LAN, tailnet and workspace pod sources. No Cloudflare public DNS record or Tunnel route is added. TLS is issued through the existing DNS-01 issuer. Workspace pods have an explicit host alias for the private Coder name because cluster DNS does not use the tailnet resolver.

Native SSH bypasses the Coder CLI transport and uses the operator's iSH and desktop public keys declared in `base/authorized_keys`. Its NodePort is reachable on the LAN and through the subnet route. No Internet port forwarding is part of this setup. Tailnet ACL ownership remains with the operator; restrict the subnet route to the intended devices/users.

### Development dashboard and read-only workspace access

Open **https://dev.lab.bingo/** for the Coder development dashboard. Its cobalt palette and locally hosted Red Hat fonts follow Portal, Slots and Games; it supports light/dark themes and mobile layouts. The declared workspace is `bingops/lab`, agent `main`, matching the template's single-workspace restriction.

- **Servers:** project-owned HTTP listeners are discovered automatically. Cards show project, runtime, port, response state and `https://PORT.dev.lab.bingo/`; open or copy an address, search, filter by project or save favorites in the browser. Refresh runs every 10 seconds while visible, with manual refresh available.
- **Projects:** only non-hidden project directory names are listed; selecting a project filters its active servers. Inactive projects are not presented as running applications.
- **Coder:** links open the existing workspace dashboard for its terminal and management controls. This dashboard does not execute commands or launch servers.
- **Images:** `https://4175.dev.lab.bingo/` browses permitted raster images in project folders, in read-only mode. It refuses writes, traversal, hidden paths, symlinks, SVG and files over 32 MiB. The home/account configuration is outside its root.
- **Manual ports:** open any non-privileged port 1024–65535 through the short alias, even when automatic discovery does not recognize its service.

#### Authentication and discovery

The landing shell contains public names/links only and remains behind the existing LAN/tailnet/workspace allowlist. Private project and server metadata requires the owner's Coder application session. Without that session, the UI shows a sign-in action rather than fabricated or stale server data. This goes through `https://4175.dev.lab.bingo/_dev/return`, lets Coder/Authentik establish the existing wildcard app cookie, then returns to the dashboard. The return destination is fixed; no redirect URL can be supplied by the caller.

The dashboard's `GET /api/workspace` is forwarded by `base/dev-proxy.mjs` to the fixed Coder-protected `4175` application route `/api/dev/status`. The gateway never calls the workspace directly or holds an account/API token. Coder's login redirects become a JSON 401 for the dashboard, with a separate top-level sign-in link. Non-JSON responses and unavailable/old agents show unavailable state; the gateway does not falsely report an empty healthy workspace. Previously loaded information is marked stale after a failed refresh. Expired authentication clears the private inventory from the UI.

The loopback gallery process also implements discovery in `base/gallery.py`. It reads `/proc/net/tcp{,6}` and same-user socket ownership, associates processes with their working directory under `/home/coder/projects`, then sends a bounded HTTP HEAD to local listeners only. It does **not** read process arguments, environment variables, Git metadata or project/configuration contents. Coder/Codex/Claude, SSH and browser helper processes are excluded. No external hosts are scanned. Non-HTTP sockets and listeners outside project directories are omitted. HTTP services bound exclusively to a non-loopback interface and TLS-only workspace listeners are not automatically detected; the manual port control remains available for compatible Coder routes. Detection is capped at 64 candidate ports, 100 project names and eight concurrent probes, with a five-second cache and a partial-result indicator. Results contain no PID, absolute working directory, command line, credentials or response body.

#### Proxy, TLS and lifecycle

Coder retains `CODER_WILDCARD_ACCESS_URL=*.dev.lab.bingo`. The stateless Node gateway in the existing `coder-dev-portal` Deployment maps short aliases to canonical `PORT--main--lab--bingops.dev.lab.bingo` hosts and streams HTTP/WebSockets through Coder's owner-private application proxy. Same-app Origin/Location and host-scoped cookie headers are translated; unrelated origins and authentication callback parameters remain intact. Canonical URLs stay supported. URLs are never logged because authentication callbacks can contain temporary credentials. A port-only hostname identifies the declared workspace; multiple workspaces require an explicit disambiguation scheme before extending it.

`dev-access.yaml` owns apex/wildcard ingress routes. cert-manager owns `coder/coder-dev-tls` for `dev.lab.bingo` and `*.dev.lab.bingo`, renewed through the existing `letsencrypt-cloudflare` DNS-01 issuer. Private CoreDNS owns apex and one-label wildcard answers to `192.168.10.151`; the `lab.bingo` Tailscale split-DNS route covers them. There is no new credential, public DNS application record, Internet tunnel, per-port Kubernetes Service or workspace volume mount in the dashboard Deployment.

The dashboard HTML/CSS/JS and fonts are mounted from a content-hashed ConfigMap; source changes roll only its stateless Deployment. The gallery/discovery source remains in the `coder-workspace-gallery` ConfigMap, mounted read-only at `/etc/coder-gallery/server.py`; template startup launches it on `127.0.0.1:4175`. An existing workspace can adopt the mount through Coder **Update**, which restarts its processes. To update discovery without restarting the workspace, stop only the existing loopback gallery listener and relaunch the identical committed source in a retained terminal:

```sh
python3 /home/coder/projects/labops/apps/workloads/coder/base/gallery.py --root /home/coder/projects --port 4175
```

The RPG process remains owned by its project (`cd /home/coder/projects/rpg && npm run dev`, port 4173). No proxy starts application processes. Reboot/replacement requires restarting development servers separately. The old dedicated RPG NodePort and `/rpg/` ingress have been replaced by generic aliases.

#### Verification and reconstruction

```sh
node --test hacks/tests/test_coder_dev_proxy.mjs
python3 -m unittest discover -s hacks/tests -p test_coder_gallery.py
node hacks/tests/test_coder_dev_ui.mjs
kubectl kustomize apps/workloads/coder/clusters/labprod > /tmp/coder-render.yaml
```

The browser test uses the real gateway with fixture-only Coder responses, covering six viewports, filtering, favorite persistence, themes, expired sessions, empty inventory and stale state. It needs an installed Chromium or `CHROMIUM_BIN`; no account credentials are used. Captures are local ignored artifacts.

After reconciliation, verify TLS and authentication redirects without printing cookies/query strings; then sign in as the owner. Start a server under a project, wait up to ten seconds for its card, open its short URL, stop it and verify removal. Test a WebSocket dev server and gallery image access. Authentication, unavailable discovery and zero detected servers must remain distinct states.

| Reconstruction question | Answer |
| --- | --- |
| Rebuild without chat history? | Yes: manifests, dashboard, discovery and template startup are declared here; existing workspace adoption is documented above. |
| Inputs outside Git? | No new input. Existing Coder/Authentik accounts, issuer credentials and retained home recovery remain in this runbook's Inputs outside Git and backup sections. |
| Partial failure / repeated operation? | GitOps reconciliation is idempotent; hashed dashboard updates roll automatically. Only one gallery listener may own port 4175. |
| Ownership and order? | Existing DNS/issuer → Coder control plane and ConfigMaps → workspace/gallery → project processes. GitOps owns infrastructure; the owner runs development servers. |
| Safe verification? | Offline fixture tests plus TLS/status checks and owner-session browser checks, without printing tokens or private configuration. |

Kubernetes projects ConfigMap keys under a directory with mode 0777, even on a read-only mount. OpenSSH rejects that directory as an ordinary authorized-keys file path with `StrictModes yes`. The server keeps that check enabled and loads only the declared public keys through `AuthorizedKeysCommand /usr/bin/cat /etc/coder-ssh/authorized_keys`, executed as the existing non-root `coder` user. The command is root-owned in the image and its input is the read-only GitOps ConfigMap; local home keys are not an additional login source.

The current cluster uses Flannel without a NetworkPolicy enforcement controller. Namespace separation and scoped service accounts do not establish network isolation from production services. This workspace is reserved for trusted operator code. Untrusted multi-user execution requires an enforcement layer or a separate cluster before expanding access.

## Identity and administrator

The tracked `coder.yaml` Authentik blueprint declares a public OIDC PKCE client and a `coder-admins` group containing only `bingops` (`therealbingops@gmail.com`). Application policy and Coder's allowed-group check both restrict login. Password authentication and later self-signups are disabled.

Authentik is the sole interactive login provider. The server explicitly disables Coder's built-in GitHub login and default GitHub external-auth connector with `--oauth2-github-default-provider-enable=false` and `--external-auth-github-default-provider-enable=false`. These are CLI flags: the external-auth environment prefix conflicts with Coder v2.36.7's indexed-provider parser. Git and SSH remain available in the workspace; project credentials belong to the persistent user configuration, not the image. This introduces no external credential, account migration or recovery input. After rollout, the public `/api/v2/users/authmethods` response must show GitHub and password disabled and OIDC enabled.

The automatic setup provisions `bingops` as an active OIDC owner before normal login. It uses the official `coder server create-admin-user` recovery/bootstrap command to obtain temporary operator access, then uses the API to create or verify the declared OIDC identity. Its temporary local identity and password are derived in memory, with separate HMAC purposes, from the existing CNPG credential and installation generation. This lets a retry resume a partial attempt without accumulating accounts or requiring a new recoverable secret. The temporary identity is deleted as soon as a fifteen-minute setup token has been issued to the OIDC owner; that token is revoked at completion.

The public control plane keeps password authentication disabled throughout setup. A temporary recovery instance of the same pinned Coder version connects to the same database, binds only `127.0.0.1:18080` inside the setup pod, and runs zero provisioners. It authenticates the temporary identity and exits before any template or workspace operation. It has no Service or ingress. The resulting session is used through the normal control plane API. The permanent `bingops` account remains OIDC with no local password. A completed setup must leave no active `@coder-bootstrap.invalid` identity. Interrupted attempts are cleaned on retry. No OIDC client secret or long-lived setup credential is needed.

Verify the first owner, its login type and the sole group member after login. Do not enable paid role-sync settings as a substitute for this check. Removing group access must also revoke active Coder tokens/sessions and suspend the account if it had previously signed in.

## Inputs outside Git

| Input | Owner and recovery |
| --- | --- |
| Bitwarden machine token | Existing `labprod` bootstrap token; recover/rotate through the Secrets Manager machine account and `hacks/bootstrap-bitwarden.sh`. Two least-privilege sync CronJobs propagate it to the Coder namespaces. |
| R2 access pair | Existing bucket-scoped Object Read and Write credential in the Bitwarden `labprod` project; recover from Bitwarden or replace at Cloudflare and update the mapped values. It is reused for dedicated Coder prefixes, not prefix-isolated from other consumers of the same bucket. |
| Authentik account access | Operator password manager and the Authentik recovery runbook. The public PKCE client adds no shared secret. |
| SSH private keys | Remain on the operator's respective iPhone and desktop devices. Git stores only their public keys in `base/authorized_keys`; add or revoke a device key declaratively there and verify its fingerprint with `ssh-keygen -lf` before publication. Replace/revoke that public key if its device/private key is lost. |
| Coder setup credentials | Generated in memory by the operator-owned job using the existing CNPG application credential. Temporary local identities are deleted and setup tokens revoked; an interrupted token expires after fifteen minutes. No additional recoverable secret is required. |
| Workspace image publication | Existing GitHub Actions package-write token; configure the GHCR package for anonymous read, or recover a scoped pull credential separately. No token is committed. |
| Operator client access | Existing `labmgmt`/`labprod` kubeconfigs and optional Talos config, generated by `hacks/cluster-setup.sh`; recover from the infrastructure state and trusted operator configuration as documented in `hacks/README.md`. Explicit enrollment streams only these contexts into retained home files (0600) and preserves existing defaults. Re-enroll after client credential rotation. No new cluster, role or image credential is created. |
| Codex account | Operator's OpenAI account and its recovery method. First device-code login is completed by the account owner; the auth cache stays in the private retained home. Recover by signing in again, never by baking a token into an image. |
| Claude account | Operator's Claude subscription or Anthropic Console account, with permissions to use Claude Code. The owner completes `claude auth login` after the Claude-containing image is adopted. Linux OAuth credentials stay in `~/.claude/.credentials.json` (0600), settings in `~/.claude` (0700) and `~/.claude.json`; home backups include them. Revoke/rotate through Anthropic or sign in again after loss; no credential is an image/Git input or a Coder login credential. |
| Proxmox operator SSH | Existing private key for `bingo@192.168.1.100`, explicitly selected for enrollment. Recover from protected operator storage or install a replacement public key through the Proxmox administrator. The public host key is declared in `base/proxmox_known_hosts`, obtained through the existing operator connection on 2026-10-14; verify replacements through the Proxmox console/administrator after host reconstruction and update Git. Account and sudo permissions remain unchanged. Other personal SSH keys are excluded. |
| Terraform inputs/state | Ignored `.tfvars` and local state for the `proxmox`, `cloudflare` and `network` stacks. Recover/rotate API credentials through their owning runbooks. Coder is the selected primary runner: finish source operations before transfer and retain source state privately for recovery. Subsequent state revisions depend on the retained-home backup. Never operate two independent state copies against the same infrastructure. |
| CLI sessions/AWS | GitHub/Codex file-based sessions and explicitly selected AWS config/credentials are sensitive user inputs stored only in the private retained home. Recover by signing into their providers and revoke/rotate there. Source process environment, AWS SSO caches and unrelated SSH keys are excluded. |
| CAPI / Authentik recovery files | With `--homeops-root`, existing `capi/credentials.env` and `apps/platform/authentik/credentials/bootstrap-password` are enrolled privately when present. Recover/rotate provider tokens through [CAPI](../../../capi/README.md) and the initial administrator through [Authentik](../../../docs/authentik.md). They remain ignored user files, never image inputs. |

The generated CNPG password, Coder agent token and Terraform state must never be printed or committed. Coder stores its template/state in PostgreSQL. A restored database regenerates namespace application credentials through CNPG.

## Installation order

These steps change live infrastructure and are for the installation authorized by the operator.

1. `homeops-dev:0.1.3` is built in pull requests and published after an authorized merge. Verify anonymous access and pin its published digest before completing runtime acceptance. GitOps may wait for publication. The bootstrap image has its own lifecycle.
2. Integrate the reviewed GitOps changes. Let Authentik and private DNS reconcile before Coder becomes available. The existing parent split route already covers the name.
3. Verify the namespace-local token sync and Bitwarden mappings, then CNPG readiness, Coder health and the certificate.
4. Let `coder-auto-setup` run in `coder-workspaces`. Its first pod binds the retained home and creates the OIDC owner, imports the template, sets default autostop to zero and creates `bingops/lab` with `--stop-after 0h`.
5. Verify that the job completes and leaves only the permanent OIDC owner. Open the private URL through Tailscale and use the normal Authentik login. No manual template import or setup token is required.
6. After the Pod is ready, clone LabOps into `/opt/homeops/labops`, enroll the selected operator access and verify a real CLI task. Migrate local Terraform state before running Terraform there. The image creates no cluster and applies no HomeOps infrastructure automatically.

## Automatic initialization and retries

Terraform creates the workspace Deployment with `wait_for_rollout = false`, as in [Coder's official Kubernetes template](https://github.com/coder/coder/blob/main/examples/templates/kubernetes/main.tf). A successful infrastructure apply permits agent authentication; its blocking startup script then launches SSH. The unchanged TCP readiness probe still reports actual SSH availability. Coder agent/startup state and Kubernetes readiness are separate from the provision-job result. Do not make Terraform completion wait for a probe that depends on its own agent registration, and do not increase the ten-minute timeout to hide this cycle.

CI provisions this real template against a disposable Kubernetes cluster on a GitHub runner, checks agent connection and retained-home initialization, then logs in with a generated SSH key. No cluster is created on Coder or HomeOps infrastructure by that test, and no operator credentials are used.

The CronJob uses a small image containing the pinned official Coder CLI and Python. It can read only its own ServiceAccount metadata and the generated `coder-postgresql-app` Secret. The development container has neither of these permissions nor the bootstrap token. The job retrieves the connection only when initialization is needed and does not write it into the home or its logs.

A file lock on the retained home serializes setup. The non-sensitive marker `.config/lab/bootstrap.json` records the desired definition hash, bootstrap ServiceAccount UID, owner ID and workspace ID. If the definition and installation identity match and the database is initialized, the next run exits without creating credentials or changing the workspace.

The job preserves an existing identity only when its username, email, active status and OIDC login type match the declaration. It refuses to reset a conflicting identity. Template changes are imported and activated. An existing healthy or intentionally stopped workspace is preserved. A failed `start` build is retried with the declared active template and must succeed before a completion marker is written. Adoption of a new image in a running workspace is a deliberate Coder update, so an active simulation is preserved. After merging an image-digest change and GitOps reconciliation, wait for the five-minute setup job to import and activate the template, then select **Update** on `bingops/lab` in Coder. This live operation restarts the workspace and interrupts running processes and SSH sessions while preserving the retained home. Repeating the update after adoption does not require recreating the workspace. After reconnecting, run `homeops-dev-check` to verify installed tool versions without contacting production. Roll back by restoring the previous image digest in Git, reconciling the template and updating the workspace through Coder again.

New installations and rebuilt namespaces have a new ServiceAccount UID and re-run setup against the recovered database. A database-only recovery must update `CODER_BOOTSTRAP_GENERATION` alongside the archive generation. On partial failure, the job retries, removes reserved temporary identities and resumes the missing operations. The reserved `setup-*` identities with the `@coder-bootstrap.invalid` suffix belong exclusively to this process.

The job is scheduled rather than a PostSync hook: its first pod binds the `WaitForFirstConsumer` home PVC, which would otherwise prevent application health and deadlock a hook waiting for it. The current generation and input files are all in Git.

For an authorized immediate retry, first confirm there is no active setup Job, then create one from the declared CronJob:

```sh
kubectl --context labprod -n coder-workspaces create job coder-setup-manual --from=cronjob/coder-auto-setup
```

The manual helper remains available for operator diagnosis after SSO; it is not part of the ordinary setup. It refuses an unpinned image and reads a short-lived token only from environment:

```sh
read -rsp 'Coder session token: ' CODER_SESSION_TOKEN; export CODER_SESSION_TOKEN
```

```sh
CODER_BIN=/path/to/coder ./hacks/setup-coder-workspace.sh
```

```sh
unset CODER_SESSION_TOKEN
```

The optional helper imports the Git-tracked template, sets its default autostop to zero, and creates the single workspace with `--stop-after 0h` if it does not exist. Check an existing workspace's schedule separately; the helper does not silently restart or replace it.

Creating another real workspace name or owner is rejected by the template precondition; Coder's ownerless preview plans are allowed. A stopped workspace is restarted through Coder, not by manually creating a conflicting Deployment.

## Use from iSH

Install an OpenSSH client in iSH if needed, connect the Tailscale iOS app, then run:

```sh
ssh -p 30222 coder@coder.lab.bingo
```

Verify the host-key fingerprint through the operator channel before accepting the first connection. The host key lives in the retained home and is included in backups.

```sh
tmux new -As lab
```

Codex runs on the workspace through this SSH session. For first account enrollment, use [official device-code login](https://learn.chatgpt.com/docs/auth); subsequent runs reuse the private `.codex` directory:

```sh
codex login --device-auth
```

After adopting `homeops-dev:0.1.3`, enroll Claude separately using [its official login flow](https://code.claude.com/docs/en/authentication). Follow the URL/code instructions in the SSH terminal using Safari; retain any verification code privately:

```sh
claude auth login
```

Run `claude` in the desired project. To change accounts use `claude auth logout` followed by `claude auth login`; for Codex use `codex logout` followed by `codex login --device-auth`. Startup preserves those user-owned sessions and settings. Authentik signs you into Coder only. An account login does not verify model execution or sandbox compatibility.

Clone the project once into the persistent directory; an existing checkout is preserved:

```sh
test -d /opt/homeops/labops/.git || git clone https://github.com/bingops-com/labops.git /opt/homeops/labops
```

```sh
cd /opt/homeops/labops && codex
```

The image includes bubblewrap but keeps the current restricted Pod profile. Test actual sandboxed command execution before declaring Codex usable; the [image runbook](../../../docker/homeops-dev/README.md) explains the runtime dependency and links the official container guidance. No automatic sandbox or approval bypass is configured.

The workspace's autostop is disabled. `tmux` preserves a shell and its jobs across iPhone disconnects. A pod replacement or node outage still stops processes; long simulations must checkpoint to the home volume. The current single-node cluster provides persistence and restart, not high availability.

```sh
cd ~/projects
```

```sh
python3 -m venv --system-site-packages city/.venv
```

Python libraries installed in the image are visible to that virtual environment. Additional project dependencies can be installed into the venv and declared in the project. Code, parameters and outputs belong under `~/projects`; caches and venvs can be reconstructed.

## Operator cluster access

Personal Bash aliases can also be enrolled from the trusted source operator host:

```sh
python3 hacks/provision-homeops-dev.py --shell-aliases
```

This copies only the explicitly selected `~/.bash_aliases` into the retained home (0600), adds common Bash shortcuts and appends an idempotent interactive-only loading hook to existing Bash/profile files without replacing their contents. It does not copy the PC's complete shell initialization, environment or history. Differing existing alias files or symlinked profiles make enrollment refuse before writes. Edit `~/.bash_aliases` in Coder for subsequent personal changes, then reload `~/.bashrc` or reconnect. Startup preserves these user-owned files, and the home backup covers them. Recovery comes from that backup or the owner's original alias file; no personal alias definition is committed to Git.

Kubernetes aliases retain their behavior and permissions: enrolling them never executes their commands. Windows paths/tools and unrelated `/opt` checkouts remain PC-specific. If the source's `ls` alias needs unavailable `exa`, the loader uses `eza` when available or GNU `ls`; absent `btop` restores ordinary `top` lookup. This avoids breaking basic shell commands while preserving the original private definitions. Verify names only, without exposing alias values:

```sh
compgen -A alias
```

Run from the trusted operator host after the workspace is ready. This writes personal generated client configuration to the retained home; it does not create a Kubernetes Secret, cluster or role. The helper selects only the existing `labmgmt` and `labprod` identities and never prints them:

```sh
python3 hacks/provision-homeops-dev.py
```

To include the existing Talos client identities, provide their private source file explicitly:

```sh
python3 hacks/provision-homeops-dev.py --talos-config "$HOME/.talos/config"
```

This installs `.kube/homeops-config` and optionally `.talos/homeops-config` with 0600 files and 0700 directories. When no default config exists it creates a `config` symlink; an existing default is preserved. In that case select the generated access explicitly in the SSH session:

```sh
export KUBECONFIG="$HOME/.kube/homeops-config" TALOSCONFIG="$HOME/.talos/homeops-config"
```

Choose the active cluster at any time from the workspace; these commands change only the persisted client selection, not infrastructure:

```sh
kubectl config use-context labprod
```

```sh
talosctl config context labprod
```

Use `labmgmt` instead for the management cluster, or pass `--context` on an individual command. Re-run the cluster-only enrollment command above from the trusted source after credential rotation. It updates the two managed identities and keeps the selected context if still available; it does not transfer or overwrite Claude/Codex sessions. An existing separate default config is still preserved. Additional personal contexts belong in a separate user-owned config, since these generated files manage only `labmgmt`/`labprod`. Credentials are enrolled snapshots: this is not an automatic issuer or rotation service. Do not repeatedly use the full initial migration command, especially its Terraform-state/session options, to refresh cluster access.

Verify without displaying credentials:

```sh
kubectl --context labprod get nodes
```

```sh
kubectl --context labmgmt get nodes
```

The copied operator identities retain their original cluster permissions. They are available to code run by this trusted operator workspace. No ServiceAccount token is automatically mounted. Credential rotation requires running the helper again; reconstruction uses the existing infrastructure recovery and `cluster-setup.sh` paths. These private home files are included in the privileged home backup described below.

## Primary workstation enrollment

Tools in the image do not imply credentials are installed. After the Pod starts, clone LabOps and transfer unpublished project changes separately before enrolling its ignored files. Finish all Terraform operations on the source PC. Run this command from the trusted source host, selecting the existing Proxmox key explicitly:

```sh
python3 hacks/provision-homeops-dev.py --talos-config "$HOME/.talos/config" --proxmox-key "$HOME/.ssh/id_rsa" --cli-sessions --aws-config --homeops-root /opt/homeops/labops --include-terraform-state --confirm-coder-primary
```

The helper streams private data through exec, never logs it and writes files atomically with mode 0600. It validates paths/conflicts before writing and refuses symlinked destinations and differing existing operator files. Kubernetes/Talos generated configs remain refreshable. Missing optional session files are skipped. It requires an existing workspace LabOps checkout before enrolling project credentials/state.

The state flags acknowledge Coder as primary; they do not establish distributed locking or disable Terraform on the old PC. Retain the source snapshot for recovery and perform subsequent Terraform operations only from Coder. A return to the PC requires transferring the latest state back first. Do not run an apply with empty replacement state. Provider caches and saved plans are not transferred; initialize providers normally on the new runner.

The helper installs a dedicated Proxmox key, known-host entry and SSH config. The config becomes the default only when none exists; otherwise select it explicitly. Read-only checks from the workspace:

```sh
ssh -F ~/.ssh/homeops-config proxmox 'hostname; sudo -n true'
```

```sh
gh api user --jq .login
```

```sh
codex login status
```

Copied Codex auth is supported by [official authentication guidance](https://learn.chatgpt.com/docs/auth). Prefer independent sign-ins if both machines continue running Codex, because copied refresh-token caches can diverge. A fresh device-code login is needed only once and persists. Neither enrollment nor startup imports the PC's sandbox/approval settings. GitHub HTTPS credential setup uses `gh auth setup-git`; Authentik governs Coder login only. AWS SSO and credentials provided through process environment require provider-specific enrollment.

This recreates HomeOps tools and selected remote privileges. Linux UID 1000 without sudo, no host Docker socket/daemon and no Windows desktop remain runtime boundaries. Actual Codex sandbox compatibility and a Docker build engine still need acceptance. The owning stack runbooks and the input table above are the recovery sources, not the source PC's shell history.

## Move the existing city design

After the workspace is ready, transfer the local project once from the operator host. Check the destination first and preserve any existing edits:

```sh
kubectl --context labprod -n coder-workspaces exec deployment/coder-bingops-lab -- test ! -e /home/coder/projects/city
```

```sh
tar -C /opt/homeops -cf - city | kubectl --context labprod -n coder-workspaces exec -i deployment/coder-bingops-lab -- tar -C /home/coder/projects -xf -
```

Treat the workspace project as user data protected by its file backup. The local city design is not yet a Git repository; publishing a repository is a separate decision.

## Backup behavior

PostgreSQL has WAL archival and daily full backups through the operator's Barman plugin. Workspace files use the existing private R2 bucket, every four hours, with version archives for changed or deleted objects. Credentials are mounted only into backup jobs, not the development container.

The file backup includes projects, output, personal client configurations (including enrolled kubeconfig/Talos/Codex credentials, Claude's `.credentials.json`, settings and `.claude.json`) and the SSH host key. Caches, package installations and virtual environments are excluded. It is a live file copy, not an atomic filesystem or application snapshot. A running simulator should write checkpoints atomically; a database introduced inside the workspace would need its own consistent backup procedure.

These R2 files use bucket access control and HTTPS; no separate client-side encryption layer is configured. The full home can include personal tokens, so treat its R2 access pair as privileged. More restrictive backup credentials or encryption require a separately recoverable key.

The marker check makes an uninitialized home fail backup rather than silently replace a prior backup with an empty directory. Freeze the CronJob before a deliberate disk-loss rebuild until files are restored and verified. Thirty-day archive pruning must occur only after a successful sync.

## Safe runtime verification

These read-only checks must not expose Secret values:

```sh
kubectl --context labprod -n argocd-system get application coder-labprod
```

```sh
kubectl --context labprod -n coder get deployment,pod,service,ingress,certificate,cluster,backup,scheduledbackup,bitwardensecret
```

```sh
kubectl --context labprod -n coder-workspaces get deployment,pod,pvc,service,cronjob,job,bitwardensecret
```

```sh
dig @192.168.10.160 coder.lab.bingo A +short
```

```sh
curl --fail --resolve coder.lab.bingo:443:192.168.10.151 https://coder.lab.bingo/healthz
```

```sh
kubectl --context labprod -n coder-workspaces exec deployment/coder-bingops-lab -- ssh-keygen -lf /home/coder/.ssh/ssh_host_ed25519_key.pub
```

Check that `coder-postgresql` reports ready, WAL archiving succeeds, a full `Backup` is completed, and the home backup finishes successfully. Confirm SSO accepts bingops and rejects a non-member. Verify SSH, file persistence after a workspace stop/start, and disabled autostop.

## Isolated restore acceptance

The `recovery/` manifests are deliberately excluded from the workload. Apply them only for an authorized acceptance test:

```sh
kubectl --context labprod apply -f apps/workloads/coder/recovery/postgresql-restorecheck.yaml
```

```sh
kubectl --context labprod apply -f apps/workloads/coder/recovery/workspace-restorecheck.yaml
```

The database test recovers into `coder-postgresql-restorecheck`, without archiving into the production generation. Verify readiness and selected non-sensitive row counts against the expected backup. The file test downloads into disposable storage, checks the initialization marker and host key, then verifies the restored objects. Its scratch storage disappears after Job cleanup.

Cleanup of the test database and its PVC requires the operator to verify the exact restorecheck resources; do not delete a production cluster or volume. A completed file Job alone does not demonstrate database recovery.

## Recovery after storage loss

Restore infrastructure and shared operators first, then Bitwarden mappings. Recover the Coder database from the documented Barman generation into a new cluster incarnation with a new archive server name. Update the tracked bootstrap/recovery configuration; never rerun initdb against the existing archive generation.

Keep workspace backup suspended, restore the saved home into its retained PVC, set ownership to UID/GID 1000, and restrict the host key permissions to 0600. Then reconcile Coder, refresh the restored template/state if needed, and start the workspace through Coder. Verify the original project files and host fingerprint before resuming backup.

An archive restore for an earlier point may require reconstructing that point from `current` and the changed/deleted archive objects. The archive is version history, not a sequence of standalone complete snapshots. Document the chosen recovery point before applying changes.

## Local validation

```sh
kubectl kustomize apps/workloads/coder/clusters/labprod >/dev/null
```

```sh
terraform fmt -check terraform/network/dns.tf apps/workloads/coder/base/template/main.tf
```

```sh
bash -n hacks/setup-coder-workspace.sh apps/workloads/coder/base/template/startup.sh
```

Validate the template in an initialized temporary directory without a plan or live provider operations. Build and test the image before importing the template. Authentication, private routing, archive restoration and iSH connectivity require runtime acceptance after deployment.

`coder-bootstrap-test.yml` builds the candidate image and exercises the real installer against disposable Coder and PostgreSQL containers. Only Kubernetes credential lookup is replaced with a test fixture. It verifies the OIDC owner, removal of temporary access, an unchanged second run, and template updates without rebuilding the existing workspace. The real server API must report GitHub/password login disabled and OIDC enabled. This does not replace an actual Authentik sign-in or backup restoration check.
