# portal

Image build for the private LabOps Portal. The source lives in
[`bingops-com/portal`](https://github.com/bingops-com/portal); this directory
only holds the Dockerfile, which clones the `master` branch of that
repository, builds the React UI, embeds it in the Go binary and ships it on a
distroless base (same pattern as `docker/www`).

```bash
docker build -t ghcr.io/bingops-com/portal docker/portal
```

The image contains no configuration: it reads `PORTAL_CONFIG`
(`/etc/portal/portal.yaml`), mounted from the `apps/workloads/portal`
ConfigMap, and writes the layout saved from the browser to `PORTAL_DATA`
(`/data`).

## Releases

The image workflow publishes `ghcr.io/bingops-com/portal` with the tags
`latest`, `sha-<short labops commit>` and a timestamp whenever:

- a push to `master` of the source repository changes its code (it sends a
  `rebuild-image` dispatch; a pull request there builds without publishing);
- a change under `docker/portal` reaches `master` here.

A published image is not deployed by itself. To roll it out, copy the
timestamp tag (`YYYYMMDD-HHmmss`) from the workflow run or the GHCR package
page into `apps/workloads/portal/base/deployment.yaml` and merge. Prefer it to
`sha-<commit>`: that `sha` is the commit of this repository at build time, so
two source builds without a commit here in between publish the same `sha` tag
and the second overwrites the first. The timestamp tag is unique per build.

## External prerequisites

| Prerequisite | Purpose | Owner and storage | Verification |
| --- | --- | --- | --- |
| `bingops-com/portal` is public | The build clones it anonymously | GitHub organisation owner | `git ls-remote --heads https://github.com/bingops-com/portal.git master` |
| GHCR package `portal` is public | `labprod` pulls it without a pull secret | Package settings, set once after the first publish | `docker manifest inspect ghcr.io/bingops-com/portal:latest` from a logged-out client |
| `REPO_INFRA_TOKEN` secret in `bingops-com/portal` | Lets the source repository dispatch `rebuild-image` here | Fine-grained token limited to this repository with `Contents: read and write`; the same kind of secret `www.bingops.com` uses; recreate it in GitHub and store it again as a repository secret to rotate | A code push to `master` of the source starts the "Build and Push Docker image to GHCR" workflow |

Without the token the dispatch fails, but a change under `docker/portal`
still builds the image.
