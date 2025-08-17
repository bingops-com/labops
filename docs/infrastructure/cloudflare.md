# 🧵 Cloudflare Tunnel Cheat Sheet (Terraform + Kubernetes)

## 🗺️ Table of Contents

1️⃣ Prerequisites
2️⃣ Overview
3️⃣ Declare a New Tunnel (Terraform)
4️⃣ Deploy or Update Tunnels
5️⃣ Create a Sealed Secret
6️⃣ Use the Tunnel in Your App
7️⃣ Troubleshooting
8️⃣ References

## 1️⃣ Prerequisites

* Cloudflare **API token** with necessary permissions
* Cloudflare **Account ID**
* Domain managed by Cloudflare
* **Terraform** installed
* **kubectl** configured to access your Kubernetes cluster
* **kubeseal** installed (for sealed secrets)

## 2️⃣ Overview

This guide helps you:

1. Deploy a Cloudflare tunnel with Terraform
2. Export the tunnel credentials
3. Create a sealed Kubernetes secret for your app
4. Use the tunnel in a Kubernetes deployment

## 3️⃣ Declare a New Tunnel (Terraform)

Follow these steps to declare a **new Cloudflare tunnel in code** so that Terraform can provision it automatically:

1. Open `terraform/cloudflare/terraform.tfvars`.
2. Locate the `tunnels` list variable. Each item represents one tunnel.
3. Append a new block with your tunnel’s settings. Example:

   ```hcl
   tunnels = [
     # ✏️ Existing tunnels…
     {
       name      = "myapp"                 # A unique tunnel name (no spaces)
       hostnames = [
         "myapp.bingops.com",             # FQDNs that should resolve through the tunnel
         "api.bingops.com"
       ]
       zone_name = "bingops"               # Must map to a key in `locals.zone_domains`

```

## 4️⃣ Deploy or Update Tunnels

From your project’s Cloudflare Terraform module:

```bash
cd ${PROJECT_PATH}/terraform/cloudflare
terraform apply -auto-approve
```

This will create credentials of each tunnel inside `terraform/cloudflare/credentials/` with the filename format `<tunnel_name>.json`.

**Terraform will provision:**

* A Cloudflare Zero Trust tunnel
* Required DNS records
* Tunnel credentials output as a JSON blob

## 5️⃣ Create a Sealed Secret for Kubernetes

Replace `<tunnel-name>` and `<your-app>` with the right values for your setup:

```bash
export PROJECT_PATH="/opt/homeops/labops"

# 2️⃣ Prepare variables for the sealed secret
export SEALED_NAMESPACE="tools"
export SEALED_CONTROLLER_NAME="sealed-secrets"

export CLOUDFLARE_NAMESPACE="cloudflare"
export TUNNEL_NAME="<tunnel_name>"
export APP_NAME="<your-app>"


kubectl create secret generic ${TUNNEL_NAME}-cloudflare-tunnel-secret \
  --namespace=${CLOUDFLARE_NAMESPACE} \
  --from-file=credentials.json=$PROJECT_PATH/terraform/cloudflare/credentials/$TUNNEL_NAME.json \
  --dry-run=client -o yaml | \
  kubeseal \
    --controller-name=$SEALED_CONTROLLER_NAME \
    --controller-namespace=$SEALED_NAMESPACE \
    --format yaml \
  > apps/$CLOUDFLARE_NAMESPACE/$APP_NAME/cloudflare-tunnel-secret.yaml
```

---

## 6️⃣ Use the Tunnel in Your App

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

## 8️⃣ References

* [Cloudflare Zero Trust Docs](https://developers.cloudflare.com/cloudflare-one/)
* [Terraform Cloudflare Provider](https://registry.terraform.io/providers/cloudflare/cloudflare/latest)

---
