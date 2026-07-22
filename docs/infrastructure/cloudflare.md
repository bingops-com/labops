# 🧵 Cloudflare Tunnel Cheat Sheet (Terraform + Kubernetes)

## ✅ Prerequisites

* Cloudflare **API token** with the permissions required by the selected
  resources. R2 bucket creation requires `Workers R2 Storage Write` at account
  scope in addition to the tunnel and DNS permissions.
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

## CloudNativePG backup buckets

Terraform owns the `bingops-cnpg-labtest` and `bingops-cnpg-labprod` R2
buckets. They use the `WEUR` location hint and remain separate so each
environment can have an independently scoped credential and retention policy.
The pinned Cloudflare provider does not support R2 jurisdiction locks; `WEUR`
is a placement hint, not a regulatory EU residency guarantee.

R2 S3 credentials are an unavoidable external prerequisite because their
secret access key is disclosed only when the token is created. In the
Cloudflare dashboard, create one Object Read & Write token limited to each
matching bucket. Store its Access Key ID and Secret Access Key directly in the
matching Bitwarden Secrets Manager project. Normal cluster machine accounts
need read-only access to those Bitwarden values. Rotate by creating a new
bucket-scoped token, updating the same Bitwarden entries, verifying a new backup,
then revoking the old token. Neither Git nor Terraform state is a recovery
source for these S3 credentials.

The non-sensitive R2 endpoint is
`https://4d31056d6b4bf143606ff3ca757e0b8c.r2.cloudflarestorage.com`.
CloudNativePG uses the Barman Cloud plugin for continuous WAL archiving, daily
base backups and point-in-time recovery. See
[`cloudnative-pg.md`](cloudnative-pg.md) for lifecycle and recovery procedures.

---

## 🔗 References

* [Cloudflare Zero Trust Docs](https://developers.cloudflare.com/cloudflare-one/)
* [Terraform Cloudflare Provider](https://registry.terraform.io/providers/cloudflare/cloudflare/latest)
