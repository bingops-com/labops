# Project Zomboid

Argo CD combines the environment resources in this directory with the Helm
chart owned by `bingops-com/pz-server`. The chart runs the Build 42 server on a
retained `local-path` PVC and publishes UDP NodePorts `30261` and `30262` for
the external gateway. RCON remains cluster-internal.

Bitwarden owns all plaintext values. The tracked mappings materialize
`pz-server-secrets` and `pz-r2-credentials`; the chart only refers to their
names and keys. The namespace must also contain the read-only `bw-auth-token`
created by the bootstrap helper.

Terraform owns `bingops-pz-labprod`. Its Object Read & Write token is an
external prerequisite restricted to that bucket and stored in Bitwarden.
Restic stops the game cleanly, uploads the persistent game data to R2, applies
the chart retention policy, and verifies a subset of repository data.

The Build 41 VM must not be retired until its complete encrypted backup exists,
the Build 42 service is reachable, and a disposable R2 restore has succeeded.

Verification must not print Secret values:

```sh
kubectl --context labprod get application -n argocd-system pz-server-labprod
```

```sh
kubectl --context labprod get bitwardensecrets -n pz-server
```

```sh
kubectl --context labprod get statefulset,pod,pvc,cronjob -n pz-server
```
