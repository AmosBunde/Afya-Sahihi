#!/usr/bin/env bash
# New top-level dependencies require a companion ADR in the same PR.
set -euo pipefail
# Only run when pyproject.toml or requirements.txt changed
CHANGED=$(git diff --cached --name-only)
if ! grep -qE 'pyproject\.toml|requirements\.txt' <<<"$CHANGED"; then
  exit 0
fi

# If deps block changed, require an ADR in docs/adr/ to also be staged
DEPS_DIFF=$(git diff --cached -U0 backend/pyproject.toml backend/requirements.txt 2>/dev/null || true)
ADDED=$(echo "$DEPS_DIFF" | grep -E '^\+[^+]' | grep -vE '^\+\+\+' || true)

if [[ -n "$ADDED" ]]; then
  if ! grep -qE '^(A|M)\s+docs/adr/' <(git diff --cached --name-status); then
    echo "⚠️  New dependencies detected but no ADR change in this commit." >&2
    echo "   Please add an ADR explaining the new dependency." >&2
    echo "   To bypass for a trivial upgrade, use: git commit --no-verify" >&2
    exit 1
  fi
fi
