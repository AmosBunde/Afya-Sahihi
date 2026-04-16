#!/usr/bin/env bash
# Shared helpers for hook unit tests.
#
# Conventions:
#   - Every test file sources this, sets HOOK_PATH, and calls pass/fail per case.
#   - Tests are deterministic. No time.sleep, no network, no reliance on the
#     real repo layout. Each test builds its own temp directory and cleans up.
#   - Exit 0 if every case passed, exit 1 on the first failure (fail-fast for
#     a safety-critical repo).
#
# Why a hand-rolled harness: these are shell scripts; adding bats-core would be
# a new dependency pulled in for 10 tests. Trade-off favored here is zero new
# deps; revisit if the test count grows past ~30.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC2034  # HOOKS_DIR is consumed by sourcing test files
HOOKS_DIR="$REPO_ROOT/scripts/hooks"

FAILED=0
CURRENT_TEST=""

_cleanup_dirs=()
_cleanup() {
  local d
  for d in "${_cleanup_dirs[@]}"; do
    [ -d "$d" ] && rm -rf "$d"
  done
}
trap _cleanup EXIT

# mktmp_dir: create a new temp dir, register for cleanup, echo the path.
mktmp_dir() {
  local d
  d="$(mktemp -d "${TMPDIR:-/tmp}/afya-hook-test.XXXXXXXX")"
  _cleanup_dirs+=("$d")
  echo "$d"
}

# case_start NAME: record the running test case label for reporting.
case_start() {
  CURRENT_TEST="$1"
}

# pass: report green, do not exit.
pass() {
  echo "  PASS  $CURRENT_TEST"
}

# fail MSG: report red with message; set FAILED=1 so the outer script exits 1.
fail() {
  echo "  FAIL  $CURRENT_TEST: $1" >&2
  FAILED=1
}

# assert_rc EXPECTED ACTUAL: compare exit codes.
assert_rc() {
  local expected="$1" actual="$2"
  if [ "$expected" != "$actual" ]; then
    fail "expected exit $expected, got $actual"
    return 1
  fi
  return 0
}

# finish: called at end of each test file to set the process exit code.
finish() {
  if [ "$FAILED" -ne 0 ]; then
    echo "TEST FILE FAILED: $(basename "${BASH_SOURCE[1]:-?}")" >&2
    exit 1
  fi
}
