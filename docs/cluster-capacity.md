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

## CPU quota recovery

Node-exporter, Traefik, Portal and the kubelet certificate approver retain CPU
requests and memory limits but have no CPU quota. This permits short bursts on
an otherwise lightly loaded node. Verify `CPUThrottlingHigh` and node CPU load
after rollout; increasing VM memory does not remove container CPU quotas.
The certificate approver bootstrap manifest is maintained in
`capi/manifests/`, attributed to a specific upstream commit and pinned to the
previously running image digest. Both new bootstrap and the existing node's
`cluster.externalCloudProvider.manifests` must reference that Git URL after
publication. Apply the same manifest for an existing deployment; do not rely
on a runtime-only resource patch that a Talos reboot would overwrite.

## Log backlog recovery

The Elasticsearch bootstrap Job installs `labops-log-normalize` and selects it
as the default ingest pipeline for both new and existing log indices. Plain
application `host` strings become `host.name`; plain `log` strings become
`message` (or `labops_original_log` when a message already exists). Existing
objects remain unchanged. This avoids ECS object/scalar mapping errors and
also processes retained Fluent Bit chunks, which a new input filter would not
repair. A retained record rejected with HTTP 400 was accepted with HTTP 201
after normalization. The backlog is replayed in place; never remove its files
to clear an alert. Monitor output records, retries and dropped-record counters
until replay catches up. The existing seven-day Elasticsearch ILM policy is
unchanged. A transient Fluent Bit rollout restart resets blocked tasks while
preserving its host-path queue; its restart annotation is recovery state, not
an additional desired configuration source.

Kubernetes label keys mix legacy `app` labels with dotted
`app.kubernetes.io/name` keys. New ingestions preserve that label map in the
searchable flattened field `kubernetes.labels_flat`, avoiding object/scalar
collisions in existing date-specific mappings. Install the flattened mapping
on existing indices and the index template before enabling that normalization.
Previously indexed documents are unchanged. Fluent Bit retains a 512 MiB
memory limit (128 MiB request) and five-second health probe timeouts for queue
replay; the old 192 MiB limit was reached while the backlog was active.

Fluent Bit allows an 8 MiB Elasticsearch response buffer: the default 512 KiB
buffer truncated bulk replies and retried already-accepted batches. Generated
record IDs still deduplicate retries. Elasticsearch keeps its CPU request,
2 GiB memory limit and fixed heap, but no CPU quota; its former two-core quota
throttled the backlog replay. Verify node CPU pressure alongside the queue.

Replay is background work on the shared eight-core node. Elasticsearch is
configured with `node.processors: 2` and JVM `ActiveProcessorCount=2`, and
Fluent Bit has one output worker. These size application thread pools rather
than imposing a Linux CPU quota. They preserve headroom for other workloads
while the retained backlog drains; steady-state input remains queued safely
with generated IDs and unlimited retries. The heap size is unchanged. Verify
node CPU, accepted records, queue depth and failed/dropped-record counters.

Retained application events also use plain `event` and `error` strings. The
ingest pipeline preserves those as `event.original` and `error.message`,
leaving existing objects unchanged. Validate complete retried chunks with the
read-only ingest/mapping simulation API; sampling only the first record can
miss one invalid document that makes an entire bulk batch retry.
