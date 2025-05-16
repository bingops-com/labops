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


