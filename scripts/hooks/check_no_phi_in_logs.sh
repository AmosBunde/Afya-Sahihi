#!/usr/bin/env bash
# check_no_phi_in_logs.sh
#
# Purpose: block any `logger.*(..., extra={"<phi_key>": ...})` call that
#   names a known-PHI key. PHI in logs violates the AKU data-handling policy
#   and the "no PHI in logs — query_id yes, query_text never" non-negotiable
#   at the top of this repo. See review SKILL §1.1.
#
# Inputs:   file paths passed as arguments by pre-commit (one per changed file).
# Exit 0:   no forbidden key appears in any logger call.
# Exit 1:   at least one logger call names a forbidden key. The offending
#           file and line appear on stderr.
# Forbidden keys: query_text, patient_name, patient_id, mrn, national_id,
#                 phone, email. Add more by editing FORBIDDEN_KEYS below.
# Allowed:  query_id, query_length, query_language_detected.
# Example:  `logger.info("x", extra={"query_text": q.text})` fails;
#           `logger.info("x", extra={"query_id": q.id})` passes.
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
