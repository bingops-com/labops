# Standalone development VM

Status: VM 160 is created and native SSH works over Tailscale. The native
application/services, data migration and Coder retirement are not yet adopted.
Cutover is deferred while work continues in the existing environment. The running Coder
workspace remains the source of operator data until migration acceptance. No
namespace, PVC or old archive may be deleted just because these files exist.

The parallel VM SSH endpoint is **`code.lab.bingo`** (`100.65.212.7`), using
account `dev` on port 22 with Tailscale connected. The private A record is owned
by `apps/platform/private-dns/labprod/configmap.yaml` through the existing
`lab.bingo` tailnet DNS route. No public record or tunnel is created. See the
[DNS ownership and recovery](../network/README.md). The existing
`coder.lab.bingo` and `dev.lab.bingo` endpoints remain on Coder until acceptance.
This SSH endpoint does not imply that native tools, portal or backup services
are already installed; those remain separate acceptance steps.

## Ownership and target

Terraform in this directory owns only Proxmox VM **160**, pool `Development`,
its Debian cloud image and dedicated `dev-vm-snippets` storage. The VM is named
`dev`, with 4 vCPU, 8 GiB RAM and an 80 GiB disk on `local-lvm`. The proposed
underlay address is `192.168.10.170/24`, VLAN 10, gateway `192.168.10.1`.
VM 160 was absent and storage/RAM had capacity during the read-only inventory
on 2026-11-22. Check the address, MAC, VM ID and current capacity again before
creation. An absent ping reply alone does not reserve an address.

This stack has separate state and `prevent_destroy`. It does not clone the
Talos template, change `labmgmt`/`labprod`, or add a CAPI cluster. The existing
[Proxmox prerequisites and API-token recovery](../proxmox/README.md) apply.

Ansible owns the native OS services. `bingops-com/dev` owns portal/gateway/
discovery sources. `environments/dev-vm` owns exact tool versions and public
SSH keys. `build-dev-release.py` packages only explicit public inputs and
npm sidecar locks into a content-addressed release with per-file SHA-256.
The release is installed at `/opt/dev-vm/releases/ID`; `current` selects it.
Projects and personal credentials live in `/home/dev`, UID 1000. The temporary
`/home/coder` compatibility symlink preserves absolute paths recorded in older
personal tool state; no Coder binary, agent, control plane or database is
installed on the VM.

## Access boundary

Tailscale runs directly in the VM. The dedicated nftables table drops SSH,
HTTPS and DNS arriving outside `tailscale0`, including connections reaching
the underlay through a subnet router. Loopback remains available to native
services. SSH uses public keys, account `dev`, no root/password login, and no
LAN/public port-forward. The Proxmox console/guest agent is the recovery path.
First boot masks SSH once, loads the firewall, installs Tailscale and only then
starts SSH. Later reboots do not mask SSH again. A firewall update replaces
only `table inet dev_vm`, preserving Tailscale's own chains.

Initial full acceptance is supervised by `dev-bootstrap.service`, enabled for
boot and retried after failure. It resumes the same verified release after SSH,
controller or VM interruption and stops retrying after writing the private
`initial-acceptance.json` receipt. A failed pre-reboot Restic process leaves a
stale repository lock; initialization removes only locks Restic identifies as
stale, never forces active locks away. Nginx and DNSmasq wait for the enrolled
Tailscale interface and retry failed startup automatically. Their failure does
not block native SSH. Inspect `sudo systemctl status dev-bootstrap` and
`sudo journalctl -u dev-bootstrap` while initial acceptance runs. Starting the
Ansible play schedules this supervised job; a successful Ansible return alone
is not proof that backup/restore acceptance is complete.

The native portal is published at `https://code.lab.bingo`, with previews at
`https://PORT.code.lab.bingo`. The existing `dev.lab.bingo` portal remains on
Coder during parallel acceptance. The native portal/gateway and discovery listen
on loopback ports 8080/4175.
Nginx exposes TLS only through the tailnet and Authentik's verified `bingops`
identity. It overwrites client identity headers. The gateway also checks the
owner, removes SSO credentials before contacting projects, restricts previews
to discovered project ports, and supports WebSockets. Static UI, favorites,
filters and image gallery keep their existing appearance. SSH is the editor/
terminal entry point; a web editor is not required for this migration.

DNSmasq answers only the `code.lab.bingo` zone on the tailnet interface. A
specific Tailscale split-DNS rule can point that zone to the VM during final
cutover; parallel acceptance uses the existing parent route and CoreDNS wildcard.
After the dedicated route is applied, it need not use Kubernetes DNS. The VM uses external resolvers with Tailscale DNS acceptance
disabled, avoiding a self-resolution/bootstrap loop. Authentik remains an
external dependency for browser login; SSH and terminal processes do not depend
on it. The existing ROM proxy and Dev share one declaratively owned embedded
outpost provider list; preserve both when preparing the cutover patch.

## External inputs and recovery

| Input | Owner, permissions, storage and recovery |
| --- | --- |
| Proxmox API token/state | Existing operator token, ignored `terraform/proxmox/credentials.auto.tfvars`; requires VM/pool/image/snippet permissions. Restore the existing state before planning an existing VM. Recover/rotate through the linked Proxmox runbook. |
| Proxmox SSH identity | Existing `bingo` key and verified host trust in the operator home, including passwordless sudo. Needed for snippets and VM checkpoints. Recover from the encrypted operator backup; Git stores public keys only. |
| Tailscale enrollment | Owner's existing tailnet login through the VM console/guest agent. No enrollment secret enters Terraform/cloud-init/Git. Revoke a lost VM in Tailscale and enroll its replacement. Tailnet grants must permit only the intended operator devices/users to TCP 22/443 and UDP/TCP 53. Do not replace the existing policy wholesale. |
| R2 key | Existing bucket-scoped key for `bingops-cnpg-labprod`, recovered from Bitwarden. The new encrypted repository uses only `dev-vm/restic`; old Coder prefixes remain untouched. This shared key cannot be revoked while other workloads depend on it. |
| Restic password | New independent recovery secret, saved in Bitwarden before the first backup, installed as `/etc/dev-vm/restic-password` mode 0600. Keep access outside the VM; without it encrypted archives cannot be restored. Rotation adds/tests a new repository key before retiring the old one. |
| TLS DNS-01 token | Cloudflare `Zone:DNS:Edit` restricted to `lab.bingo`; recover/rotate in Bitwarden/Cloudflare. Install `/etc/dev-vm/cloudflare.ini` mode 0600. It issues wildcard TLS without opening public HTTP or copying a Kubernetes TLS private key. |
| Provider logins | Personal GitHub/Codex/Claude sessions and cluster access migrate encrypted over SSH. Expired/revoked sessions require signing into their original provider. |

The non-sensitive identifiers in `environments/dev-vm/recovery.json` locate the
native VM password and DNS token in the existing Bitwarden project. Recover
inputs with `hacks/prepare-dev-recovery-inputs.py --output PRIVATE_DIRECTORY`
and the operator's external `BWS_ACCESS_TOKEN`. The hashed Python environment
includes the official Bitwarden SDK. It rereads existing keys and refuses to
replace differing local credentials. For initial enrollment only, the explicit
`--use-cluster-token --cloudflare-from-cluster` flags recover the existing
machine token and DNS credential from trusted `labprod` Secrets. They are not
new cluster prerequisites after the keys are safely persisted in Bitwarden.
The helper never prints values or places them in process arguments. Keep the
password secret while any retained Restic repository key depends on it.

`backup.env.example`, `cloudflare.ini.example` and `inventory.ini.example`
contain fake placeholders. Keep real files in ignored `.runtime/dev-vm`, with
mode 0600. Never print environment files, passwords, Terraform state, account
files or command output containing credentials. The new Restic password must
not exist only on the VM or only inside its own encrypted repository.

Recovery secret identifiers are declared in `environments/dev-vm/recovery.json`.
Use `hacks/prepare-dev-recovery-inputs.py --output /private/directory` with an
external `BWS_ACCESS_TOKEN` and the pinned `bitwarden-sdk` dependency. It reads
only the declared recovery values, writes private mode-0600 inputs and refuses
to overwrite differing inputs. Initial enrollment can reuse the trusted cluster
machine token with `--use-cluster-token`; `--cloudflare-from-cluster` is only
needed when enrolling the existing zone-scoped TLS token. The independent
Restic key and TLS token are now durably stored in the declared Bitwarden
project; reconstruction must retrieve these keys rather than generate new ones.
The recovery helper's upstream SDK flow is documented by
[Bitwarden](https://bitwarden.com/help/secrets-manager-sdk/). A complete loss of
both Kubernetes and the VM requires the owner's external Bitwarden account or
recovered machine token; Kubernetes is a bootstrap convenience, not the sole
credential recovery source.

## Preparation and first creation

From the repository root, validate/build the reviewed local sources:

```sh
terraform -chdir=terraform/dev-vm init -backend=false -input=false
terraform -chdir=terraform/dev-vm fmt -check
terraform -chdir=terraform/dev-vm validate
python3 -m unittest discover -s hacks/tests -p test_dev_vm.py -v
ansible-playbook -i 'dev,' ansible/dev-vm.yml --syntax-check
python3 hacks/build-dev-release.py
```

A plan/apply contacts live Proxmox and requires authorization. Save plans/logs
privately, review resource addresses/actions without exposing state, and apply
only the reviewed creation plan. The `-var-file` path is relative to this stack:

```sh
umask 077
mkdir -p terraform/dev-vm/.runtime
terraform -chdir=terraform/dev-vm plan -input=false \
  -var-file=../proxmox/credentials.auto.tfvars -out=.runtime/create.tfplan
terraform -chdir=terraform/dev-vm apply -input=false .runtime/create.tfplan
```

On partial failure, preserve state and replan. If a remote object exists but
was not recorded, verify its identity before an explicit import; never overwrite
an unrelated resource. Cloud-init is reconstruction input, not live OS config.

After cloud-init and QEMU guest agent are ready, enroll Tailscale from Proxmox:

```sh
ssh bingo@192.168.1.100 'sudo qm guest exec 160 -- tailscale up --hostname=dev --accept-dns=false --timeout=5s'
ssh bingo@192.168.1.100 'sudo qm guest exec 160 -- tailscale ip -4'
ssh bingo@192.168.1.100 'sudo qm guest exec 160 -- ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'
```

Complete the owner login using the returned provider URL. Verify the SSH host
fingerprint through the guest agent/console before accepting it on clients.
Use the returned tailnet address, not the underlay address, for SSH/Ansible.
If running from a workspace without Tailscale, an SSH jump through the existing
Proxmox tailnet device can connect to the VM tailnet address; it never opens
underlay port 22. Verify policy permits that exact route.

Prepare and review `hacks/prepare-dev-cutover.py --phase bootstrap --tailscale-ip ACTUAL_IP`.
It writes an ignored patch without applying it. This bootstrap phase adds only
the new Authentik provider and preserves the old Coder login. Use `--phase retire`
after native acceptance to prepare the separate DNS/GitOps/Coder removal patch.
Parallel acceptance uses `code.lab.bingo`; the legacy `dev.lab.bingo` and
`coder.lab.bingo` routes remain active until retirement.

Build a release and supply these non-secret Ansible variables plus the paths
to protected input files:

```yaml
dev_release_id: <the 64-character build identity>
dev_release_archive: /absolute/path/to/ID.tar.gz
dev_backup_env_file: /absolute/private/path/backup.env
dev_restic_password_file: /absolute/private/path/restic-password
dev_cloudflare_credentials_file: /absolute/private/path/cloudflare.ini
```

Run the reviewed `ansible/dev-vm.yml` against the tailnet inventory. Initial
installation creates/verifies the dedicated Restic repository, backs up data,
performs an isolated restoration and only then enables periodic backups.
The health helper tests the VM DNS directly and resolves its HTTPS endpoint
to the tailnet IP explicitly, so initial acceptance does not require switching
production DNS. The additive Authentik bootstrap must already be reconciled. Repeat the same release after partial failure to finish
acceptance; use `devctl update` for later releases.

## Parallel tool installation and live home copy

The initial CLI environment can be installed before portal cutover, without TLS
or backup credentials. Build a verified release as above, then run the same
Ansible play with `dev_tools_only: true`, `dev_release_id` and
`dev_release_archive`. This installs signed native packages, locked Mise/Python
clients, Codex/Claude/Screen system defaults and the SSH tool environment.
`sudo devctl install-tools ID` only accepts an uninitialized VM or a retry of
the same initial tooling release. It cannot replace an active release or adopt
a different tool release without the backup-protected update path.
`/opt/dev-vm/tooling` records this stage; `/opt/dev-vm/current` is reserved for
full native service acceptance. Tooling success is not backup acceptance. Full native activation after a
verified tools-only release requires a full VM checkpoint as well as data
backup/restore. A failed, unverified first bootstrap has no accepted system to roll back to;
it can finish installing services while the initial data upload runs. Acceptance
remains incomplete, and public update commands are refused, until a fresh data
backup and isolated restoration pass after installation. Personal projects are
never reset during this first installation.
A full off-host checkpoint and isolated bootable restore remain required for
final migration acceptance. Subsequent updates keep all checkpoint guards.

Trivy 0.66.0's upstream release assets are no longer available. Its reviewed
OCI image is pinned by digest in `environments/dev-vm/oci-tools.json`, matching
the original workspace image. Installation verifies the multiarchitecture
manifest, Linux/amd64 manifest and every downloaded layer digest, then reads
only the declared binary. Renovate tracks its image tag/digest separately from
the Mise tools. Rebuilds require the public registry mirror, not a private copy
of an old executable. Keep the existing exact-version contract for all tools. Claude explicitly
approves only its own pinned npm postinstall through Mise `allow_builds`; this
materializes its native executable without enabling arbitrary dependency scripts.

While Coder is running, a provisional home copy is supported:

```sh
python3 hacks/migrate-dev-home.py --host ACTUAL_TAILNET_IP \
  --identity ~/.ssh/homeops-proxmox --live-copy
```

A trusted jump host and separate VM host trust can be supplied with
`--proxy-jump bingo@192.168.1.100 --known-hosts /absolute/verified/known_hosts`.
This copies projects, Git metadata, uncommitted files, project dependencies,
personal provider logins, profiles, skills and client configuration. Directory
group/other write bits are removed on the destination to satisfy OpenSSH
StrictModes (the retained source home is 0777); source file modes remain intact. It skips
old workspace SSH-server identities/configuration, transient locks and
Terraform provider/module download caches. Codex SQLite databases use online
SQLite snapshots, including committed WAL changes. Source files and running
processes are never deleted or stopped. File churn is recorded in a private
`live-copy.json`; it never sets `data_verified` or transfers Terraform ownership.
Coder remains the only Terraform runner until a final quiesced synchronization.
Do not make concurrent project edits on both copies. After copying profiles,
retry `sudo devctl install-tools ID` to restore the native shell hook and verify
all clients through a fresh SSH session. Final synchronization requires both
copies' writers to be stopped and any VM edits reconciled first.

## Data migration and final Coder retirement

Freeze project writes and all Terraform operations. Copy the entire operator
home, including uncommitted work, account caches and current local Terraform
states, through `migrate-dev-home.py`; it snapshots active SQLite databases,
refuses changing source data during the rsync verification and deletes nothing
on the source. Preserve real SSH host trust; do not copy the old container SSH
host private key into the VM's new `/etc/ssh` identity.

```sh
python3 hacks/migrate-dev-home.py --host ACTUAL_TAILNET_IP \
  --identity ~/.ssh/homeops-proxmox --confirm-quiesced
```

After final copy, make the VM the sole Terraform runner. Re-run data backup
and isolated restore, and create the first full VM checkpoint. Verify all tools,
private login, HTTP/WebSocket previews, image access, terminal reconnection,
service recovery after restart and SSH refusal from the LAN. Test ordinary
reboot and Tailscale reconnection through the Proxmox console as necessary.
Do not proceed on an unavailable or unverified recovery input.

Apply the reviewed cutover source patch and publish it only after VM acceptance.
It removes `coder-labprod`/`dev-labprod` from the GitOps root, deletes the old
OIDC identities declaratively, removes the legacy Dev DNS route and installs the native Code split route and updates Portal/
Gatus. The old Applications currently have no deletion finalizers, so removing
them does not itself clean up workloads: do not mistake that for retirement.
Complete the retirement receipt with actual data/system snapshot IDs, release
identity and observed checks. Then the guarded helper deletes only the exact
namespaces `coder` and `coder-workspaces`, including Coder, its old Dev
Deployment, CNPG database, retained home PVC, SSH NodePort 30222, ConfigMaps,
credential mappings, bootstrap/sync/backup jobs, ingress, certificates and
namespace-local monitors. This destroys the old live source storage.

```sh
python3 hacks/retire-coder.py --receipt .runtime/dev-vm/retirement.json \
  --confirm coder,coder-workspaces
```

Keep old off-host file/database archives under their retention policy; do not
purge shared R2 buckets, revoke shared credentials or remove shared operators.
Remove obsolete Coder image-update rules and build jobs only after retirement;
existing unrelated/local Coder changes must remain preserved during preparation.
Update the status at the top of this runbook and `docs/rebuild.md` after runtime
acceptance. No infrastructure operation should depend on this chat history.

## Updates, rollback and restoration

Renovate proposes one PR per declared tool, with automatic merge disabled.
The actual updater runs nightly at 03:41 UTC in
`.github/workflows/dev-tools-renovate.yml`, or manually with workflow dispatch.
Its official full container is digest-pinned in `environments/dev-vm/automation.json`
and Renovate maintains that pin too. `.github/renovate-runner.json` restricts it
to this repository's VM environment files; it cannot cut over Coder or update
unrelated workloads. GitHub creates a short-lived token scoped to the repository;
no personal token or App private key is copied into this automation. Actions must
be enabled and repository policy must allow Actions to create PRs (already enabled
on this repository). The workflow declares only contents/PR/issues writes and
Actions permission for dispatching validation. Restore these settings through the
repository's Actions settings after a repository transfer/recreation.

Mise lock refreshes are explicitly allowed in the trusted runner and use its safe
mode, including npm sidecar locks; Python artifacts use Python 3.13. CI rejects
pinned source versions that disagree with their lock files. Because bot pushes
with `GITHUB_TOKEN` do not reliably launch ordinary PR CI, the updater dispatches
the existing read-only validation workflows against its own PR branches. It never
merges them. The runner does not require the development VM or Kubernetes to be
up. See [the Renovate Mise manager](https://docs.renovatebot.com/modules/manager/mise/)
and [GitHub token events](https://docs.github.com/en/actions/concepts/security/github_token).
Trivy metadata comes from Docker Hub, while actual binaries continue to use the
reviewed digest through the public pull mirror; the mirror is not a tag catalog.

Mise handles 15 version-pinned tools and the npm sidecar locks;
the OCI manifest pins Trivy independently; custom Debian
extraction covers every native package, including SSH, Tailscale, DNS and
backup clients. Pip-compile refreshes hashed Python requirements and Ansible
Galaxy tracks collections. The bootstrap Mise release is also versioned.
`kubectl` and `talosctl` remain within the declared cluster minor until an
explicit compatibility change. Self-updaters do not bypass reviewed releases.
After reviewing and merging a tool PR, the normal update is one command:

```sh
sudo dev-refresh
```

It resolves reviewed LabOps `master` to an exact commit, fetches its source in
an isolated root-owned build directory, packages the native app commit pinned in
`environments/dev-vm/app.json`, verifies the immutable release and invokes the
existing checkpoint-protected updater. It runs in systemd independently of SSH
and never resets the personal project checkouts or their uncommitted work.
The existing operator GitHub login supplies source access; no token is included
in the release. `sudo dev-refresh --revision FULL_MERGE_SHA` selects an older
reviewed master commit; commits outside master history are refused. Inspect
`sudo journalctl -u dev-refresh` and `sudo devctl status`.
`--prepare-only` stages and verifies the package without adopting it.

The default release builder also uses the declared app pin, so an empty rebuild
does not accidentally package the still-active legacy Dev master branch.
An explicit `--app /path` is a local preview override, not the reconstruction
source. Keep that source pin until the native Dev PR is merged after cutover,
then update it through a reviewed LabOps change.

For an explicitly prepared local release, build/copy it to
`/opt/dev-vm/releases/ID`, then run:

```sh
sudo devctl update ID
sudo devctl status
```

The updater runs as a transient systemd service, independently of SSH. It
requires a fresh encrypted data backup and a real isolated sentinel/SQLite restore
before installation. Native package, global OCI binary, installer/runtime or configuration changes additionally require
a full `vzdump` checkpoint streamed to encrypted R2; a CLI-only update keeps the
existing OS and uses the verified data snapshot plus retained tool versions.
Any failed prerequisite aborts adoption. Proxmox keeps the last two local VM
archives; R2 retention is separate. No data path is rolled back when a tool or
portal release is reactivated. Previous tool installations/venvs are retained.
A failed update reactivates the previous release. If native packages changed,
the state explicitly says `system-restore-required`: package changes are not
assumed reversible by a symlink swap. Use the full VM restore path below.

Data backups run every four hours and include projects/config/account state,
verified standalone Codex SQLite snapshots, release sources and cached Debian
archives. Integrity/read sampling and isolated sentinel/SQLite restoration run
weekly. Retention keeps seven days of all snapshots, 30 daily, eight weekly and
six monthly snapshots; run `dev-backup retention` with the protected backup
environment during a reviewed maintenance window. Timers/services report
failures through systemd; monitor failed units and last successful backup/restore.
These are data recovery checks, not proof of a full bootable VM restoration.

For selective data restore, load the protected Restic environment in a root
recovery shell with tracing disabled and restore the selected **data** snapshot
to a separate staging directory. Verify files there before replacing live data.
Overlay standalone databases from `var/lib/dev-vm/sqlite/.codex` onto the staged
home only with their owning processes stopped; remove stale WAL/SHM files of
those restored databases. Do not indiscriminately overwrite newer projects.

For full OS recovery, use the last local VM archive from Proxmox, or recover
`vm160.vma.zst` from the recorded **system** Restic snapshot using a separate
recovery computer and Bitwarden credentials. Restore first to an isolated test
VM/network and verify boot/services. A replacement must not run beside the
original with the same IP, MAC, SSH/Tailscale identity or active Terraform
states. Stop the original before restoring it to VM 160. `qmrestore --force`
replaces its disks and requires exact target/impact approval. Restore newer
project files separately from the latest data snapshot if needed, then verify
SSH only over Tailscale, TLS, tools and backups before resuming work.

If both disks and archives are lost, recreate the VM from the pinned Debian
image and Git, re-enroll Tailscale, recover keys from Bitwarden, restore data,
then verify. Old Debian versions may leave rolling repositories: use the cached
signed `.deb` archives from backup or a reviewed manifest update; never silently
substitute an unreviewed version. Rebuilding an empty VM is not data recovery.

## Reconstruction contract and validation

- Rebuild without chat: Terraform, native role, release builder and this runbook.
- Inputs outside Git: the table above owns creation, scope, storage and recovery.
- Partial failure: preserve Terraform state; retry the same content-addressed
  release; checkpoints and data remain independent of the active release.
- Order: Proxmox/network → VM → tailnet → native services → DNS/SSO → data
  migration → verified encrypted backups/restoration → exact Coder retirement.
- Safe checks: Terraform fmt/validate, Ansible syntax/lint, local HTTP/WebSocket
  and browser fixtures, real temporary encrypted Restic backup/restore, SQLite
  WAL acceptance, file checksum tampering and Renovate extraction/validation.
- Runtime checks still required: actual VM boot, tailnet grants and SSH refusal,
  owner SSO, full off-host system checkpoint and isolated bootable VM restore.
