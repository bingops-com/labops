# 🧵 Cloudflare Tunnel Cheat Sheet (Terraform + Kubernetes)

## ✅ Prerequisites

* Cloudflare **API token** with necessary permissions
* Cloudflare **Account ID**
* Domain managed by Cloudflare
* **Terraform** installed
* **kubectl** configured to access your Kubernetes cluster
* Access to the Bitwarden `labprod` project

---

## 📦 Overview

This guide helps you:

1. Deploy a Cloudflare tunnel with Terraform
2. Export the tunnel credentials
3. Store the tunnel credential in Bitwarden Secrets Manager
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

## Store the tunnel credential for labprod

The tunnel credential is recoverable from the Cloudflare Terraform stack and
stored only under the ignored `terraform/cloudflare/credentials` directory.
Import it directly into the Bitwarden `labprod` project without displaying or
staging its value, then record the returned non-sensitive secret UUID in
`apps/cloudflare/bingops/cloudflare-tunnel-secret.yaml`.

The Cloudflare Kustomization owns the BitwardenSecret mapping. The generated Secret is
mounted by the chart through `cloudflare.secretName`; never create a competing
plaintext Secret manually. Rotate by updating the same Bitwarden entry; the
operator refreshes the Kubernetes Secret automatically.

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
