#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/SrvRestAstroLS_v1/backend"
# Reuse the installed runtime; never install dependencies or source credentials.
exec .venv/bin/python -m modules.telchi.assistant.whatsapp_dev_quick "$@"
