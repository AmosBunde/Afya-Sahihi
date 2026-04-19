#!/usr/bin/env bash
# Tests for deploy/systemd/bootstrap/afya-sahihi-watcher.
#
# Spins up a temporary fake git repo + fake kubectl, exercises:
#   - reconcile with no change (no apply)
#   - reconcile with a new commit (apply + state file update)
#   - reconcile with a failing kubectl (state not advanced)
#   - status output
#
# No actual k3s / kubectl required — we shim them.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
watcher="$here/../../deploy/systemd/bootstrap/afya-sahihi-watcher"

[ -x "$watcher" ] || { echo "watcher not executable: $watcher" >&2; exit 2; }

# Canary: one-off failures explode loudly.
trap 'echo "FAIL at line $LINENO" >&2' ERR

fail=0
assert_eq() {
  local want="$1" got="$2" name="$3"
  if [ "$want" = "$got" ]; then
    echo "OK: $name"
  else
    echo "FAIL: $name — want=$want got=$got" >&2
    fail=1
  fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- Fake upstream repo with one commit -----------------------------------

upstream="$tmp/upstream.git"
git init --bare --initial-branch=main --quiet "$upstream"

work="$tmp/work"
git init --initial-branch=main --quiet "$work"
(
  cd "$work"
  git -c user.email=t@t -c user.name=t remote add origin "$upstream"
  mkdir -p deploy/k3s/kustomize/overlays/dev
  cat > deploy/k3s/kustomize/overlays/dev/kustomization.yaml <<'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
EOF
  git add -A
  git -c user.email=t@t -c user.name=t commit --quiet -m "initial"
  git push --quiet origin main
)
initial_sha="$(cd "$work" && git rev-parse HEAD)"

# --- Fake kubectl ---------------------------------------------------------

fake_bin="$tmp/bin"
mkdir -p "$fake_bin"
cat > "$fake_bin/kubectl" <<'EOF'
#!/usr/bin/env bash
echo "fake-kubectl $*" >&2
exit "${FAKE_KUBECTL_EXIT:-0}"
EOF
chmod +x "$fake_bin/kubectl"

# --- Test harness setup ---------------------------------------------------

export GITOPS_REPO="$upstream"
export GITOPS_BRANCH=main
export GITOPS_LOCAL_CHECKOUT="$tmp/checkout"
export GITOPS_STATE_FILE="$tmp/state"
export GITOPS_SSH_KEY=""
export DEPLOYMENT_ENV=dev
export OVERLAY_PATH="deploy/k3s/kustomize/overlays/dev"
export KUBECTL_BIN="$fake_bin/kubectl"
export KUBECONFIG="$tmp/kubeconfig"
touch "$KUBECONFIG"
export PATH="$fake_bin:$PATH"

# --- Test 1: reconcile with no existing state applies initial commit ------

"$watcher" reconcile >/dev/null

[ -f "$GITOPS_STATE_FILE" ]
last="$(awk -F= '/^last_applied_sha=/ {print $2}' "$GITOPS_STATE_FILE")"
assert_eq "$initial_sha" "$last" "reconcile applies initial commit and records state"

# --- Test 2: reconcile with no change is a no-op --------------------------

log="$("$watcher" reconcile 2>&1)"
if echo "$log" | grep -q '"applying manifests"'; then
  echo "FAIL: second reconcile should not re-apply unchanged state" >&2
  fail=1
else
  echo "OK: reconcile is a no-op when sha unchanged"
fi

# --- Test 3: new commit triggers apply ------------------------------------

(
  cd "$work"
  echo "# comment" >> deploy/k3s/kustomize/overlays/dev/kustomization.yaml
  git -c user.email=t@t -c user.name=t commit --quiet -am "update"
  git push --quiet origin HEAD
)
new_sha="$(cd "$work" && git rev-parse HEAD)"

"$watcher" reconcile >/dev/null
last="$(awk -F= '/^last_applied_sha=/ {print $2}' "$GITOPS_STATE_FILE")"
assert_eq "$new_sha" "$last" "reconcile applies new commit and advances state"

# --- Test 4: failing kubectl keeps old state ------------------------------

(
  cd "$work"
  echo "# another" >> deploy/k3s/kustomize/overlays/dev/kustomization.yaml
  git -c user.email=t@t -c user.name=t commit --quiet -am "update-2"
  git push --quiet origin HEAD
)
broken_sha="$(cd "$work" && git rev-parse HEAD)"

FAKE_KUBECTL_EXIT=1 "$watcher" reconcile >/dev/null 2>&1 && {
  echo "FAIL: reconcile should return non-zero when kubectl fails" >&2
  fail=1
} || echo "OK: reconcile returns non-zero on kubectl failure"

last="$(awk -F= '/^last_applied_sha=/ {print $2}' "$GITOPS_STATE_FILE")"
if [ "$last" = "$broken_sha" ]; then
  echo "FAIL: state advanced to broken_sha despite kubectl failure" >&2
  fail=1
else
  echo "OK: state not advanced after kubectl failure (state=$last, broken=$broken_sha)"
fi

# --- Test 5: status prints expected fields --------------------------------

out="$("$watcher" status 2>&1)"
echo "$out" | grep -q "head sha:" && echo "OK: status reports head sha" \
  || { echo "FAIL: status missing head sha"; fail=1; }
echo "$out" | grep -q "last applied:" && echo "OK: status reports last applied" \
  || { echo "FAIL: status missing last applied"; fail=1; }
echo "$out" | grep -q "overlay:" && echo "OK: status reports overlay" \
  || { echo "FAIL: status missing overlay"; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo ""
  echo "All watcher tests passed."
fi
exit "$fail"
