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
(`/etc/status/status.yaml`), rendered by the `charts/status` Helm chart
from the values of `apps/workloads/status`, and writes its availability history to `STATUS_DATA` (`/data`).

## Releases

The image workflow publishes `ghcr.io/bingops-com/status` with the tags
`latest`, `sha-<short labops commit>` and a timestamp whenever:

- a push to `master` of the source repository changes its code (it sends a
  `rebuild-image` dispatch; a pull request there builds without publishing);
- a change under `docker/status` reaches `master` here.

A published image is not deployed by itself. Once `deploy-target` exists in
this directory, the workflow opens a pull request (`deploy/status-<tag>`) after
each publication that sets `image.tag` of the Helm values file it names to the
new timestamp tag (`YYYYMMDD-HHmmss`); merging it is the deployment. See
[`docker/portal/README.md`](../portal/README.md) for why the timestamp tag is
the one deployed.

## External prerequisites

| Prerequisite | Purpose | Owner and storage | Verification |
| --- | --- | --- | --- |
| `bingops-com/status` is public | The build clones it anonymously | GitHub organisation owner | `git ls-remote --heads https://github.com/bingops-com/status.git master` |
| GHCR package `status` is public | `labprod` pulls it without a pull secret | Package settings, set once after the first publish | `docker manifest inspect ghcr.io/bingops-com/status:latest` from a logged-out client |
| `REPO_INFRA_TOKEN` organisation secret of `bingops-com`, readable by `status` | Lets the source repository dispatch `rebuild-image` here | Fine-grained token limited to this repository with `Contents: read and write`, shared by every source repository that requests a rebuild; see the procedure below | A code push to `master` of the source starts the "Build and Push Docker image to GHCR" workflow |
| Actions may create pull requests | Lets the image workflow open the deployment pull request | Repository setting **Settings > Actions > General > Allow GitHub Actions to create and approve pull requests**; owner: repository admin | A publication is followed by a `deploy/status-<tag>` pull request |

Without the token the dispatch fails, but a change under `docker/status` still
builds the image. No secret value is stored in this repository.

## Creating or rotating `REPO_INFRA_TOKEN`

The token is a sensitive external input: it cannot be recovered from Git or
read back from GitHub, only replaced. Its owner is the lab operator. It is
stored once, as an Actions secret of the `bingops-com` organisation limited to
the source repositories that request a rebuild: `portal`, `status`,
`www.bingops.com` and `blog.bingops.com`. Its consumers are their
`.github/workflows/trigger-rebuild.yml`. The same steps create it, rotate it
and recover from its loss or expiry; repeating them is safe.

1. In GitHub, open **Settings > Developer settings > Personal access tokens >
   Fine-grained tokens > Generate new token**, signed in as an owner of the
   `bingops-com` organisation.
2. Set **Resource owner** to `bingops-com`, **Repository access** to **Only
   select repositories** with `bingops-com/labops` alone, and under
   **Repository permissions** set **Contents** to **Read and write**. GitHub
   adds **Metadata: Read-only** by itself. Grant nothing else: `Contents`
   write is what the `repository_dispatch` API requires.
3. Choose an expiry and note its date in the password manager entry of the
   token; an expired token only stops automatic rebuilds.
4. Store the value as the organisation secret without putting it on a command
   line. Run this in an interactive terminal: `gh` then prompts for the value
   and keeps it out of the shell history, whereas without a terminal it reads
   standard input and stores whatever it finds there, even nothing. The
   session needs the `admin:org` scope
   (`gh auth refresh -h github.com -s admin:org`).

   ```bash
   gh secret set REPO_INFRA_TOKEN --org bingops-com --visibility selected \
     --repos portal,status,www.bingops.com,blog.bingops.com
   ```

   `--repos` replaces the whole list: to give one more source repository
   access, repeat the command with the complete list, or add it under
   **Organization settings > Secrets and variables > Actions**, which keeps
   the value.
5. Keep the value nowhere else than the password manager, or discard it:
   generating a new token is the recovery procedure.

Do not create a repository secret of the same name: it would take precedence
over the organisation secret and be missed by the next rotation. Organisation
secrets are available to these repositories because they are public.

Verify without revealing the value:

```bash
gh secret list --org bingops-com
gh api orgs/bingops-com/actions/secrets/REPO_INFRA_TOKEN/repositories \
  --jq '.repositories[].name'
```

The first shows the name and its update date, the second the repositories
allowed to read it. Neither proves the value is right: the next code push to
`master` of a source repository must end its "Trigger Docker Rebuild" workflow
in success and start "Build and Push Docker image to GHCR" here. To rotate,
generate a new token, repeat step 4, then delete the previous token in GitHub.
