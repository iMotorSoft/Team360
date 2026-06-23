#!/usr/bin/env bash
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# backend-dev.sh — Team360 backend launcher (production-like config)
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- Local overrides -------------------------------------------------------
if [[ -f "$SCRIPT_DIR/.env.backend-dev.local" ]]; then
  set -a
  source "$SCRIPT_DIR/.env.backend-dev.local"
  set +a
fi

# ---- Production-like defaults (all overridable) ----------------------------
export AUTOMATION_DIAGNOSIS_REPOSITORY="${AUTOMATION_DIAGNOSIS_REPOSITORY:-postgres}"
export TEAM360_EMBEDDING_VERSION="${TEAM360_EMBEDDING_VERSION:-team360-openai-small-1536-v1}"
export TEAM360_AI_PROVIDER="${TEAM360_AI_PROVIDER:-litellm}"
export TEAM360_LITELLM_BASE_URL="${TEAM360_LITELLM_BASE_URL:-http://127.0.0.1:4000}"
export TEAM360_LITELLM_MODEL_ALIAS="${TEAM360_LITELLM_MODEL_ALIAS:-openai_gpt-5-nano}"
export TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER="${TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER:-milvus}"
export TEAM360_MILVUS_HOST="${TEAM360_MILVUS_HOST:-127.0.0.1}"
export TEAM360_MILVUS_PORT="${TEAM360_MILVUS_PORT:-19530}"
export TEAM360_MILVUS_COLLECTION="${TEAM360_MILVUS_COLLECTION:-team360_sales_diagnosis_knowledge_v1}"
export TEAM360_DIAGNOSIS_STATE_PROVIDER="${TEAM360_DIAGNOSIS_STATE_PROVIDER:-postgres}"
export TEAM360_PUBLIC_ORGANIZATION_CODE="${TEAM360_PUBLIC_ORGANIZATION_CODE:-team360_live}"
export TEAM360_PUBLIC_WORKSPACE_CODE="${TEAM360_PUBLIC_WORKSPACE_CODE:-team360_public_site}"
export TEAM360_PUBLIC_PACKAGE_CODE="${TEAM360_PUBLIC_PACKAGE_CODE:-pkg_sales_diagnosis}"
export TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE="${TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE:-ks_team360_sales_diagnosis}"
# TEAM360_LITELLM_API_MODE is NOT set — production default auto routes to
# /v1/responses for openai_gpt-5-nano (see litellm_client.py:should_use_responses_api)

# ---- Preflight: services ---------------------------------------------------

_preflight_tcp() {
  local host="$1" port="$2" label="$3"
  if timeout 3 bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
    echo "  [ok] $label ($host:$port)"
    return 0
  else
    echo "  [fail] $label ($host:$port) — not reachable"
    return 1
  fi
}

PREFLIGHT_OK=0

echo "[backend-dev] Preflight checks..."

_preflight_tcp 127.0.0.1 5432 "PostgreSQL" || PREFLIGHT_OK=1
_preflight_tcp 127.0.0.1 19530 "Milvus" || PREFLIGHT_OK=1
_preflight_tcp 127.0.0.1 4000 "LiteLLM" || PREFLIGHT_OK=1

# LiteLLM HTTP check — 401 means "available, needs auth"
LITELLM_HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:4000/health 2>/dev/null || true)"
if [[ "$LITELLM_HTTP_CODE" == "000" || -z "$LITELLM_HTTP_CODE" ]]; then
  echo "  [fail] LiteLLM HTTP check failed (no response)"
  PREFLIGHT_OK=1
elif [[ "$LITELLM_HTTP_CODE" == "401" ]]; then
  echo "  [ok] LiteLLM reachable; authentication required."
elif [[ "$LITELLM_HTTP_CODE" == "200" ]]; then
  echo "  [ok] LiteLLM authenticated preflight: OK."
elif [[ "$LITELLM_HTTP_CODE" == "403" ]]; then
  echo "  [warn] LiteLLM reachable; credentials rejected (HTTP 403)."
elif [[ "$LITELLM_HTTP_CODE" =~ ^5[0-9][0-9]$ ]]; then
  echo "  [warn] LiteLLM reachable but returned HTTP $LITELLM_HTTP_CODE (internal error)."
else
  echo "  [info] LiteLLM HTTP status $LITELLM_HTTP_CODE"
fi

if [[ "$PREFLIGHT_OK" -ne 0 ]]; then
  echo "[backend-dev] Some services are not reachable. Continuing anyway..."
fi

echo ""

# ---- Release port 7050 -----------------------------------------------------

_free_port_7050() {
  local pid
  pid="$(ss -tlnp 2>/dev/null | grep ':7050 ' | sed -E 's/.*pid=([0-9]+),.*/\1/' | head -1 || true)"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  local cmd
  cmd="$(ps -p "$pid" -o comm= 2>/dev/null || echo 'unknown')"
  echo "[backend-dev] Port 7050 is in use by PID $pid ($cmd). Stopping..."
  kill -TERM "$pid" 2>/dev/null || true
  local waited=0
  while [[ "$waited" -lt 10 ]]; do
    if ! ss -tlnp 2>/dev/null | grep -q ':7050 '; then
      echo "[backend-dev] Port 7050 freed."
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  echo "[backend-dev] Graceful stop failed. Sending SIGKILL to PID $pid..."
  kill -KILL "$pid" 2>/dev/null || true
  sleep 1
  if ss -tlnp 2>/dev/null | grep -q ':7050 '; then
    echo "[backend-dev] ERROR: could not free port 7050. Aborting."
    exit 1
  fi
  echo "[backend-dev] Port 7050 freed (SIGKILL)."
}

_free_port_7050

# ---- Summary ---------------------------------------------------------------

echo "[backend-dev] Team360 backend production-like"
echo "[backend-dev] Repository: $AUTOMATION_DIAGNOSIS_REPOSITORY"
echo "[backend-dev] Conversation state: $TEAM360_DIAGNOSIS_STATE_PROVIDER"
echo "[backend-dev] AI provider: $TEAM360_AI_PROVIDER"
echo "[backend-dev] LiteLLM: $TEAM360_LITELLM_BASE_URL"
echo "[backend-dev] Model alias: $TEAM360_LITELLM_MODEL_ALIAS"
echo "[backend-dev] API mode: auto/productive default"
echo "[backend-dev] Retrieval: $TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER"
echo "[backend-dev] Collection: $TEAM360_MILVUS_COLLECTION"
echo "[backend-dev] Listening: http://127.0.0.1:7050"
echo ""

# ---- Start backend ---------------------------------------------------------

UVICORN="$SCRIPT_DIR/backend/.venv/bin/uvicorn"
if [[ ! -x "$UVICORN" ]]; then
  echo "[backend-dev] ERROR: uvicorn not found at $UVICORN"
  echo "[backend-dev] Run 'uv sync' or 'uv venv' in backend/ first."
  exit 1
fi

exec "$UVICORN" ls_iMotorSoft_Srv01:app \
  --host 127.0.0.1 \
  --port 7050
