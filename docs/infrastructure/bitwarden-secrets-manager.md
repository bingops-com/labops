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
create one machine account per project, grant each account read access only to
its matching project, and generate an access token. Store the tokens in the
organization's protected recovery process or generate replacements after loss.
Revoking and replacing a token is the rotation mechanism; its value cannot be
recovered from Git.

The operator token must exist in the same namespace as each
`BitwardenSecret`. Export the new token only in the shell running the bootstrap
helper, run `hacks/bootstrap-bitwarden.sh` for the corresponding cluster, and
unset it afterward. See [`hacks/README.md`](../../hacks/README.md) for the
idempotent procedure and namespace inventory.

## Migration and recovery order

1. Reconcile the GitOps-declared operator and wait for its deployment and CRD.
2. Create or recover the two Bitwarden projects and least-privilege machine
   accounts, then inject their tokens with the bootstrap helper.
3. Import each existing secret value directly from its authoritative recovery
   source into the matching Bitwarden project; never print or stage values.
4. Commit `BitwardenSecret` mappings using the returned secret UUIDs and
   temporary Kubernetes Secret names.
5. Compare key sets and value hashes between the temporary and current Secrets
   without printing values, then test `labtest` consumers.
6. Change the mappings to the established Kubernetes Secret names and remove
   the corresponding SealedSecrets only after the tested cutover is healthy.
7. Repeat the reviewed cutover for `labprod`; uninstall Sealed Secrets only
   after no SealedSecret resources remain in either cluster or in Git.

During migration, Sealed Secrets deliberately remains installed. Do not allow
both controllers to own the same Kubernetes Secret name concurrently.

## Non-sensitive verification

Verify the operator deployment and CRD are present, each `BitwardenSecret`
reports successful synchronization, and the expected generated Secret names
and key names exist. Compare hashes inside a short-lived local process if a
value comparison is required; never emit Secret YAML, base64 payloads, or
decoded values. Re-running the token bootstrap and allowing Argo CD to reconcile
is safe after partial failure.
