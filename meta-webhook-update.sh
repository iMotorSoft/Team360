#!/usr/bin/env bash
# Evolution/Meta DEV only. Credentials must already be exported; never source secrets.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$ROOT/SrvRestAstroLS_v1/backend/modules/messaging/providers/evolution/meta_webhook_update.py" "$@"
