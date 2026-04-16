#!/usr/bin/env bash
# check_adr_for_new_dep.sh
#
# Purpose: block a commit that adds a Python dependency to
#   backend/pyproject.toml or backend/requirements.txt unless a file under
#   docs/adr/ is also staged in the same commit. Enforces the
#   "every new dependency has an ADR" rule from skills/afya-sahihi-principal/
#   SKILL.md §13.
#
# Inputs:   reads `git diff --cached`; takes no arguments.
# Exit 0:   no relevant dep change, or an ADR file is staged alongside the change.
# Exit 1:   dep file changed, new lines added, no ADR staged.
# Escape:   `git commit --no-verify` for a trivial upgrade (documented in the
#           error message the hook prints on failure).
# Example:  staging `backend/pyproject.toml` with a new dependency but no
#           `docs/adr/NNNN-*.md` in the same commit fails the hook.
set -euo pipefail
# Only run when pyproject.toml or requirements.txt changed
CHANGED=$(git diff --cached --name-only)
if ! grep -qE 'pyproject\.toml|requirements\.txt' <<<"$CHANGED"; then
  exit 0
fi

# If deps block changed, require an ADR in docs/adr/ to also be staged.
# Use `--` pathspec so a missing dep file is treated as no-op instead of
# failing the diff (previously a repo without requirements.txt would cause
# the hook to silently skip the check).
DEPS_DIFF=$(git diff --cached -U0 -- backend/pyproject.toml backend/requirements.txt 2>/dev/null || true)
ADDED=$(echo "$DEPS_DIFF" | grep -E '^\+[^+]' | grep -vE '^\+\+\+' || true)

if [[ -n "$ADDED" ]]; then
  if ! grep -qE '^(A|M)\s+docs/adr/' <(git diff --cached --name-status); then
    echo "⚠️  New dependencies detected but no ADR change in this commit." >&2
    echo "   Please add an ADR explaining the new dependency." >&2
    echo "   To bypass for a trivial upgrade, use: git commit --no-verify" >&2
    exit 1
  fi
fi
