# Helper scripts

## `capi-init.sh`

Loads the ignored CAPI Proxmox credentials, requires the expected management
cluster context, installs the provider versions pinned in the repository, and
waits for their deployments. See [`capi/README.md`](../capi/README.md) for the
token, ACL, and credentials setup that must be completed first.

## `cluster-setup.sh`

Installs Kubernetes and Talos client access from the sensitive Terraform
outputs and automatically discovers the `labprod` and `labtest` CAPI clusters.
Each available cluster receives a dedicated kubeconfig with a short context:

```text
~/.kube/lab_mgmt  -> context labmgmt
~/.kube/lab_prod  -> context labprod
~/.kube/lab_test  -> context labtest
```

The files are flattened into `~/.kube/config`, while Talos contexts are merged
into `~/.talos/config`. These are the clients' standard paths, so `kubectl` and
`talosctl` work directly without exports or other environment setup. The script
also maintains an idempotent compatibility block in `~/.bashrc`.

Workload talosconfigs come from the CAPI-generated
`<cluster>-talosconfig` Secrets in `capi-workloads`. The resulting
`~/.talos/config` is rebuilt from the LabOps configurations on every run.

Prerequisites:

- `terraform`, `kubectl`, `jq`, and `clusterctl` in `PATH`;
- a completed Terraform apply for `labmgmt`;
- access to the Terraform state containing the management credentials;
- CAPI running on `labmgmt` to discover workload clusters.

From the repository root:

```sh
./hacks/cluster-setup.sh
kubectl config get-contexts
talosctl config contexts
```

Unavailable default workload clusters are skipped. A workload supplied
explicitly with `--workload` is required and causes the script to fail if its
kubeconfig is unavailable.

Common options:

```sh
# Retrieve management access without checking workload clusters.
./hacks/cluster-setup.sh --management-only

# Require a selected workload cluster.
./hacks/cluster-setup.sh --workload labtest

# Install elsewhere or use another filename prefix.
./hacks/cluster-setup.sh --config-dir "$HOME/.config/kube" --prefix homeops_

# Generate files without changing a shell startup file.
./hacks/cluster-setup.sh --no-bashrc

# Update a different Bash startup file.
./hacks/cluster-setup.sh --bashrc "$HOME/.bash_profile"
```

Files are replaced atomically with mode `0600`. Run
`./hacks/cluster-setup.sh --help` for the complete option reference. Do not
copy generated kubeconfigs into logs or commits: each contains administrator
client credentials.
