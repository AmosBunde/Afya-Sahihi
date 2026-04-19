#!/usr/bin/env bash
# Install the afya-sahihi-watcher binary + systemd unit.
#
# Expects to be run on afya-sahihi-deploy-01 after install_k3s_server.sh
# has produced /etc/afya-sahihi/kubeconfig.yaml.
#
# Usage:
#   sudo ./install_watcher.sh
#
# Idempotent.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../../.." && pwd)"

install -d -m 0755 /usr/local/bin
install -d -m 0755 /etc/afya-sahihi/env
install -d -m 0755 /srv/afya-sahihi/gitops
install -d -m 0755 /var/log/afya-sahihi

install -m 0755 "$here/afya-sahihi-watcher" /usr/local/bin/afya-sahihi-watcher
install -m 0644 "$repo_root/deploy/systemd/afya-sahihi-watcher.service" \
  /etc/systemd/system/afya-sahihi-watcher.service

# Env file — operator must populate GITOPS_REPO / GITOPS_SSH_KEY before
# first start. Ship an example if not present so the service is not
# broken silently.
if [ ! -f /etc/afya-sahihi/env/systemd-watcher.env ]; then
  install -m 0640 "$repo_root/env/systemd-watcher.env" \
    /etc/afya-sahihi/env/systemd-watcher.env
  echo "  -> seeded /etc/afya-sahihi/env/systemd-watcher.env (fill in secrets)"
fi

# User + group for the unit.
id -u afya-sahihi-deploy >/dev/null 2>&1 || \
  useradd --system --home /srv/afya-sahihi --shell /usr/sbin/nologin \
    --user-group afya-sahihi-deploy
chown -R afya-sahihi-deploy:afya-sahihi-deploy /srv/afya-sahihi /var/log/afya-sahihi

systemctl daemon-reload
systemctl enable --now afya-sahihi-watcher.service

echo ""
echo "afya-sahihi-watcher installed. Status:"
systemctl --no-pager --lines=5 status afya-sahihi-watcher.service || true
