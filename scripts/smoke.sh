#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "[SMOKE] Probing IDRA API at ${API_URL}..."

# 1. Liveness check
HEALTH_RESP=$(curl -fsS --max-time 5 "${API_URL}/health") || {
  echo "[SMOKE] FAIL: /health endpoint unreachable at ${API_URL}/health" >&2
  exit 1
}

if ! echo "${HEALTH_RESP}" | grep -q '"status":"ok"'; then
  echo "[SMOKE] FAIL: /health did not return status ok: ${HEALTH_RESP}" >&2
  exit 1
fi
echo "[SMOKE] PASS: /health liveness ok"

# 2. Deep health check
DEEP_RESP=$(curl -fsS --max-time 5 "${API_URL}/health/deep") || {
  echo "[SMOKE] FAIL: /health/deep unreachable" >&2
  exit 1
}

if ! echo "${DEEP_RESP}" | grep -q '"components"'; then
  echo "[SMOKE] FAIL: /health/deep missing components: ${DEEP_RESP}" >&2
  exit 1
fi
echo "[SMOKE] PASS: /health/deep components verified"

# 3. Citizen Assistance safe fallback / grounded response check
ASSIST_RESP=$(curl -fsS --max-time 10 -X POST "${API_URL}/assistant/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "What should I do during severe flood waterlogging in Chennai?"}') || {
  echo "[SMOKE] FAIL: /assistant/query failed" >&2
  exit 1
}

if ! echo "${ASSIST_RESP}" | grep -q '"disclaimer"'; then
  echo "[SMOKE] FAIL: /assistant/query missing safety disclaimer: ${ASSIST_RESP}" >&2
  exit 1
fi
echo "[SMOKE] PASS: /assistant/query verified"

echo "[SMOKE] ALL CHECKS PASSED."
exit 0
