#!/usr/bin/env bash
# Join a k3s worker node.
#
# Expects the join token at /etc/afya-sahihi/secrets/k3s-token (copied
# there out-of-band by the operator — never fetched over the network).
# The control node URL is passed via --server.
#
# Usage:
#   sudo ./install_k3s_agent.sh --server=https://afya-sahihi-ctrl-01.internal:6443

set -euo pipefail

readonly K3S_VERSION="v1.30.5+k3s1"

server=""
for arg in "$@"; do
  case "$arg" in
    --server=*) server="${arg#--server=}" ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done
[ -n "$server" ] || { echo "--server=<url> required" >&2; exit 2; }

if ! "$(dirname "$0")/preflight.sh" --role=agent; then
  echo "preflight failed; fix and re-run" >&2
  exit 1
fi

if command -v k3s >/dev/null 2>&1; then
  current="$(k3s --version | awk '/^k3s/ {print $3}')"
  if [ "$current" = "$K3S_VERSION" ]; then
    echo "k3s $K3S_VERSION already installed; nothing to do"
    exit 0
  fi
  echo "FAIL: k3s $current already installed; expected $K3S_VERSION." >&2
  exit 1
fi

token="$(cat /etc/afya-sahihi/secrets/k3s-token)"

curl -sfL https://get.k3s.io | \
  INSTALL_K3S_VERSION="$K3S_VERSION" \
  K3S_URL="$server" \
  K3S_TOKEN="$token" \
  INSTALL_K3S_EXEC="agent \
    --node-label=afya-sahihi.aku.edu/role=worker" \
  sh -

echo ""
echo "k3s $K3S_VERSION agent joined $server"
