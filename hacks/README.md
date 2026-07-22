# Helper scripts

Expose every executable `hacks/*.sh` helper as a command without the `.sh`
suffix. The default destination is `~/.local/bin`; set `LABOPS_BIN_DIR` to use
another directory. Installation refuses to overwrite unrelated paths.

```sh
task hacks:install
task hacks:check
```

For example, `hacks/deploy.sh` becomes `deploy`. Remove only the symlinks owned
by the current checkout with `task hacks:remove`.

The repository lifecycle also uses
`ansible/proxmox-template-verify.yml` as a read-only gate between the Proxmox
Terraform apply and CAPI workload creation. It ensures template 1234 retains
its Talos ISO on `ide2` while `ide0` remains available for CAPMOX NoCloud data.

## `bootstrap-bitwarden.sh`

Injects or rotates the Bitwarden Secrets Manager machine-account token in every
namespace that consumes external secrets. The helper reads
`BWS_LABTEST_ACCESS_TOKEN` or `BWS_LABPROD_ACCESS_TOKEN` from its process
environment, validates the selected kubectl context and all target namespaces,
then reconciles `bw-auth-token` idempotently. The token is never stored in Git or
placed literally in the command line.

Generate a project-scoped access token from the matching Bitwarden US machine
account, export it in the shell that runs the helper, then execute one cluster at
a time:

```sh
./hacks/bootstrap-bitwarden.sh labtest
./hacks/bootstrap-bitwarden.sh labprod
```

The required namespaces are `argocd-system`, `cert-manager`, and `postgresql`
on `labtest`, and `argocd-system`, `authentik`, `cert-manager`, and `cloudflare`
on `labprod`.
Re-run the same command after token rotation or partial failure. Verify without
revealing the token with `kubectl --context <cluster> --namespace <namespace>
get secret bw-auth-token`; never use `-o yaml` or decode its data.

## `deploy.sh`

Previews the changes that Argo CD would apply to the selected live cluster,
then temporarily points an existing Application at a pushed revision. Select `test` or `prod`; if
`--app` is omitted, every Git-backed workload Application in that environment
is targeted. If `--revision` is omitted, the current Git branch is used.
Every deployment requires typing `yes` after reviewing the diff.

```sh
./hacks/deploy.sh diff test --app portfolio
./hacks/deploy.sh deploy test --app portfolio
./hacks/deploy.sh status test
./hacks/deploy.sh restore test
./hacks/deploy.sh diff prod --revision feature/my-change
./hacks/deploy.sh deploy prod --app portfolio --revision feature/my-change
./hacks/deploy.sh restore prod --app portfolio
```

`--app` is optional for every subcommand; omitting it operates on all matching
Applications. `dev` remains an alias for `test`. `diff` displays one unified
live-to-desired diff per Application, including the Kubernetes object path;
additions are green and deletions are red. It does not print the branch name.
Applications without changes are omitted entirely. `deploy` shows the same
diff before asking for `yes`. `restore` returns
both environments to `master`. Overrides are
recorded on the child Application; the root ignores only `targetRevision` drift
and continues to self-heal every other field. Reapply the corresponding root
bootstrap once after enabling this policy on an existing cluster.

The self-managed `argocd-<cluster>` Application is rendered locally with Helm
and compared through `kubectl diff`; Argo CD core mode cannot authorize new
cluster-scoped resources that are not yet tracked by its own Application. For
that Application, an explicit `--revision` must match the current local branch.

The helper requires `git`, `jq`, `kubectl`, `argocd`, the `labtest` and
`labprod` kubectl contexts, and a remote branch that has already been pushed.
Override context names with `LABTEST_CONTEXT` and `LABPROD_CONTEXT`. For core
mode, it creates a mode-0600 temporary kubeconfig scoped to the selected context
and `argocd-system` namespace, then removes it automatically; the operator's
kubeconfig is never modified.

## `capi-init.sh`

Loads the ignored CAPI Proxmox credentials, requires the expected management
cluster context, installs the provider versions pinned in the repository, and
waits up to ten minutes for the management Kubernetes API before installing the
providers, then waits for their deployments. See
[`capi/README.md`](../capi/README.md) for the token, ACL, and credentials setup
that must be completed first.

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
