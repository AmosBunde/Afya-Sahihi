#!/usr/bin/env bash
# Structured log calls must not include query_text (PHI).
# Allowed: query_id, query_language, query_length. Forbidden: query_text, patient_name, etc.
set -euo pipefail
RC=0
FORBIDDEN_KEYS='"(query_text|patient_name|patient_id|mrn|national_id|phone|email)"'
for f in "$@"; do
  # Look for logger calls with extra= that include forbidden keys
  if grep -nE "logger\.(info|warning|error|debug|critical)" "$f" | \
     grep -E "$FORBIDDEN_KEYS" ; then
    echo "❌ $f logs PHI. Log query_id, not query_text." >&2
    RC=1
  fi
done
exit $RC
