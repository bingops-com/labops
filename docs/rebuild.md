# Full infrastructure rebuild

## Ownership

- Terraform owns Proxmox networking, Cloudflare, Tailscale DNS and `labmgmt`.
- CAPI on `labmgmt` owns the sole workload cluster `labprod`.
- Argo CD owns all platform services and workloads on `labprod`.
- Bitwarden owns plaintext application credentials; Git owns their mappings.

## Inputs outside Git

Required recoverable inputs are the Proxmox Terraform and CAPMOX API tokens,
the Tailscale OAuth client, the Cloudflare infrastructure and cert-manager
tokens, the generated tunnel credential, one R2 S3 key restricted to
`bingops-cnpg-labprod`, one R2 S3 key restricted to `bingops-pz-labprod`, the
Project Zomboid Restic repository password, and the `labprod` Bitwarden machine
token. Keep them in the owning password manager or ignored credential file and
rotate them at their provider if lost. Terraform state, kubeconfigs and Talos
configs are sensitive generated state, not documentation.

## Dependency order

1. Restore operator credentials, Proxmox networking and Tailscale routing.
2. Recreate Terraform-owned `labmgmt`; verify Talos and Kubernetes APIs.
3. Initialize pinned CAPI providers and create `labprod`.
4. Install local clients, then bootstrap Argo CD and its production root.
5. Inject the `labprod` Bitwarden machine token into the bootstrap namespaces
   and wait for mappings. Workload token synchronizers, including Project
   Zomboid, then create their namespace-local copy automatically.
6. Apply reviewed Cloudflare DNS, tunnel and the production R2 buckets.
7. Reconcile storage, CloudNativePG and Barman Cloud; verify backup and restore.
8. Reconcile Authentik, observability and workloads; verify Synced/Healthy.
9. Reconcile the private DNS zone `lab.bingo`, Gatus and the LabOps Portal;
   verify `https://lab.bingo` through LAN or Tailscale without publishing it
   through the public Cloudflare Tunnel. The portal image is built from
   `docker/portal`, which clones the `master` branch of `bingops-com/portal`;
   that repository, its public GHCR image and the dispatch token are external
   prerequisites listed in `docker/portal/README.md`. The layout saved from
   the browser lives only on the `portal-data` PVC and is not restored: the
   portal starts from `apps/workloads/portal/base/portal.yaml`.
10. Create the bucket-scoped Project Zomboid R2 token in Bitwarden, reconcile
    its mappings and the workload, then verify a Restic snapshot and a
    disposable restore before retiring the Build 41 VM.

For total VM-disk loss, follow the Proxmox recovery procedure. Never replace
`labmgmt` while it owns `labprod` unless CAPI objects have first been moved.

## Retirement of the former test environment

Retire in this order: confirm the test database backup retention decision,
delete the `labtest` CAPI Cluster while `labmgmt` is available, verify VM 152
and CAPI objects are gone, apply the reviewed Cloudflare plan only after
confirming deletion of `bingops-cnpg-labtest`, and apply the reviewed Tailscale
DNS plan to remove `test.lab.bingo`. Remove obsolete Bitwarden and external R2
credentials only after all consumers are gone.

The operations are idempotent when an already-absent cluster, DNS route or
bucket is treated as absent. Safe verification is based on resource existence,
node readiness and Argo CD health; never print state, kubeconfigs or Secrets.
