# 🧵 Cloudflare Tunnel Cheat Sheet (Terraform + Kubernetes)

## ✅ Prerequisites

* Cloudflare **API token** with necessary permissions
* Cloudflare **Account ID**
* Domain managed by Cloudflare
* **Terraform** installed
* **kubectl** configured to access your Kubernetes cluster
* **kubeseal** installed (for sealed secrets)

---

## 📦 Overview

This guide helps you:

1. Deploy a Cloudflare tunnel with Terraform
2. Export the tunnel credentials
3. Create a sealed Kubernetes secret for your app
4. Use the tunnel in a Kubernetes deployment

---

## ⚙️ Terraform: Deploy Cloudflare Tunnel

From your project’s Cloudflare Terraform module:

```bash
cd terraform/cloudflare
terraform init
terraform apply
```

**Terraform will provision:**

* A Cloudflare Zero Trust tunnel
* Required DNS records
* Tunnel credentials output as a JSON blob

---

## 🔐 Export Tunnel Credentials

Extract the credentials to a temporary file:

```bash
terraform output -json cloudflare_tunnel_credentials > /tmp/tunnel_credentials.json
```

---

## 🛡️ Create a Sealed Secret for Kubernetes

Replace `<your-namespace>` and `<your-app>` with the right values for your setup:

```bash
kubectl create secret generic cloudflare-tunnel-secret \
  --namespace=<your-namespace> \
  --from-file=credentials.json=/tmp/tunnel_credentials.json \
  --dry-run=client -o yaml | \
  kubeseal \
    --controller-name=sealed-secrets \
    --controller-namespace=tools \
    --format yaml \
  > apps/<your-app>/cloudflare-tunnel-secret.yaml
```

---

## 📦 Usage in Your App

Reference the secret in the cloudflare-tunnel Helm Chart values:

values.yaml :
```yaml
cloudflare:
  ...
  secretName: "cloudflare-tunnel-secret"
```

it will be mounted as a file in your pod, typically at `/etc/cloudflare/creds/credentials.json`.

---

## 🧯 Troubleshooting

| Problem               | What to Check                          |
| --------------------- | -------------------------------------- |
| Tunnel not connecting | Verify the secret is mounted correctly |
| DNS doesn’t resolve   | Confirm DNS records in Cloudflare      |
| Credential error      | Re-export credentials from Terraform   |

---

## 🔗 References

* [Cloudflare Zero Trust Docs](https://developers.cloudflare.com/cloudflare-one/)
* [Terraform Cloudflare Provider](https://registry.terraform.io/providers/cloudflare/cloudflare/latest)
