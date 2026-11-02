#!/usr/bin/env bash
# Build every configured app locally and collect APKs into ./release-apks
# plus per-build records into ./build_records so manifest.json can be rebuilt.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/release-apks"
REC="$ROOT/build_records"
LOG="$ROOT/build-logs"
mkdir -p "$OUT" "$REC" "$LOG"

cd "$ROOT"
source venv/bin/activate

export GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token)}"
export GH_TOKEN="$GITHUB_TOKEN"
export FLARESOLVERR_URL="${FLARESOLVERR_URL:-http://localhost:8192/v1}"

mapfile -t ROWS < <(python3 - <<'PY'
import json
pl=json.load(open('patch-config.json'))['patch_list']
s=set()
for e in pl:
    if (e['app_name'],e['source']) not in s:
        s.add((e['app_name'],e['source']))
        print(e['app_name'],e['source'])
PY
)

echo "Total app/source pairs: ${#ROWS[@]}"
fail=0
for row in "${ROWS[@]}"; do
  set -- $row
  app="$1"; src="$2"
  echo "=============================================================="
  echo ">>> BUILD $app ($src)  $(date -u +%H:%M:%S)"
  log="$LOG/${app}__${src}.log"
  if APP_NAME="$app" SOURCE="$src" python3 -m src >"$log" 2>&1; then
    echo "  OK $app/$src"
  else
    echo "  FAIL $app/$src (see $log)"
    fail=$((fail+1))
  fi
  # collect any produced apks + records regardless of exit status
  for apk in "$ROOT"/*.apk; do
    [ -e "$apk" ] || continue
    mv -f "$apk" "$OUT"/
    APP_NAME="$app" SOURCE="$src" APK_PATH="$(basename "$apk")" python3 scripts/record_build.py >/dev/null 2>&1 || true
  done
done

echo "=============================================================="
echo "Done. Failures: $fail"
echo "APKs in release-apks:"
ls -1 "$OUT"/*.apk 2>/dev/null | wc -l
