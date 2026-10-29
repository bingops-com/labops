# www

Cette image Docker sert à builder et servir le site statique [`www.bingops.com`](https://github.com/bingops-com/www.bingops.com) à l’aide de [Caddy](https://caddyserver.com/).

---

## 📦 Contenu de l'image

- **Base :** `debian:trixie-slim` (image minimale et sécurisée)
- **Node.js :** v23.0.0 pour builder le frontend avec Vite
- **Caddy :** v2.7.6 comme serveur HTTP statique
- **Code source cloné depuis :**  
  [`https://github.com/bingops-com/www.bingops.com`](https://github.com/bingops-com/www.bingops.com) (`main` branch)

---

## 🚀 Build manuel

```bash
docker build -t ghcr.io/bingops-com/www docker/www
````

---

## ▶️ Utilisation

```bash
docker run -p 80:80 ghcr.io/bingops-com/www
```

Accédez ensuite à l’application via [http://localhost](http://localhost).

---

## 🧼 Contenu nettoyé après build

L'image finale est optimisée :

* `node_modules`, `.git`, cache npm et Node.js supprimés
* Seul le site statique généré (`/app/dist`) est servi par Caddy

---

## 📜 Licence

Distribué selon la licence du projet [`www.bingops.com`](https://github.com/bingops-com/www.bingops.com).



## Publication and GitOps deployment

Merging `bingops-com/www.bingops.com` to `main` dispatches the `www` build in
LabOps. Non-PR builds publish an immutable timestamp tag to `ghcr.io/bingops-com/www`.
The legacy public package is not linked to a repository and rejects LabOps'
`GITHUB_TOKEN` with `permission_denied: write_package`. The existing repository
`GHCR_TOKEN` was also rejected at login on 2026-10-29; it is not used as a fallback.
A package administrator must grant `bingops-com/labops` write access under the
www package's **Manage Actions access** settings to restore automatic publication.
GitHub does not expose that package setting through its public REST/GraphQL API.
Do not store a broadly scoped operator GitHub credential in Actions to bypass it.

### Operator publication recovery

`.github/scripts/publish-www-static.sh` publishes the built static files as a new
OCI layer on an existing immutable www runtime image. It needs Node/npm, Git,
Python, GitHub CLI and **Google go-containerregistry crane** (the unrelated
michaelsauter/crane CLI is not compatible). The runtime base must be an existing
`ghcr.io/bingops-com/www@sha256:...` digest, obtainable from the running Pod imageID.
This preserves its Caddy configuration; an opaque `/app/dist` layer replaces all
old site files and assets. The source checkout must be clean and match its fetched
`origin/main`. Runtime source revision is recorded in OCI labels.

Use go-containerregistry v0.22.1 from its official GitHub release, verify the
`go-containerregistry_Linux_x86_64.tar.gz` SHA-256 against that release's
`checksums.txt`, and extract its `crane` binary to an operator tools directory.
Set `CRANE_BIN` to that verified binary. This is an operator prerequisite, not a
container-runtime dependency.

Authenticate GitHub CLI as a package maintainer with classic PAT scopes
`read:packages` and `write:packages`; credentials remain in the operator's normal
GitHub CLI credential store. Login/rotation is owned by that maintainer through
`gh auth login`, with replacement PATs created through GitHub token settings.
Never print the credential. The helper pipes it to crane and removes its temporary
registry authentication directory on exit. No credential is copied into CI or the
cluster. Re-running an existing target succeeds only for the same source revision;
a different revision cannot overwrite that release name.

After fetching the website source and installing its declared Node dependencies:

```sh
CRANE_BIN=/path/to/google-crane .github/scripts/publish-www-static.sh \
  /path/to/www.bingops.com \
  ghcr.io/bingops-com/www@sha256:BASE_DIGEST \
  ghcr.io/bingops-com/www:UNIQUE_RELEASE_TAG
```

The digest and tag above are placeholders; use the observed runtime digest and a
new release name. The helper builds the source, publishes and validates the manifest/configuration
without re-downloading all unchanged base layers, then prints only its public
digest. Runtime health is verified after GitOps reconciliation. This is a registry write, requiring deployment
authorization. No workload changes until the following GitOps release step.

Check the workflow result and published package tags without revealing credentials.
After publication, open a deployment PR updating only the `newTag` in
`apps/workloads/portfolio/clusters/labprod/kustomization.yaml`. Render that overlay
before merging. Argo CD owns reconciliation of `portfolio-labprod` and the
Deployment in namespace `portfolio`. Reapplying the same tag is idempotent.
Verify Argo CD Synced/Healthy, Deployment availability and the served site. Rollback
is a Git revert of the tag update to the previous published image.
