#!/usr/bin/env bash
# One-time developer environment bootstrap for Afya Sahihi.
#
# Installs pinned dev tools (pre-commit, detect-secrets) from
# tools/requirements-dev.txt and activates all three pre-commit hook types
# in the current clone.
#
# Usage:
#   scripts/dev_install.sh
#
# Exits non-zero on the first failure so a contributor cannot proceed with
# a partially-initialised environment — clinical codebases fail closed.
set -euo pipefail

# Resolve the repo root so the script works no matter where it is invoked from.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required on PATH" >&2
  exit 1
fi

# Enforce Python 3.12 so the dev toolchain matches the runtime pin
# declared in skills/afya-sahihi-principal/SKILL.md §1.
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)'; then
  echo "error: Python 3.12+ is required; see CONTRIBUTING.md §'One-time setup per clone'" >&2
  exit 1
fi

# If run outside a virtualenv on a PEP-668-managed system (Debian, Ubuntu,
# Homebrew) pip will refuse. Surface that up front with a useful pointer
# instead of failing later with a confusing externally-managed error.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -z "${CI:-}" ]; then
  echo "warn: no VIRTUAL_ENV set; if pip refuses with 'externally-managed-environment'," >&2
  echo "      activate a venv first (uv venv && source .venv/bin/activate)" >&2
fi

python3 -m pip install --upgrade --quiet pip
python3 -m pip install --quiet -r tools/requirements-dev.txt

pre-commit install --install-hooks
pre-commit install --hook-type pre-push
pre-commit install --hook-type commit-msg

if [ ! -f .secrets.baseline ]; then
  echo "info: creating .secrets.baseline"
  detect-secrets scan > .secrets.baseline
fi

echo "ok: developer environment ready"
