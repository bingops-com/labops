# Task organization

The root [`Taskfile.yml`](../Taskfile.yml) includes one file per lifecycle
owner. Public task names remain stable even though their implementations are
split across files:

| Include | Public namespace | Responsibility |
| --- | --- | --- |
| `proxmox.yml` | `proxmox:*` | Ansible checks and Proxmox host configuration |
| `network.yml` | `network:*` | Persistent VLAN and Tailscale Terraform stack |
| `terraform.yml` | `terraform:*` | Terraform-owned `labmgmt` lifecycle |
| `capi.yml` | `capi:*` | CAPI providers and workload clusters |
| `clients.yml` | `clients:*` | Kubernetes and Talos client configuration |
| `workstation.yml` | `workstation:*` | Operator reachability checks |
| `setup.yml` | `setup:*` | Cross-subsystem setup orchestration |
| `lifecycle.yml` | `lifecycle:*` | Full create, recreate and destroy workflows |

List tasks without contacting infrastructure:

```sh
task --list
```

Inspect a composed workflow without executing it:

```sh
task --summary lifecycle:create
```

Prompts reduce accidental execution but do not replace review. Tasks named
`apply`, `delete`, `destroy`, `recreate`, `setup` or `lifecycle` change live
infrastructure. Review the owning Terraform plan, current Kubernetes context,
exact targets and subsystem README before confirming them. Generated plans,
state, kubeconfigs and credentials remain outside Git.

When adding a task, place it in the file matching its lifecycle owner. Add a
new include only for a new owner or a file that has become independently useful;
do not move a task merely to shorten a small file. Cross-include calls must use
an absolute task name such as `:network:plan`, because unprefixed calls resolve
relative to the including namespace.
