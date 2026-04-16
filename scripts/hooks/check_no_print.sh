#!/usr/bin/env bash
# check_no_print.sh
#
# Purpose: reject `print(` in backend Python. The structured JSON logger is
#   the only approved output path (SKILL.md §0 non-negotiable #8, §10, §13).
#   A stray print() in a service process escapes the structured-log schema
#   and bypasses the PHI scrubber.
#
# Inputs:   file paths passed as arguments by pre-commit (one per changed file).
# Exit 0:   no bare print() call in any provided file (or every such call is
#           marked with `# noqa: T201` for a CLI tool).
# Exit 1:   at least one bare print() call found; file:line printed to stderr.
# Escape:   append `# noqa: T201` on the same line for CLI tools where print
#           is the intended output mechanism.
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
