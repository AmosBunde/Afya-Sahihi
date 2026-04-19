#!/usr/bin/env bash
# Install k3s server (control plane) on the Afya Sahihi control node.
#
# We disable k3s's bundled servicelb because we route via the host
# network + Traefik, and we pin k3s to a stable version rather than
# chasing `latest`. The join token is written to
# /etc/afya-sahihi/secrets/k3s-token for workers to pick up over
# SSH-provided means (NOT over the network; the token is a cluster
# bootstrap secret).
#
# Usage:
#   sudo ./install_k3s_server.sh
#
# Idempotent: if k3s is already installed at the pinned version this
# script is a no-op. An attempted downgrade aborts with an error.

set -euo pipefail

# Pinned quarterly per ADR-0005. Update deliberately.
readonly K3S_VERSION="v1.30.5+k3s1"

if ! "$(dirname "$0")/preflight.sh" --role=server; then
  echo "preflight failed; fix and re-run" >&2
  exit 1
fi

# Abort on an existing k3s at a different version rather than silently
# upgrade. Upgrades go through a separate playbook.
if command -v k3s >/dev/null 2>&1; then
  current="$(k3s --version | awk '/^k3s/ {print $3}')"
  if [ "$current" = "$K3S_VERSION" ]; then
    echo "k3s $K3S_VERSION already installed; nothing to do"
    exit 0
  fi
  echo "FAIL: k3s $current already installed; expected $K3S_VERSION." >&2
  echo "      This script does not upgrade; see docs/runbooks/upgrades.md." >&2
  exit 1
fi

install -d -m 0700 /etc/afya-sahihi/secrets
install -d -m 0755 /etc/afya-sahihi
# kube-apiserver writes audit records here; it creates the file but
# not the parent directory. Without this install -d, k3s crashes at
# startup with an opaque "no such file or directory" error.
install -d -m 0750 /var/log/k3s

# --disable servicelb: Traefik fronts the cluster; we don't need klipper.
#   (We keep k3s's built-in local-path storageClass on — the
#   observability stack's PVCs rely on it.)
# --node-label wires the control node for workloads that tolerate the
#   control role (observability stack lives here).
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_VERSION="$K3S_VERSION" \
  INSTALL_K3S_EXEC="server \
    --disable=servicelb \
    --write-kubeconfig-mode=0640 \
    --write-kubeconfig=/etc/afya-sahihi/kubeconfig.yaml \
    --tls-san=afya-sahihi-ctrl-01.internal \
    --tls-san=afya-sahihi.aku.edu \
    --kube-apiserver-arg=audit-log-path=/var/log/k3s/audit.log \
    --kube-apiserver-arg=audit-log-maxage=30 \
    --node-label=afya-sahihi.aku.edu/role=control" \
  sh -

# Wait for the apiserver to come up. 60s bound to avoid an infinite hang.
deadline=$(( $(date +%s) + 60 ))
until kubectl --kubeconfig /etc/afya-sahihi/kubeconfig.yaml get nodes >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "FAIL: apiserver did not become Ready within 60s" >&2
    exit 1
  fi
  sleep 2
done

# Export the join token for workers.
cp /var/lib/rancher/k3s/server/node-token /etc/afya-sahihi/secrets/k3s-token
chmod 0400 /etc/afya-sahihi/secrets/k3s-token

echo ""
echo "k3s $K3S_VERSION installed and Ready."
echo "  kubeconfig:  /etc/afya-sahihi/kubeconfig.yaml"
echo "  join token:  /etc/afya-sahihi/secrets/k3s-token"
echo ""
echo "Next: copy the join token to each worker and run"
echo "      install_k3s_agent.sh --server=https://<ctrl>:6443"
