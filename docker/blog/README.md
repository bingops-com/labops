# Blog

Cette image Docker sert à builder et servir un site statique avec [Caddy](https://caddyserver.com/) à partir d’un projet Node.js.

Le déploiement GitOps, les dépendances et la reprise du site public sont décrits
dans le [runbook du blog](../../apps/workloads/blog/README.md). La production
utilise une empreinte d’image figée ; reconstruire cette image depuis la branche
`master` du dépôt source ne garantit pas un contenu identique.

---

## 📦 Contenu de l'image

* **Base :** `debian:trixie-slim` (image minimale, stable et sécurisée)
* **Node.js :** v23.0.0 pour le build frontend (ex: avec Vite, React, etc.)
* **Caddy :** v2.7.6 pour servir les fichiers statiques
* **Répertoire de travail :** `/app`

---

## 🚀 Build manuel

```bash
docker build -t blog .
```

---

## ▶️ Utilisation

```bash
docker run -p 80:80 blog
```

Accédez ensuite à l’application via [http://localhost](http://localhost).

---

## 🧼 Contenu nettoyé après build

L’image finale est allégée :

* Suppression de `node_modules`, `.git`, cache npm et Node.js après le build
* Seuls les fichiers statiques générés (`/app/dist`) sont conservés
* Le serveur Caddy sert directement ces fichiers

## 📜 Licence

Distribué selon la licence du projet [`blog.bingops.com`](https://github.com/bingops-com/blog.bingops.com).
