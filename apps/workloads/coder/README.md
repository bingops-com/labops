# Coder development environment

Coder provides the private control plane at `https://coder.lab.bingo`. The `bingops/lab` workspace is intended for persistent experimentation, including the city simulator. Its native OpenSSH endpoint is `coder.lab.bingo:30222`, usable from iSH with the Tailscale iOS app connected.

## Ownership and deployment status

Argo CD owns the `coder-labprod` workload, the retained home PVC, SSH Service, secret mappings and backup schedules. Coder's Terraform template owns only the workspace Deployment. Terraform's network stack owns tailnet DNS. Authentik owns identity and authorization. Bitwarden owns the R2 credential.

This change is prepared locally. Image publication, deployment, login, connectivity, backup and restore checks remain pending. Update this paragraph with dated runtime evidence after rollout; a successful local render does not establish operational readiness.

## Components

| Component | Configuration |
| --- | --- |
| Control plane | Coder v2.36.7, one replica, private HTTPS ingress. |
| Database | Operator-managed `coder-postgresql`, PostgreSQL 18.4, generated `coder-postgresql-app` credential. |
| Database backup | Barman Cloud, WAL archival and daily full backup, `s3://bingops-cnpg-labprod/coder`, generation `coder-postgresql-g1`, 14-day retention. |
| Workspace | `bingops/lab`, Terraform-managed Deployment in `coder-workspaces`, 2 CPU and 4 GiB limits. |
| Home | GitOps-owned `coder-bingops-home`, 20 GiB local-path request, retained from Argo pruning/deletion. |
| SSH | Port 2222 in the pod, private NodePort 30222, public-key authentication only. |
| Home backup | Every four hours in UTC to `coder-workspaces/bingops-lab/current`, changed/deleted objects archived for 30 days. |
| Tools | Python with scientific packages, Go, Node/npm, Git, tmux, build tools and OpenSSH. |
| Monitoring | Coder ServiceMonitor, CNPG PodMonitor, Gatus health check and Portal links/backup inventory. |

The persistent home is independent of the workspace lifecycle. Stop, start or replacement must preserve it. The requested local-path size is not a disk quota; track actual node storage and usage.

## Private access

The existing Proxmox Tailscale router advertises `192.168.10.0/24`. Tailnet DNS already sends the `lab.bingo` zone to `192.168.10.160`, which also covers Coder. Private CoreDNS answers Coder with `192.168.10.151`. No additional Tailscale DNS route is necessary.

The Coder ingress permits LAN, tailnet and workspace pod sources. No Cloudflare public DNS record or Tunnel route is added. TLS is issued through the existing DNS-01 issuer. Workspace pods have an explicit host alias for the private Coder name because cluster DNS does not use the tailnet resolver.

Native SSH bypasses the Coder CLI transport and uses the supplied iSH public key. Its NodePort is reachable on the LAN and through the subnet route. No Internet port forwarding is part of this setup. Tailnet ACL ownership remains with the operator; restrict the subnet route to the intended devices/users.

The current cluster uses Flannel without a NetworkPolicy enforcement controller. Namespace separation and scoped service accounts do not establish network isolation from production services. This workspace is reserved for trusted operator code. Untrusted multi-user execution requires an enforcement layer or a separate cluster before expanding access.

## Identity and administrator

The tracked `coder.yaml` Authentik blueprint declares a public OIDC PKCE client and a `coder-admins` group containing only `bingops` (`therealbingops@gmail.com`). Application policy and Coder's allowed-group check both restrict login. Password authentication and later self-signups are disabled.

Coder v2.36.7 supports a public OIDC client and gives the first OIDC user the owner role even when signups are disabled. The first login must therefore be `bingops` through Authentik. No local bootstrap administrator or OIDC client secret is created.

Verify the first owner, its login type and the sole group member after login. Do not enable paid role-sync settings as a substitute for this check. Removing group access must also revoke active Coder tokens/sessions and suspend the account if it had previously signed in.

## Inputs outside Git

| Input | Owner and recovery |
| --- | --- |
| Bitwarden machine token | Existing `labprod` bootstrap token; recover/rotate through the Secrets Manager machine account and `hacks/bootstrap-bitwarden.sh`. Two least-privilege sync CronJobs propagate it to the Coder namespaces. |
| R2 access pair | Existing bucket-scoped Object Read and Write credential in the Bitwarden `labprod` project; recover from Bitwarden or replace at Cloudflare and update the mapped values. It is reused for dedicated Coder prefixes, not prefix-isolated from other consumers of the same bucket. |
| Authentik account access | Operator password manager and the Authentik recovery runbook. The public PKCE client adds no shared secret. |
| SSH private key | Remains on the operator's iPhone. Git stores only its public key; replace that key declaratively if the device/key is lost. |
| Coder session token for template setup | Short-lived generated credential issued to `bingops` after SSO. Keep in process environment, revoke after setup, recreate through authenticated Coder access if needed. |
| Workspace image publication | Existing GitHub Actions package-write token; configure the GHCR package for anonymous read, or recover a scoped pull credential separately. No token is committed. |

The generated CNPG password, Coder agent token and Terraform state must never be printed or committed. Coder stores its template/state in PostgreSQL. A restored database regenerates namespace application credentials through CNPG.

## Installation order

These steps change live infrastructure and are for the installation authorized by the operator.

1. Publish the reviewed workspace image with the existing Docker workflow. Resolve its manifest digest and replace the release-tag reference in `base/template/main.tf` with `ghcr.io/bingops-com/coder-workspace@sha256:...`.
2. Integrate the reviewed GitOps changes. Let Authentik and private DNS reconcile before Coder becomes available. The existing parent split route already covers the name.
3. Verify the namespace-local token sync and Bitwarden mappings, then CNPG readiness, Coder health and the certificate.
4. Open the private URL over Tailscale and sign in as `bingops` through Authentik. Verify the sole owner and create a short-lived setup token.
5. On an operator host with the pinned Coder CLI, run the idempotent workspace helper. It refuses an unpinned image and requires the token only through environment.

```sh
read -rsp 'Coder session token: ' CODER_SESSION_TOKEN; export CODER_SESSION_TOKEN
```

```sh
CODER_BIN=/path/to/coder ./hacks/setup-coder-workspace.sh
```

```sh
unset CODER_SESSION_TOKEN
```

The helper imports the Git-tracked template, sets its default autostop to zero, and creates the single workspace with `--stop-after 0h` if it does not exist. Check an existing workspace's schedule separately; the helper does not silently restart or replace it.

Retrying after partial initialization updates the template and retains the independent home. Creating another name or owner is rejected by the template precondition. A stopped workspace is restarted through Coder, not by manually creating a conflicting Deployment.

## Use from iSH

Install an OpenSSH client in iSH if needed, connect the Tailscale iOS app, then run:

```sh
ssh -p 30222 coder@coder.lab.bingo
```

Verify the host-key fingerprint through the operator channel before accepting the first connection. The host key lives in the retained home and is included in backups.

```sh
tmux new -As lab
```

The workspace's autostop is disabled. `tmux` preserves a shell and its jobs across iPhone disconnects. A pod replacement or node outage still stops processes; long simulations must checkpoint to the home volume. The current single-node cluster provides persistence and restart, not high availability.

```sh
cd ~/projects
```

```sh
python3 -m venv --system-site-packages city/.venv
```

Python libraries installed in the image are visible to that virtual environment. Additional project dependencies can be installed into the venv and declared in the project. Code, parameters and outputs belong under `~/projects`; caches and venvs can be reconstructed.

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

The file backup includes projects, output, configuration and the SSH host key. Caches, package installations and virtual environments are excluded. It is a live file copy, not an atomic filesystem or application snapshot. A running simulator should write checkpoints atomically; a database introduced inside the workspace would need its own consistent backup procedure.

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
