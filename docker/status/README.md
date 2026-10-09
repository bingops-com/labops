# status

Image build for the public status page of the lab. The source lives in
[`bingops-com/status`](https://github.com/bingops-com/status); this directory
only holds the Dockerfile, which clones the `master` branch of that
repository, builds the React UI, embeds it in the Go binary and ships it on a
distroless base (same pattern as `docker/portal`).

```bash
docker build -t ghcr.io/bingops-com/status docker/status
```

The image contains no configuration: it reads `STATUS_CONFIG`
(`/etc/status/status.yaml`), mounted from the `apps/workloads/status`
ConfigMap, and writes its availability history to `STATUS_DATA` (`/data`).

## Releases

The image workflow publishes `ghcr.io/bingops-com/status` with the tags
`latest`, `sha-<short labops commit>` and a timestamp whenever:

- a push to `master` of the source repository changes its code (it sends a
  `rebuild-image` dispatch; a pull request there builds without publishing);
- a change under `docker/status` reaches `master` here.

A published image is not deployed by itself. Once `deploy-target` exists in
this directory, the workflow opens a pull request (`deploy/status-<tag>`) after
each publication that sets the image of the manifest it names to the new
timestamp tag (`YYYYMMDD-HHmmss`); merging it is the deployment. See
[`docker/portal/README.md`](../portal/README.md) for why the timestamp tag is
the one deployed.

## External prerequisites

| Prerequisite | Purpose | Owner and storage | Verification |
| --- | --- | --- | --- |
| `bingops-com/status` is public | The build clones it anonymously | GitHub organisation owner | `git ls-remote --heads https://github.com/bingops-com/status.git master` |
| GHCR package `status` is public | `labprod` pulls it without a pull secret | Package settings, set once after the first publish | `docker manifest inspect ghcr.io/bingops-com/status:latest` from a logged-out client |
| `REPO_INFRA_TOKEN` secret in `bingops-com/status` | Lets the source repository dispatch `rebuild-image` here | Fine-grained token limited to this repository with `Contents: read and write`, as for `bingops-com/portal`; recreate it in GitHub and store it again as a repository secret to rotate | A code push to `master` of the source starts the "Build and Push Docker image to GHCR" workflow |
| Actions may create pull requests | Lets the image workflow open the deployment pull request | Repository setting **Settings > Actions > General > Allow GitHub Actions to create and approve pull requests**; owner: repository admin | A publication is followed by a `deploy/status-<tag>` pull request |

Without the token the dispatch fails, but a change under `docker/status` still
builds the image. No secret value is stored in this repository.
