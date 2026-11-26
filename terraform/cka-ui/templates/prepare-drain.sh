#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl create namespace cka-drain
kubectl -n cka-drain create deployment web --image=nginx:1.28 --replicas=3
kubectl -n cka-drain expose deployment web --port=80
kubectl -n cka-drain create pdb web --selector=app=web --min-available=2
kubectl -n cka-drain run probe --image=busybox:1.37 --restart=Never --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"cka-worker-2"}}}' -- sleep 28800
kubectl -n cka-drain rollout status deployment/web --timeout=180s
kubectl -n cka-drain wait --for=condition=Ready pod/probe --timeout=180s
