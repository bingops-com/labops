# Status

The status page is the public view of the lab's availability: for each
publicly hosted service, whether it responds, its availability day by day over
90 days and the interruptions recorded. It runs only on `labprod` and is
published at `https://status.lab.bingo` through Cloudflare Tunnel.

## Ownership

- Source: separate `bingops-com/status` repository, which documents the
  configuration file and the API.
- Manifests: the locally maintained Helm chart
  [`charts/status`](../../../charts/status) (Deployment, Service, ConfigMap
  and PVC). Argo CD renders it from `master` with the release name `status`
  and `clusters/labprod/values.yaml`, the only environment-specific file. The
  Application creates the `status` namespace. The chart is also published to
  `oci://ghcr.io/bingops-com/helm` when it changes, but `labprod` does not
  consume that copy: a chart change deploys at merge, without a version bump.
- Image: [`docker/status`](../../../docker/status/README.md) clones the
  `master` branch of the source and lists the external prerequisites. Each
  publication opens a `deploy/status-<tag>` pull request that sets
  `image.tag` in `clusters/labprod/values.yaml`; merging it is the
  deployment. Keep `tag:` on the line after `repository:`, which is how the
  workflow finds it.
- Content: the `config` block of `clusters/labprod/values.yaml` is the source
  of truth for the Gatus groups made public, the words shown for each service
  and the hand-written announcements. The chart renders it as `status.yaml`
  and stamps its checksum on the pod, so a change restarts the page.
- Availability data: [`apps/workloads/gatus`](../gatus/README.md). The page
  probes nothing itself; it reads
  `http://gatus.gatus.svc.cluster.local:8080/api/v1/endpoints/statuses` every
  minute.
- DNS and route: `status.lab.bingo` is declared in
  `terraform/cloudflare/locals.tf` (CNAME to the tunnel, created by a Terraform
  apply of that stack) and in `apps/cloudflare/bingops/values.yaml` (tunnel
  ingress to the `status` Service). There is no Traefik Ingress: the tunnel is
  the only way in.

## What is public

Only endpoints of the Gatus group `Public` are read, recorded and served. To
put a service on the page, add its endpoint to that group in
`apps/workloads/gatus/base/config.yaml`, then optionally its description and
address under `config.services` in `clusters/labprod/values.yaml`. Moving an endpoint out of the group removes it
from the page at the next reading.

From a check the page keeps the service name, the outcome and the duration.
Probed addresses, conditions, Gatus error messages and the Gatus address are
neither stored nor sent to visitors. Endpoints of the `Plateforme` group,
including the page's own health check, never appear.

## Acceptance gate

- Database: none. A JSON file on the `status-data` PVC (`local-path`, 64Mi)
  holds the checks counted per day and the incidents.
- Authentik: not applicable. The page is public and read-only: no login, no
  form, no administrative function. Its content changes only through Git.
- Durable data: disposable. Losing `status-data` resets the page to "no
  measurement" for past days and empties the logbook; current states are
  correct again at the next reading. It is not backed up. Gatus keeps only
  seven days, so older figures cannot be rebuilt.

No credential is involved: the pod has no service account token, no Secret and
no access to the Kubernetes API.

## Verify

```sh
helm lint charts/status
helm template status charts/status --namespace status \
  --values apps/workloads/status/clusters/labprod/values.yaml >/dev/null
kubectl --context labprod get application status-labprod -n argocd-system
kubectl --context labprod get deployment,pod,pvc -n status
curl -fsS https://status.lab.bingo/healthz
curl -fsS https://status.lab.bingo/api/status | grep -c '"state"'
```

The `kubectl --context` and `curl` commands contact live systems and are
read-only. The API answer must list the services of the `Public` group and
contain neither `svc.cluster.local` nor a name of the `Plateforme` group. In a
browser, check the headline, one mark per day and per service, the logbook,
both languages and a phone width. This check is non-sensitive.

Right after the first deployment every past day reads "no measurement": the
page does not go further back than its own history.

## Rollback

Revert the deployment pull request to return to the previous image, or revert
the change that added the Application to remove the page. Removing
`status.lab.bingo` from `terraform/cloudflare/locals.tf` and applying that
stack deletes the DNS record.
