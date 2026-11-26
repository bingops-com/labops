#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG=/etc/kubernetes/admin.conf
manifest=/root/cka-calico-v3.33.0.yaml
curl -fLsS --retry 3 https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/calico.yaml -o "$manifest"
echo '2de8f47595fb9c41b3f47d7b767a1f8e72ecf84057af834738ff12689a234da5  /root/cka-calico-v3.33.0.yaml' | sha256sum --check --status
# Set the lab Pod CIDR explicitly instead of relying on Calico's default.
# The stock manifest comments out the optional CIDR setting.
sed -i 's/# - name: CALICO_IPV4POOL_CIDR/- name: CALICO_IPV4POOL_CIDR/;s/#   value: "192.168.0.0\/16"/  value: "10.240.0.0\/16"/' "$manifest"
kubectl apply --server-side -f "$manifest"
