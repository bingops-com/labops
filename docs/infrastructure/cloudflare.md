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

## Seal the tunnel credential for labprod

The tunnel credential is recoverable from the Cloudflare Terraform stack and
stored only under the ignored `terraform/cloudflare/credentials` directory.
The labprod Sealed Secrets controller is named `sealed-secrets-controller` in
`kube-system`. Regenerate the committed ciphertext after a tunnel credential or
controller-key rotation without displaying plaintext:

```sh
kubectl create secret generic cloudflare-tunnel-secret --namespace cloudflare --from-file=credentials.json=terraform/cloudflare/credentials/bingops-tunnel.json --dry-run=client -o json | kubeseal --context labprod --controller-name sealed-secrets-controller --controller-namespace kube-system --scope strict --format yaml > apps/cloudflare/bingops/cloudflare-tunnel-secret.yaml
```

Validate the generated manifest against the current controller:

```sh
kubeseal --context labprod --controller-name sealed-secrets-controller --controller-namespace kube-system --validate < apps/cloudflare/bingops/cloudflare-tunnel-secret.yaml
```

The Cloudflare Kustomization owns the SealedSecret. The generated Secret is
mounted by the chart through `cloudflare.secretName`; never create a competing
plaintext Secret manually.

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
