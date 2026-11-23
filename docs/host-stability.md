# Homelab restart investigation

The Ryzen 9 5950X host recorded repeated Machine Check errors and unexpected
boot interruptions on 2026-11-21 through 2026-11-23. Errors occurred on logical
CPUs 3, 17 and 19 in banks 1/5. Bank decoding is CPU-specific; these observations
do not establish a failed component or prove an overclock/undervolt. The owner
does not know whether PBO, Curve Optimizer or a memory profile is enabled.
Host logs show no deliberate shutdown for the observed interruptions; HA reports
quorum OK and no managed resources in the inspected status. No stress test ran.

## Reversible mitigation

`ansible/proxmox-stability.yml` restricts its changes to hostname `homelab` and
CPU model `AMD Ryzen 9 5950X`, verifies the kernel's boost interface and installs
`labops-cpu-boost.service`. It disables CPU boost immediately and before guest
startup on subsequent boots. It does not restart guests or the host and does
not change firmware, voltages, RAM timings or machine-check handling. Peak CPU
performance is reduced; this is a mitigation trial, not a root-cause diagnosis.

```sh
ansible-playbook -i ansible/inventories/main/hosts ansible/proxmox-stability.yml --check --diff
ansible-playbook -i ansible/inventories/main/hosts ansible/proxmox-stability.yml --diff
```

Existing operator SSH/sudo access is the only input outside Git; recover it
through the Proxmox administrator's protected credentials. No new key, password
or firmware setting is introduced. Verify the service is active and
`/sys/devices/system/cpu/cpufreq/boost` reads `0`, alongside uptime and filtered
kernel logs. A successful short workload is not proof of long-term stability.
Reapply the role after rebuilding this same host; its guard rejects other CPUs.

To restore boost, change `proxmox_stability_boost_enabled` to `true` in Git,
review the reason and rerun the playbook. The same service then writes `1`.
Do not disable hardware-error reporting or treat quieter logs as a repair.
If interruptions continue, the owner needs to check stock BIOS CPU/RAM settings,
firmware support, power/thermals and hardware with a recovery window; no BIOS
flash or diagnostic stress load is part of this mitigation.

References: [kernel CPU frequency/boost interface](https://docs.kernel.org/admin-guide/pm/cpufreq.html),
[CPU-specific machine-check interpretation](https://docs.kernel.org/arch/x86/x86_64/machinecheck.html).
