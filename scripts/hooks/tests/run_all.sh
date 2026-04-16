#!/usr/bin/env bash
# Run every hook unit test file. Exits non-zero on the first failure so CI
# surfaces the offending hook quickly.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

shopt -s nullglob
any=0
for t in "$TESTS_DIR"/test_*.sh; do
  any=1
  echo "=== $(basename "$t") ==="
  bash "$t"
done
shopt -u nullglob

if [ "$any" -eq 0 ]; then
  echo "error: no test_*.sh files in $TESTS_DIR" >&2
  exit 1
fi

echo "All hook tests passed."
