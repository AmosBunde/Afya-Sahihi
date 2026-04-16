#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_adr_for_new_dep.sh"

# This hook reads `git diff --cached`. Build a tiny test repo per case.

_init_repo() {
  local d="$1"
  git -C "$d" init -q
  git -C "$d" config user.email test@example.com
  git -C "$d" config user.name test
  git -C "$d" commit -q --allow-empty -m "seed"
}

case_start "green: no dep file change — hook is a no-op"
D=$(mktmp_dir)
_init_repo "$D"
mkdir -p "$D/backend/app"
echo "print('x')" > "$D/backend/app/foo.py"
git -C "$D" add backend/app/foo.py
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "red: pyproject.toml adds a dep with no ADR staged"
mkdir -p "$D/backend"
cat > "$D/backend/pyproject.toml" <<'TOML'
[project]
name = "x"
dependencies = ["httpx==0.27.0"]
TOML
git -C "$D" add backend/pyproject.toml
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 1 "$rc" && pass

case_start "green: pyproject.toml change accompanied by ADR is accepted"
mkdir -p "$D/docs/adr"
echo "# ADR 0099: adopt httpx" > "$D/docs/adr/0099-adopt-httpx.md"
git -C "$D" add docs/adr/0099-adopt-httpx.md
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

finish
