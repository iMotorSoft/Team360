#!/usr/bin/env bash
# Independent TelchiAI DEV control. Never manages Evolution or Cloudflare.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd -- "$SCRIPT_DIR/../../backend" && pwd)"
if [[ $# -lt 1 || ! "$1" =~ ^(start|stop|status)$ ]]; then
  printf 'Usage: %s {start|stop|status} [--config PRIVATE_JSON]\n' "$0" >&2
  exit 2
fi
if [[ ! -x "$BACKEND/.venv/bin/python" ]]; then
  printf 'Backend virtualenv unavailable; no service started.\n' >&2
  exit 1
fi
cd -- "$BACKEND"
# Sanitize before Python imports too (PYTHONPATH/PYTHONHOME must not win).
exec /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  "$BACKEND/.venv/bin/python" -m modules.telchi.assistant.whatsapp_dev_lifecycle "$@"
