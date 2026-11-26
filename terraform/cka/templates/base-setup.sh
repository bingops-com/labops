#!/usr/bin/env bash
set -euo pipefail

# Deliberately leave container runtime, swap, kubelet, kubeadm and Kubernetes
# installation to the learner. This script only prepares operator access.
install -d -m 0775 -o ubuntu -g ubuntu /opt/shared
systemctl enable --now qemu-guest-agent.service
printf 'CKA base VM ready; install Kubernetes manually.\n' >/etc/motd
