# 🚀 Argo CD Quickstart

## ✅ Prerequisites

* **Kubernetes** cluster running
* **kubectl** configured for your cluster
* **kustomize** (v5+) with Helm support

---

## 📦 Overview

This guide shows how to deploy Argo CD using the manifests in this repository and how to bootstrap your GitOps workflow.

1. Install Argo CD in the `argocd-system` namespace using Kustomize.
2. Access the Argo CD UI and log in.
3. Register your Git repository so Argo CD can sync applications.

---

## ⚙️ Deploy Argo CD

From the repository root:

```bash
# Deploy to the preprod cluster
kubectl kustomize --enable-helm apps/argocd/clusters/preprod | kubectl apply -f -
```

Repeat the command with `production` to target the production cluster.

---

## 🔐 Log In

After installation, retrieve the initial admin password:

```bash
kubectl -n argocd-system get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

Forward the Argo CD service to access the UI locally:

```bash
kubectl -n argocd-system port-forward svc/argocd-server 8080:443
```

Open `https://localhost:8080` and log in with username `admin` and the password from above.

---

## 📂 Connect Your Repo

In the Argo CD UI, add this Git repository under *Settings → Repositories* so Argo CD can watch for changes and deploy applications defined under `apps/`.

Once connected, create an "Application" pointing to one of the Kustomize directories, e.g. `apps/blog/clusters/preprod`.

### Example: portfolio application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: www-production
  namespace: argocd-system
spec:
  project: default
  source:
    repoURL: https://github.com/bingops-com/labops.git
    targetRevision: HEAD
    path: apps/bingops/clusters/production/www
  destination:
    server: https://kubernetes.default.svc
    namespace: bingops
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

## 🧯 Troubleshooting

| Problem           | Check                                      |
| ----------------- | ------------------------------------------- |
| Pods not running  | `kubectl get pods -n argocd-system`         |
| Login issues      | Verify the initial admin secret is correct  |
| Sync failures     | Ensure the repository URL and branch are correct |

---

## 🔗 References

* [Argo CD Documentation](https://argo-cd.readthedocs.io/)
