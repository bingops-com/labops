# portal

Image build for the private LabOps Portal. The source lives in
[`bingops-com/portal`](https://github.com/bingops-com/portal); this directory
only holds the Dockerfile, which clones the `master` branch of that
repository, builds the React UI, embeds it in the Go binary and ships it on a
distroless base (same pattern as `docker/www`).

```bash
docker build -t ghcr.io/bingops-com/portal docker/portal
```

The build writes the source commit to `/version.txt`, which the portal shows
in its footer. The image contains no configuration: it reads `PORTAL_CONFIG`
(`/etc/portal/portal.yaml`), mounted from the `apps/workloads/portal`
ConfigMap, and writes the layout saved from the browser to `PORTAL_DATA`
(`/data`).

## Releases

The image workflow publishes `ghcr.io/bingops-com/portal` with the tags
`latest`, `sha-<short labops commit>` and a timestamp whenever:

- a push to `master` of the source repository changes its code (it sends a
  `rebuild-image` dispatch; a pull request there builds without publishing);
- a change under `docker/portal` reaches `master` here.

A published image is not deployed by itself. After each publication the
workflow opens a pull request (`deploy/portal-<tag>`) that sets the image of
the manifest named in `deploy-target` to the new timestamp tag
(`YYYYMMDD-HHmmss`); merging it is the deployment, closing it skips the build.
The timestamp tag is used rather than `sha-<commit>` because that `sha` is the
commit of this repository at build time: two source builds without a commit
here in between would publish the same `sha` tag. Pull requests opened by the
workflow token do not start other workflows, so they carry no checks.

## External prerequisites

| Prerequisite | Purpose | Owner and storage | Verification |
| --- | --- | --- | --- |
| `bingops-com/portal` is public | The build clones it anonymously | GitHub organisation owner | `git ls-remote --heads https://github.com/bingops-com/portal.git master` |
| GHCR package `portal` is public | `labprod` pulls it without a pull secret | Package settings, set once after the first publish | `docker manifest inspect ghcr.io/bingops-com/portal:latest` from a logged-out client |
| `REPO_INFRA_TOKEN` secret in `bingops-com/portal` | Lets the source repository dispatch `rebuild-image` here | Fine-grained token limited to this repository with `Contents: read and write`; the same kind of secret `www.bingops.com` uses; recreate it in GitHub and store it again as a repository secret to rotate | A code push to `master` of the source starts the "Build and Push Docker image to GHCR" workflow |

Without the token the dispatch fails, but a change under `docker/portal`
still builds the image.
| Actions may create pull requests | Lets the image workflow open the deployment pull request | Repository setting **Settings > Actions > General > Allow GitHub Actions to create and approve pull requests**; owner: repository admin | A publication is followed by a `deploy/portal-<tag>` pull request |

Without that setting the publication still succeeds and the last step fails;
update the image tag in `deploy-target`'s manifest by hand.
