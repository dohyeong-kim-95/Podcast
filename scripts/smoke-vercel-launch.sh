#!/usr/bin/env bash

set -euo pipefail

APP_URL="${APP_URL:-${1:-}}"
API_URL="${API_URL:-${2:-}}"

if [[ -z "${APP_URL}" || -z "${API_URL}" ]]; then
  echo "usage: APP_URL=https://podcast.bubblelab.dev API_URL=https://api.run.app $0"
  echo "   or: $0 https://podcast.bubblelab.dev https://api.run.app"
  exit 1
fi

APP_URL="${APP_URL%/}"
API_URL="${API_URL%/}"

tmp_body="$(mktemp)"
tmp_headers="$(mktemp)"

cleanup() {
  rm -f "$tmp_body" "$tmp_headers"
}

trap cleanup EXIT

pass() {
  echo "[PASS] $1"
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

check_http_ok() {
  local name="$1"
  local url="$2"
  local code

  code="$(curl -sS -o "$tmp_body" -w "%{http_code}" "$url")" || fail "$name request failed"
  if [[ "$code" != "200" ]]; then
    echo "response body:" >&2
    cat "$tmp_body" >&2 || true
    fail "$name returned HTTP $code"
  fi

  pass "$name"
}

check_health() {
  local body

  body="$(curl -sS "$API_URL/health")" || fail "backend health request failed"
  if [[ "$body" != *'"status":"ok"'* && "$body" != *'"status": "ok"'* ]]; then
    echo "$body" >&2
    fail "backend health returned unexpected body"
  fi

  pass "backend health"
}

check_cors_preflight() {
  curl -sS -o /dev/null -D "$tmp_headers" \
    -X OPTIONS \
    "$API_URL/api/auth/verify" \
    -H "Origin: $APP_URL" \
    -H "Access-Control-Request-Method: POST" || fail "CORS preflight request failed"

  if ! grep -iq "^access-control-allow-origin: ${APP_URL}$" "$tmp_headers"; then
    cat "$tmp_headers" >&2
    fail "CORS allow-origin header did not match ${APP_URL}"
  fi

  pass "backend CORS preflight"
}

check_http_ok "frontend home" "$APP_URL/"
check_http_ok "frontend login" "$APP_URL/login"
check_http_ok "frontend manifest" "$APP_URL/manifest.json"
check_http_ok "frontend service worker" "$APP_URL/sw.js"
check_health
check_cors_preflight

echo
echo "Manual checks still required:"
echo "- Google redirect login on $APP_URL"
echo "- NotebookLM re-auth flow in /settings"
echo "- push permission + FCM delivery"
