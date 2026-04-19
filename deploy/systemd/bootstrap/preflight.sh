#!/usr/bin/env bash
# Preflight checks for an Afya Sahihi k3s node.
#
# Runs before install_k3s_server.sh or install_k3s_agent.sh. Verifies
# kernel version, cgroup version, disk layout, and (for the GPU node)
# NVIDIA driver version. Exits non-zero on the first failure with a
# clear message so the operator can fix one thing at a time.
#
# Usage:
#   sudo ./preflight.sh [--role=server|agent|gpu]
#
# Defaults to --role=server which runs all checks except the GPU one.
# --role=gpu runs the GPU check in addition.

set -euo pipefail

role="server"
for arg in "$@"; do
  case "$arg" in
    --role=*) role="${arg#--role=}" ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

fail=0

check() {
  local name="$1"; shift
  if "$@"; then
    echo "OK: $name"
  else
    echo "FAIL: $name" >&2
    fail=1
  fi
}

# --- kernel --------------------------------------------------------------

check_kernel_min_6_1() {
  local kv
  kv="$(uname -r | cut -d. -f1,2)"
  awk -v v="$kv" 'BEGIN { split(v, a, "."); if (a[1] < 6 || (a[1] == 6 && a[2] < 1)) exit 1 }'
}
check "kernel >= 6.1 (cgroup v2 + recent containerd features)" check_kernel_min_6_1

# --- cgroup v2 -----------------------------------------------------------

check_cgroup_v2() {
  [ -f /sys/fs/cgroup/cgroup.controllers ]
}
check "cgroup v2 unified hierarchy (/sys/fs/cgroup/cgroup.controllers)" check_cgroup_v2

# --- swap ----------------------------------------------------------------

check_swap_off() {
  [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]
}
check "swap disabled (kubelet refuses to run with swap on)" check_swap_off

# --- disk ----------------------------------------------------------------

check_rancher_disk() {
  # k3s stores its data in /var/lib/rancher; require >= 20 GiB free.
  local avail_kb
  avail_kb="$(df -Pk /var/lib 2>/dev/null | awk 'NR==2 {print $4}')"
  [ -n "$avail_kb" ] && [ "$avail_kb" -ge $((20 * 1024 * 1024)) ]
}
check "/var/lib >= 20 GiB free (k3s data directory)" check_rancher_disk

# --- required binaries ---------------------------------------------------

check_curl() { command -v curl >/dev/null; }
check_systemctl() { command -v systemctl >/dev/null; }
check "curl installed (k3s installer fetches over HTTPS)" check_curl
check "systemctl available (k3s runs as systemd unit)" check_systemctl

# --- network -------------------------------------------------------------

check_port_6443_free() {
  # k3s binds the kube-apiserver on 6443; fail if already in use.
  ! ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ':6443$'
}
check "port 6443 free (k3s apiserver binds here)" check_port_6443_free

# --- agent-specific ------------------------------------------------------

if [ "$role" = "agent" ]; then
  check_k3s_token() {
    [ -f /etc/afya-sahihi/secrets/k3s-token ] && [ -s /etc/afya-sahihi/secrets/k3s-token ]
  }
  check "k3s join token at /etc/afya-sahihi/secrets/k3s-token" check_k3s_token
fi

# --- gpu-specific --------------------------------------------------------

if [ "$role" = "gpu" ]; then
  check_nvidia_driver() {
    if ! command -v nvidia-smi >/dev/null; then return 1; fi
    local driver_major
    driver_major="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)"
    [ -n "$driver_major" ] && [ "$driver_major" -ge 550 ]
  }
  check "NVIDIA driver >= 550 (H100 on MedGemma 27B)" check_nvidia_driver
fi

if [ "$fail" -eq 0 ]; then
  echo ""
  echo "All preflight checks passed for role=$role."
fi
exit "$fail"
