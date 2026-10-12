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
helm template status charts/status --namespace status --values apps/workloads/status/clusters/labprod/values.yaml >/dev/null
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

## Recover an unreadable history

If the pod exits with `unreadable history` and `unexpected end of JSON input`,
the public route returns 502 even while Gatus and the tunnel are healthy.
The history is generated, disposable state, not a credential or a declarative
input. There is no external backup: an empty file contains no recoverable
measurements. This manual procedure is a fallback for images without startup
recovery. Images implementing the recovery in
[`bingops-com/status#2`](https://github.com/bingops-com/status/pull/2) can
preserve invalid files and restore a same-volume `history.json.bak`
automatically; that copy does not protect against losing the PVC.
The operator owns recovery; resetting it loses past figures and incidents on
this page, without changing Gatus or the other services.

The following commands contact and modify **live labprod**. Obtain explicit
authorization to quarantine the history and restart this workload first.
Use a client with permission to create/get/list/watch/delete pods, read pod
logs, create pod exec sessions, and read/watch deployments in `status`.
No Secret access is needed.
Keep the existing failed status pod: the temporary helper's affinity places
it on the same node for the `local-path` ReadWriteOnce PVC. The helper uses
the application's UID/GID, has no API token and expires after 30 minutes.
Its pinned public Python image must be cached or pullable on that node.

```sh
kubectl --context labprod logs -n status deployment/status --previous --tail=20
kubectl --context labprod create -f apps/workloads/status/recovery/pod.yaml
kubectl --context labprod wait -n status --for=condition=Ready pod/status-history-recovery --timeout=60s
kubectl --context labprod exec -n status status-history-recovery -- python3 -c 'import pathlib,json,hashlib; p=pathlib.Path("/data/history.json"); b=p.read_bytes(); print("bytes:",len(b)); print("sha256:",hashlib.sha256(b).hexdigest()); print("recovery copy exists:",p.with_name("history.json.bak").exists()); json.loads(b)'
```

The inspection prints only length and checksum, then fails if the JSON is
invalid. Inspect any changed error before proceeding. If a recovery copy is
present, stop and assess the source application's automatic recovery before
resetting measurements. Set the shell variable
to the checksum just inspected; it is not sensitive. The script refuses a
different invalid file, leaves valid JSON untouched, and treats an absent
file as already recovered. It atomically renames the invalid file to a unique
`/data/history.json.corrupt-<timestamp>-<id>` on the same PVC and verifies its
checksum. Keep this archive on the PVC for any later investigation; do not
commit generated history or replace a healthy history with it.

```sh
read -r -p 'Inspected history SHA-256: ' status_history_sha256
kubectl --context labprod exec -i -n status status-history-recovery -- python3 - "$status_history_sha256" < apps/workloads/status/recovery/quarantine-history.py
kubectl --context labprod delete pod -n status -l app.kubernetes.io/name=status,app.kubernetes.io/instance=status --wait=false
kubectl --context labprod rollout status deployment/status -n status --timeout=60s
kubectl --context labprod exec -n status status-history-recovery -- python3 -c 'import pathlib,json; p=pathlib.Path("/data/history.json"); d=json.loads(p.read_bytes()); print("new history JSON valid; bytes:",p.stat().st_size); print("archives:",[(x.name,x.stat().st_size) for x in p.parent.glob("history.json.corrupt-*")])'
kubectl --context labprod delete pod -n status status-history-recovery --ignore-not-found=true --wait=false
curl -fsS https://status.lab.bingo/healthz
curl -fsS https://status.lab.bingo/api/status | python3 -c 'import json,sys; d=json.load(sys.stdin); print("services:",[(s["name"],s["state"]) for s in d["services"]]); print("stale:",d["stale"]); assert "svc.cluster.local" not in json.dumps(d)'
```

The Deployment recreates the application pod from its unchanged GitOps
configuration; avoid a rollout annotation or scaling change. If a step
fails, retain the archive, inspect pod status and retry from the helper
creation step (reuse an existing ready helper instead of creating it again).
Always delete the helper after verification, including after a failed
recovery. Neither the helper nor the quarantine is a persistent cluster
configuration change. A fresh rebuild still needs only the normal chart,
image, Gatus and tunnel dependencies above.

This restores service without establishing why the file became empty.
Recurrence requires investigation of the source application's persistence
and node/storage failures; the procedure does not change the application.

A preventive application release belongs in `bingops-com/status`: require
regression tests for empty/truncated JSON, preserving the invalid file,
restoring from a valid same-volume recovery copy, and restarting safely after
recovery. Writes must synchronize the temporary file before atomic replacement
and the directory after replacement. A same-volume copy cannot replace an
external backup or protect against loss of the PVC. These behaviors require
a new source build and deployment image tag; this operator runbook alone does
not change the running application's behavior. Follow the image publication
and deployment ownership described above, then verify the public health and
fresh Gatus data without deliberately corrupting the production volume.

## Rollback

Revert the deployment pull request to return to the previous image, or revert
the change that added the Application to remove the page. Removing
`status.lab.bingo` from `terraform/cloudflare/locals.tf` and applying that
stack deletes the DNS record.
