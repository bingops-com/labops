# Bitwarden Secrets Manager

Bitwarden Secrets Manager is the target source of application credentials for
the workload clusters. The Bitwarden US organization at `vault.bitwarden.com`
contains two projects:
one dedicated to `labtest` and one dedicated to `labprod`. Each project is
accessible through a distinct machine account and access token. Never grant a
test machine account access to production secrets.

## Ownership and stored state

- Git and Argo CD own the pinned `sm-operator` installation and every
  `BitwardenSecret` mapping.
- Bitwarden US owns secret values, projects, machine accounts, access grants,
  and audit history.
- Project, organization, and secret UUIDs are non-sensitive declarative inputs
  and belong in the corresponding manifests.
- Machine-account access tokens are sensitive bootstrap inputs and never belong
  in Git, Terraform state, Kubernetes YAML, documentation, or shell history.
- Kubernetes owns the generated `Secret` cache and the namespace-local
  `bw-auth-token` bootstrap Secrets. They are reconstructed, not backed up.

The operator is installed from `https://charts.bitwarden.com` at chart version
`2.0.3`, uses the US cloud region, and refreshes every 300 seconds. The chart
Application is declared independently in each cluster app-of-apps directory.

## External prerequisite and recovery

An owner of the Bitwarden US organization must create or recover both projects,
create one machine account per project, grant each account read/write access
only while provisioning or rotating values, then reduce it to read access for
normal operator use. Generate a matching access token and store it in the
organization's protected recovery process or generate replacements after loss.
Revoking and replacing a token is the rotation mechanism; its value cannot be
recovered from Git.

The operator token must exist in the same namespace as each
`BitwardenSecret`. Export the new token only in the shell running the bootstrap
helper, run `hacks/bootstrap-bitwarden.sh` for the corresponding cluster, and
unset it afterward. See [`hacks/README.md`](../../hacks/README.md) for the
idempotent procedure and namespace inventory.

## Recovery order

1. Reconcile the GitOps-declared operator and wait for its deployment and CRD.
2. Create or recover the two Bitwarden projects and least-privilege machine
   accounts, then inject their tokens with the bootstrap helper.
3. Recover each missing value from its authoritative external source into the
   matching Bitwarden project; never print or stage values.
4. Reconcile the committed `BitwardenSecret` UUID mappings and verify their
   status before starting dependent workloads.

Argo CD resolves OIDC secret references only from Secrets labeled
`app.kubernetes.io/part-of: argocd`. The operator does not propagate arbitrary
labels, so each OIDC overlay also declares a metadata-only Secret manifest with
that label. It contains no `data` or `stringData`; Bitwarden remains the sole
owner of the secret value.

## Non-sensitive verification

Verify the operator deployment and CRD are present, each `BitwardenSecret`
reports successful synchronization, and the expected generated Secret names
and key names exist. Compare hashes inside a short-lived local process if a
value comparison is required; never emit Secret YAML, base64 payloads, or
decoded values. Re-running the token bootstrap and allowing Argo CD to reconcile
is safe after partial failure.
