# Portal image publication

`portal-release.yml` reads the full public source SHA from `source.txt`, builds
this Dockerfile with `PORTAL_SOURCE_REF`, publishes an immutable GHCR digest,
and smoke-tests `/healthz`. On `master` it promotes only the Deployment image
in a non-force Git commit. A concurrent edit rejects the push; rerun from the
current branch rather than force-pushing. Feature-branch builds publish an
artifact only. The recorded artifact contains the image digest and source SHA.

The old `deploy-target` marker and cross-repository `REPO_INFRA_TOKEN` dispatch
are retired for Portal. Publication uses LabOps' own `GITHUB_TOKEN` with package
write and contents write for the promotion commit. No new long-lived CI token
is required. Generic Docker builds may publish tags, but production follows the
reviewed source pin and the digest promoted by `portal-release.yml`.

The source repository and GHCR package remain public for anonymous source
fetches and cluster image pulls. Recover access through the GitHub organisation
administrator if either visibility changes. Configuration, OIDC settings and
the retained `portal-data` session/layout volume belong to the workload runbook;
no application configuration or private key is baked into the image.
