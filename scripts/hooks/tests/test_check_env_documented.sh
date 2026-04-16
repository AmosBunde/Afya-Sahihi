#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_env_documented.sh"

case_start "green: missing settings.py exits 0 (no-op)"
D=$(mktmp_dir)
mkdir -p "$D/env"
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "green: every settings field present in env/ is accepted"
mkdir -p "$D/backend/app"
cat > "$D/backend/app/settings.py" <<'PY'
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    service_name: str = "afya"
    pg_host: str = "localhost"
PY
cat > "$D/env/app.env" <<'ENV'
SERVICE_NAME=afya
PG_HOST=localhost
ENV
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "red: settings field missing from env/ is rejected"
cat > "$D/env/app.env" <<'ENV'
SERVICE_NAME=afya
ENV
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
