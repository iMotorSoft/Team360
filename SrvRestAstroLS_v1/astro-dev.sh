#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# astro-dev.sh — Team360 Astro development launcher
#
# Development only. Requires IS_REST_PRO=false in global.js.
# Production is served by Nginx and does not use this launcher.
# ---------------------------------------------------------------------------
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASTRO_DIR="$SCRIPT_DIR/astro"
GLOBAL_JS="$ASTRO_DIR/src/components/global.js"
ASTRO_HOST="${ASTRO_HOST:-127.0.0.1}"
ASTRO_PORT="${ASTRO_PORT:-3050}"

# ---- Logging ---------------------------------------------------------------

_log() { printf '[astro-dev] %s\n' "$*"; }
_ok()   { printf '  [ok] %s\n' "$*"; }
_warn() { printf '  [warn] %s\n' "$*"; }
_fail() { printf '  [fail] %s\n' "$*" >&2; }

_die() {
  _log "ERROR: $*"
  exit 1
}

# ---- IS_REST_PRO guard -----------------------------------------------------

_log "Team360 Astro development launcher"
_log "Astro directory: $ASTRO_DIR"

if [[ ! -f "$GLOBAL_JS" ]]; then
  _die "global.js not found at $GLOBAL_JS"
fi

# Extract IS_REST_PRO value, tolerate flexible whitespace
IS_REST_PRO_LINES="$(grep -c 'IS_REST_PRO' "$GLOBAL_JS" || true)"
if [[ "$IS_REST_PRO_LINES" -eq 0 ]]; then
  _die "IS_REST_PRO not found in $GLOBAL_JS"
fi

IS_REST_PRO_VALUES="$(grep -Eo 'IS_REST_PRO\s*=\s*(true|false)' "$GLOBAL_JS" | sed 's/.*=//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort -u || true)"
VALUE_COUNT="$(printf '%s\n' "$IS_REST_PRO_VALUES" | grep -c . || true)"

if [[ "$VALUE_COUNT" -ne 1 ]]; then
  _log "IS_REST_PRO found $VALUE_COUNT distinct value(s) in $GLOBAL_JS:"
  grep -n 'IS_REST_PRO' "$GLOBAL_JS"
  _die "IS_REST_PRO must have exactly one definition (true or false)"
fi

IS_REST_PRO_VALUE="$IS_REST_PRO_VALUES"

if [[ "$IS_REST_PRO_VALUE" == "true" ]]; then
  _log "ERROR: IS_REST_PRO=true."
  _log "Astro dev will not start because the frontend is configured for production."
  _die "Set IS_REST_PRO=false in $GLOBAL_JS for local development."
fi

if [[ "$IS_REST_PRO_VALUE" != "false" ]]; then
  _die "Unexpected IS_REST_PRO value: $IS_REST_PRO_VALUE (expected false)"
fi

_ok "IS_REST_PRO: false"

# ---- Dependencies ----------------------------------------------------------

for cmd in npx node; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    _die "required command not found: $cmd"
  fi
done

# ---- Port 3050 management --------------------------------------------------

_free_astro_port() {
  local pid
  pid="$(ss -H -ltnp "sport = :${ASTRO_PORT}" 2>/dev/null | grep -oE 'pid=[0-9]+' | sed 's/^pid=//' | head -1 || true)"

  if [[ -z "$pid" ]]; then
    _ok "Port ${ASTRO_PORT}: free"
    return 0
  fi

  local cmd
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || echo 'unknown')"
  _log "Port ${ASTRO_PORT} is in use by PID $pid: $cmd"

  _log "Sending SIGTERM to PID $pid..."
  kill -TERM "$pid" 2>/dev/null || true

  local waited=0
  while [[ "$waited" -lt 10 ]]; do
    if ! ss -H -ltnp "sport = :${ASTRO_PORT}" 2>/dev/null | grep -q .; then
      _ok "Port ${ASTRO_PORT} freed."
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  _log "Sending SIGKILL to PID $pid..."
  kill -KILL "$pid" 2>/dev/null || true
  sleep 1

  if ss -H -ltnp "sport = :${ASTRO_PORT}" 2>/dev/null | grep -q .; then
    _die "could not free port ${ASTRO_PORT}"
  fi

  _ok "Port ${ASTRO_PORT} freed (SIGKILL)."
}

_free_astro_port

# ---- Start Astro -----------------------------------------------------------

_log "Starting Astro at http://${ASTRO_HOST}:${ASTRO_PORT}"
printf '\n'

cd "$ASTRO_DIR"
exec npx astro dev \
  --host "$ASTRO_HOST" \
  --port "$ASTRO_PORT"
