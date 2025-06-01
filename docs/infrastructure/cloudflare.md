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

This will create credentials of each tunnel inside `terraform/cloudflare/credentials/` with the filename format `<tunnel_name>.json`.

**Terraform will provision:**

* A Cloudflare Zero Trust tunnel
* Required DNS records
* Tunnel credentials output as a JSON blob

---

## 🛡️ Create a Sealed Secret for Kubernetes

Replace `<tunnel-name>` and `<your-app>` with the right values for your setup:

```bash
export PROJECT_PATH="/opt/homeops/labops"

export SEALED_NAMESPACE="tools"
export SEALED_CONTROLLER_NAME="sealed-secrets"

export CLOUDFLARE_NAMESPACE="cloudflare"
export TUNNEL_NAME="<tunnel_name>"
export APP_NAME="<your-app>"


kubectl create secret generic cloudflare-tunnel-secret \
  --namespace=$CLOUDFLARE_NAMESPACE \
  --from-file=credentials.json=$PROJECT_PATH/terraform/cloudflare/credentials/$TUNNEL_NAME.json \
  --dry-run=client -o yaml | \
  kubeseal \
    --controller-name=$SEALED_CONTROLLER_NAME \
    --controller-namespace=$SEALED_NAMESPACE \
    --format yaml \
  > apps/$CLOUDFLARE_NAMESPACE/$APP_NAME/cloudflare-tunnel-secret.yaml
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
