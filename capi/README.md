# Cluster API on `labmgmt`

Terraform creates `labmgmt` and Talos template 1234. CAPI on `labmgmt`
reuses that template and exclusively owns the single workload cluster
`labprod`; never add `labprod` to the Proxmox Terraform cluster map.

`labmgmt` is a lifecycle control plane, not a second application environment.
All workloads, ingress, persistence and observability run only on `labprod`.

`labprod` uses VM 151, node address `192.168.10.151`, API VIP
`192.168.10.160`, 8 cores and 32 GiB. Those addresses and VM ID must be free
before creation and excluded from DHCP. CAPMOX full clones use `local-lvm`.

Create the ignored `capi/credentials.env` from its example, provision the
least-privilege CAPMOX token documented by the Proxmox runbook, and initialize
the pinned providers with `./hacks/capi-init.sh`.

Create and verify the workload:

```sh
kubectl apply -f capi/namespace.yaml
kubectl apply -f capi/clusters/labprod.yaml
clusterctl describe cluster labprod --namespace capi-workloads
```

Then install clients with `./hacks/cluster-setup.sh --workload labprod`.
Changing the immutable machine template can replace the single control plane
and its local disk; use a maintenance and recovery plan for an existing
cluster. Provider IDs are generated state and must not be hardcoded.

The former `labtest` is intentionally absent from Git. Delete its CAPI Cluster
only with explicit confirmation of cluster `labtest`, VM 152 and data loss,
while `labmgmt` is available, then wait for its Machines and VM to disappear.
Never delete `labmgmt` while it owns `labprod`; use `clusterctl move` for a
management-cluster replacement.
