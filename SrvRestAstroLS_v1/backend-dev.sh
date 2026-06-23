#!/usr/bin/env bash
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# backend-dev.sh — Team360 backend launcher (production-like configuration)
#
# Responsibilities:
# - Load optional local overrides.
# - Configure the backend like production.
# - Verify PostgreSQL, Milvus and LiteLLM without managing them.
# - Safely release port 7050.
# - Start the Team360 backend in the foreground.
#
# This script does NOT start, stop or restart:
# - PostgreSQL
# - Milvus
# - LiteLLM
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_HOST="${TEAM360_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${TEAM360_BACKEND_PORT:-7050}"

# PostgreSQL currently follows the production-local configuration.
POSTGRES_HOST="${TEAM360_POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${TEAM360_POSTGRES_PORT:-5432}"

# ---- Logging ---------------------------------------------------------------

_log() {
  printf '[backend-dev] %s\n' "$*"
}

_ok() {
  printf '  [ok] %s\n' "$*"
}

_warn() {
  printf '  [warn] %s\n' "$*"
}

_fail() {
  printf '  [fail] %s\n' "$*" >&2
}

_die() {
  _log "ERROR: $*"
  exit 1
}

_on_error() {
  local exit_code=$?
  local line_number="${1:-unknown}"

  _log "ERROR: command failed at line ${line_number} with exit code ${exit_code}."
  exit "$exit_code"
}

trap '_on_error "$LINENO"' ERR

# ---- Required commands -----------------------------------------------------

_require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    _die "required command not found: ${command_name}"
  fi
}

for command_name in timeout curl ss sed grep ps kill sleep; do
  _require_command "$command_name"
done

# ---- Local overrides -------------------------------------------------------

LOCAL_ENV_FILE="$SCRIPT_DIR/.env.backend-dev.local"

if [[ -f "$LOCAL_ENV_FILE" ]]; then
  _log "Loading local overrides from .env.backend-dev.local"

  set -a
  # shellcheck disable=SC1090
  source "$LOCAL_ENV_FILE"
  set +a
fi

# ---- Production-like defaults ---------------------------------------------
#
# Every value can be overridden by:
# - the current shell environment; or
# - .env.backend-dev.local
#
# No credentials are defined here.

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

# Intentionally not defined.
#
# Production currently relies on automatic routing:
# openai_gpt-5-nano -> /v1/responses
#
# Do not define TEAM360_LITELLM_API_MODE here unless production is changed too.

# ---- URL parsing -----------------------------------------------------------

_parse_http_url() {
  local url="$1"
  local default_port

  if [[ "$url" =~ ^https:// ]]; then
    default_port="443"
  elif [[ "$url" =~ ^http:// ]]; then
    default_port="80"
  else
    _die "unsupported LiteLLM URL: ${url}. Expected http:// or https://"
  fi

  local without_scheme="${url#*://}"
  local authority="${without_scheme%%/*}"

  if [[ "$authority" == *:* ]]; then
    LITELLM_HOST="${authority%%:*}"
    LITELLM_PORT="${authority##*:}"
  else
    LITELLM_HOST="$authority"
    LITELLM_PORT="$default_port"
  fi

  if [[ -z "$LITELLM_HOST" || -z "$LITELLM_PORT" ]]; then
    _die "could not parse LiteLLM host and port from ${url}"
  fi

  if [[ ! "$LITELLM_PORT" =~ ^[0-9]+$ ]]; then
    _die "invalid LiteLLM port parsed from ${url}: ${LITELLM_PORT}"
  fi
}

_parse_http_url "$TEAM360_LITELLM_BASE_URL"

# ---- TCP preflight ---------------------------------------------------------

_preflight_tcp() {
  local host="$1"
  local port="$2"
  local label="$3"

  if timeout 3 bash -c "echo > /dev/tcp/${host}/${port}" 2>/dev/null; then
    _ok "${label} (${host}:${port})"
    return 0
  fi

  _fail "${label} (${host}:${port}) is not reachable"
  return 1
}

# ---- LiteLLM HTTP preflight ------------------------------------------------

_preflight_litellm_http() {
  local models_url="${TEAM360_LITELLM_BASE_URL%/}/v1/models"
  local response_file
  local http_code

  response_file="$(mktemp)"
  trap 'rm -f "$response_file"' RETURN

  local curl_args=(
    --silent
    --show-error
    --connect-timeout 3
    --max-time 10
    --output "$response_file"
    --write-out '%{http_code}'
  )

  local auth_was_used=0

  if [[ -n "${LITELLM_MASTER_KEY:-}" ]]; then
    curl_args+=(
      --header "Authorization: Bearer ${LITELLM_MASTER_KEY}"
    )
    auth_was_used=1
  fi

  http_code="$(
    curl "${curl_args[@]}" "$models_url" 2>/dev/null || true
  )"

  case "$http_code" in
    200)
      if [[ "$auth_was_used" -eq 1 ]]; then
        _ok "LiteLLM authenticated preflight"
      else
        _ok "LiteLLM HTTP preflight"
      fi

      if grep -q '"openai_gpt-5-nano"' "$response_file"; then
        _ok "LiteLLM model alias registered: openai_gpt-5-nano"
      else
        _warn "LiteLLM responded successfully, but openai_gpt-5-nano was not found in /v1/models"
      fi
      ;;

    401)
      if [[ "$auth_was_used" -eq 1 ]]; then
        _fail "LiteLLM rejected LITELLM_MASTER_KEY (HTTP 401)"
        return 1
      fi

      _ok "LiteLLM reachable; authentication required"
      _warn "LITELLM_MASTER_KEY is not available in this shell"
      _warn "The backend may still resolve credentials through its existing configuration"
      ;;

    403)
      if [[ "$auth_was_used" -eq 1 ]]; then
        _fail "LiteLLM rejected the supplied credentials (HTTP 403)"
      else
        _fail "LiteLLM is reachable but denied access (HTTP 403)"
      fi
      return 1
      ;;

    000|"")
      _fail "LiteLLM HTTP check returned no response"
      return 1
      ;;

    5??)
      _fail "LiteLLM returned an internal error (HTTP ${http_code})"
      return 1
      ;;

    *)
      _fail "LiteLLM returned unexpected HTTP status ${http_code}"
      return 1
      ;;
  esac

  return 0
}

# ---- Run service preflight -------------------------------------------------

_log "Preflight checks..."

PREFLIGHT_FAILED=0

_preflight_tcp \
  "$POSTGRES_HOST" \
  "$POSTGRES_PORT" \
  "PostgreSQL" \
  || PREFLIGHT_FAILED=1

_preflight_tcp \
  "$TEAM360_MILVUS_HOST" \
  "$TEAM360_MILVUS_PORT" \
  "Milvus" \
  || PREFLIGHT_FAILED=1

_preflight_tcp \
  "$LITELLM_HOST" \
  "$LITELLM_PORT" \
  "LiteLLM TCP" \
  || PREFLIGHT_FAILED=1

if [[ "$PREFLIGHT_FAILED" -eq 0 ]]; then
  _preflight_litellm_http || PREFLIGHT_FAILED=1
fi

if [[ "$PREFLIGHT_FAILED" -ne 0 ]]; then
  _die "required production-like services are unavailable. Backend will not be started."
fi

printf '\n'

# ---- Port 7050 helpers -----------------------------------------------------

_port_listener_lines() {
  ss -H -ltnp "sport = :${BACKEND_PORT}" 2>/dev/null || true
}

_port_is_in_use() {
  [[ -n "$(_port_listener_lines)" ]]
}

_listener_pids() {
  _port_listener_lines \
    | grep -oE 'pid=[0-9]+' \
    | sed 's/^pid=//' \
    | sort -u
}

_show_remaining_listeners() {
  local listeners
  listeners="$(_port_listener_lines)"

  if [[ -n "$listeners" ]]; then
    _log "Remaining listeners on port ${BACKEND_PORT}:"
    printf '%s\n' "$listeners" >&2
  fi
}

# ---- Safely release backend port ------------------------------------------

_free_backend_port() {
  if ! _port_is_in_use; then
    _log "Port ${BACKEND_PORT} is free."
    return 0
  fi

  local pids=()
  local pid
  local cmd

  mapfile -t pids < <(_listener_pids)

  if [[ "${#pids[@]}" -eq 0 ]]; then
    _show_remaining_listeners
    _die "port ${BACKEND_PORT} is occupied, but its listener PID could not be identified safely"
  fi

  _log "Port ${BACKEND_PORT} is occupied."

  for pid in "${pids[@]}"; do
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    cmd="${cmd:-unknown}"

    _log "Listener PID ${pid}: ${cmd}"
  done

  for pid in "${pids[@]}"; do
    _log "Sending SIGTERM to PID ${pid}..."
    kill -TERM "$pid" 2>/dev/null || true
  done

  local waited=0

  while [[ "$waited" -lt 10 ]]; do
    if ! _port_is_in_use; then
      _log "Port ${BACKEND_PORT} freed gracefully."
      return 0
    fi

    sleep 1
    waited=$((waited + 1))
  done

  _warn "Graceful stop did not release port ${BACKEND_PORT} after 10 seconds."

  # Refresh the PID list in case the listener changed during shutdown.
  mapfile -t pids < <(_listener_pids)

  if [[ "${#pids[@]}" -eq 0 ]]; then
    _show_remaining_listeners
    _die "port ${BACKEND_PORT} remains occupied, but its listener PID cannot be identified safely"
  fi

  for pid in "${pids[@]}"; do
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    cmd="${cmd:-unknown}"

    _warn "Sending SIGKILL to PID ${pid}: ${cmd}"
    kill -KILL "$pid" 2>/dev/null || true
  done

  sleep 1

  if _port_is_in_use; then
    _show_remaining_listeners
    _die "could not free port ${BACKEND_PORT}"
  fi

  _log "Port ${BACKEND_PORT} freed with SIGKILL."
}

_free_backend_port

# ---- Validate backend environment -----------------------------------------

UVICORN="$SCRIPT_DIR/backend/.venv/bin/uvicorn"

if [[ ! -x "$UVICORN" ]]; then
  _log "ERROR: uvicorn not found or not executable at:"
  _log "       ${UVICORN}"
  _log "Prepare the backend environment with:"
  _log "       cd \"$SCRIPT_DIR/backend\" && uv sync"
  exit 1
fi

# ---- Configuration summary ------------------------------------------------

printf '\n'
_log "Team360 backend production-like"
_log "Repository: ${AUTOMATION_DIAGNOSIS_REPOSITORY}"
_log "Conversation state: ${TEAM360_DIAGNOSIS_STATE_PROVIDER}"
_log "AI provider: ${TEAM360_AI_PROVIDER}"
_log "LiteLLM: ${TEAM360_LITELLM_BASE_URL}"
_log "Model alias: ${TEAM360_LITELLM_MODEL_ALIAS}"
_log "API mode: auto / production default"
_log "Retrieval: ${TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER}"
_log "Milvus: ${TEAM360_MILVUS_HOST}:${TEAM360_MILVUS_PORT}"
_log "Collection: ${TEAM360_MILVUS_COLLECTION}"
_log "Organization: ${TEAM360_PUBLIC_ORGANIZATION_CODE}"
_log "Workspace: ${TEAM360_PUBLIC_WORKSPACE_CODE}"
_log "Package: ${TEAM360_PUBLIC_PACKAGE_CODE}"
_log "Knowledge scope: ${TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE}"
_log "Application: ls_iMotorSoft_Srv01:app"
_log "Listening: http://${BACKEND_HOST}:${BACKEND_PORT}"
printf '\n'

# ---- Start backend ---------------------------------------------------------
#
# exec replaces the shell process so that:
# - Ctrl+C reaches Uvicorn directly;
# - termination signals are propagated correctly;
# - the resulting exit code belongs to the backend process.

exec "$UVICORN" ls_iMotorSoft_Srv01:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT"

