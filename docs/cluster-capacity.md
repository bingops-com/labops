# Existing Talos VM capacity

Desired capacity is declared in `terraform/proxmox/terraform.tfvars` for
Terraform-owned `labmgmt` (VM 150, 8 GiB, 100 GiB disk), and
`capi/clusters/labprod.yaml` for CAPI-owned `labprod` (VM 151, 64 GiB,
500 GiB disk, 8 cores). Proxmox's existing `local-lvm` pool supplies the disks.
Check actual thin-pool capacity, not the capacity of the separate `nvme2-lvm`.

For a new deployment, the owners provision these sizes directly. On an existing
single-node cluster, hardware expansion must preserve the existing VM, disk,
provider UUID and local volumes. Never apply a Terraform replacement or delete
a CAPI Machine to resize it. The versioned machine template is immutable;
`OnDelete` is intentional and prevents capacity/configuration edits from
replacing the only control plane. Subsequent upgrades require a separate plan.

Before any authorized change, verify the VM names, addresses, `scsi0` disk
references and available host RAM using the enrolled Proxmox SSH identity:

```sh
ssh proxmox 'sudo qm config 150; sudo qm config 151; sudo pvesm status --storage local-lvm; free -h'
kubectl --context labmgmt get machines,proxmoxmachines -n capi-workloads
talosctl --context labprod -n 192.168.10.151 get volumeconfig EPHEMERAL
```

Pause neither application reconciliation nor the management cluster. First set
the existing TalosControlPlane rollout strategy to `OnDelete`, then apply the
new ProxmoxMachineTemplate and update its infrastructure template reference.
Keep the old template and Machine: their original immutable allocation is
historical generated state, not a second capacity source. CAPMOX v0.9.0 cannot
update that allocation's disk field; do not bypass its admission validation.

Resize only `local-lvm:vm-151-disk-0` on VM 151. `qm disk resize 151 scsi0
500G` sets an absolute size; check the current size first, skip if already 500G
and stop if larger (never shrink). Talos's default EPHEMERAL has `grow: true`.
Verify `/var` grows; a cold start also reprobes the disk. The local-path PVCs
share `/var`; their requested capacities are not physical quotas.

Set VM 150 to `--memory 8192 --balloon 8192` and VM 151 to `--memory 65536
--balloon 65536`. Matching minimum and maximum avoids reclaiming the requested
RAM through ballooning. Check pending/current settings. A running VM without
memory hotplug requires graceful shutdown followed by start; an OS reboot
alone does not restart QEMU with the new RAM. Never force-stop a timed-out
shutdown. Do one VM at a time and verify its Kubernetes API/Ready condition
before proceeding. Skip the power cycle if current hardware already matches.

Production hosts the Coder workstation: schedule its graceful shutdown/start
from Proxmox (a transient systemd service), not a process running in that VM.
That service must start the same VM only after successful shutdown, preserve
disks and identity, and retain its result in the Proxmox journal. Expect all
single-node applications to be unavailable during this maintenance. Resume
verification after the workspace reconnects; do not bootstrap either cluster.

```sh
talosctl --context labmgmt -n 192.168.10.150 memory
talosctl --context labprod -n 192.168.10.151 memory
talosctl --context labprod -n 192.168.10.151 get volumestatus EPHEMERAL
kubectl --context labmgmt get nodes
kubectl --context labprod get nodes,pods -A
```

Reruns inspect actual capacity and skip completed steps, including cold starts.
Terraform's existing private state remains authoritative for VM 150; refresh it
on the next normal plan, rejecting unrelated/replacement actions. Never create
a second state for that VM. The owner recovers API tokens from the password
manager and SSH/Talos/Kubernetes clients from retained-home enrollment/backups;
see the owning Proxmox, CAPI and Coder runbooks. No new credential is needed.
Verification uses only capacity, readiness and identity, never Secret values.
