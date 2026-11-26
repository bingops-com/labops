#!/usr/bin/env bash
# Trusted preparation. This file is never sent to the candidate interface.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
swapoff -a
sed -ri '/\sswap\s/s/^/#/' /etc/fstab
cat >/etc/modules-load.d/kubernetes.conf <<'MODULES'
overlay
br_netfilter
MODULES
modprobe overlay
modprobe br_netfilter
cat >/etc/sysctl.d/99-cka-kubernetes.conf <<'SYSCTL'
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
net.ipv4.ip_forward=1
SYSCTL
sysctl --system >/dev/null
apt-get update -qq
apt-get install -y -qq containerd apt-transport-https ca-certificates curl gpg bash-completion jq vim-tiny
install -d -m0755 /etc/containerd /etc/apt/keyrings
containerd config default >/etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sed -i 's/image_pull_with_sync_fs = false/image_pull_with_sync_fs = true/;s/use_local_image_pull = false/use_local_image_pull = true/;s/snapshotter = .*/snapshotter = "overlayfs"/' /etc/containerd/config.toml
systemctl enable --now containerd
systemctl restart containerd
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.37/deb/Release.key | gpg --dearmor --yes -o /etc/apt/keyrings/kubernetes.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes.gpg] https://pkgs.k8s.io/core:/stable:/v1.37/deb/ /' >/etc/apt/sources.list.d/kubernetes.list
apt-get update -qq
apt-get install -y -qq kubelet=1.37.2-1.1 kubeadm=1.37.2-1.1 kubectl=1.37.2-1.1 cri-tools=1.36.0-1.1
apt-mark hold kubelet kubeadm kubectl cri-tools >/dev/null
cat >/etc/crictl.yaml <<'CRI'
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 10
CRI
systemctl enable kubelet
cat >/etc/profile.d/cka-tools.sh <<'TOOLS'
alias k=kubectl
if command -v kubectl >/dev/null; then
  source /usr/share/bash-completion/bash_completion
  source <(kubectl completion bash)
  complete -o default -F __start_kubectl k
fi
TOOLS
