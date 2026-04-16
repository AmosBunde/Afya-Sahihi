#!/usr/bin/env bash
# No print() in production backend code. Use the structured logger.
set -euo pipefail
RC=0
for f in "$@"; do
  # Match bare print( not inside a string, ignore lines with '# noqa: T201'
  if grep -Hn -E '^[^#]*\bprint\(' "$f" | grep -v 'noqa: T201'; then
    echo "❌ $f contains print(). Use structured logger." >&2
    RC=1
  fi
done
exit $RC
