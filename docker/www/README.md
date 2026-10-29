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
`GITHUB_TOKEN` with `permission_denied: write_package`. Only the `www` registry
login uses the existing LabOps Actions secret `GHCR_TOKEN`; other images retain
`GITHUB_TOKEN`.

`GHCR_TOKEN` is an external sensitive input owned by the maintainers of the
`bingops-com/www` package. It must be a classic GitHub PAT with `read:packages`
and `write:packages`, issued to an account with write access to that package.
Store it only as the LabOps repository Actions secret, never in Git or logs.
To recover or rotate it, the package maintainer creates a replacement token,
updates that repository secret using GitHub Settings → Secrets and variables →
Actions, reruns the failed www build, verifies publication, then revokes the old
token. Secret values must not be printed during verification.

Check the workflow result and published package tags without revealing credentials.
After publication, open a deployment PR updating only the `newTag` in
`apps/workloads/portfolio/clusters/labprod/kustomization.yaml`. Render that overlay
before merging. Argo CD owns reconciliation of `portfolio-labprod` and the
Deployment in namespace `portfolio`. Reapplying the same tag is idempotent.
Verify Argo CD Synced/Healthy, Deployment availability and the served site. Rollback
is a Git revert of the tag update to the previous published image.
