#!/usr/bin/env bash
# Idempotent FortiClient VPN-TELCHI importer/connector.
# Secrets remain exclusively in the external FortiClient XML configuration.
set -uo pipefail

: "${TEAM360_TELCHI_SECRET_ROOT:?TEAM360_TELCHI_SECRET_ROOT must point to the external Telchi private root}"
if [[ "$TEAM360_TELCHI_SECRET_ROOT" != /* ]]; then
  printf '%s\n' 'SECRET_ROOT_INVALID: TEAM360_TELCHI_SECRET_ROOT must be absolute.' >&2
  exit 3
fi
CONFIG_FILE="$TEAM360_TELCHI_SECRET_ROOT/fortinet/InsidingConfig.conf.txt"
VPN_USERNAME="insiding_vpn"

emit() {
  printf '%s\n' "$1"
}

if [[ ! -f "$CONFIG_FILE" || -L "$CONFIG_FILE" ]]; then
  emit "CONFIG_INVALID"
  printf 'Fortinet configuration is missing or is a rejected symlink: %s\n' "$CONFIG_FILE" >&2
  exit 3
fi

profile_name=""
if ! profile_name="$(python3 - "$CONFIG_FILE" <<'PY'
import sys
import xml.etree.ElementTree as ET

try:
    root = ET.parse(sys.argv[1]).getroot()
except (ET.ParseError, OSError):
    raise SystemExit(2)
if root.tag != "forticlient_configuration":
    raise SystemExit(3)
connections = root.findall("./vpn/ipsecvpn/connections/connection")
if len(connections) != 1:
    raise SystemExit(4)
connection = connections[0]
def value(path):
    return (connection.findtext(path) or "").strip()
required = {
    "name": value("name"),
    "gateway": value("ike_settings/server"),
    "authentication_method": value("ike_settings/authentication_method"),
    "preshared_key": value("ike_settings/auth_data/preshared_key"),
    "username": value("ike_settings/xauth/username"),
}
if not all(required.values()):
    raise SystemExit(5)
print(required["name"])
PY
)" || [[ -z "$profile_name" ]]; then
  emit "CONFIG_INVALID"
  printf '%s\n' 'The external file is not a complete single-profile FortiClient IPsec XML configuration.' >&2
  exit 3
fi
emit "CONFIG_PRESENT"

if ! command -v forticlient >/dev/null 2>&1; then
  emit "DEPENDENCY_MISSING"
  printf '%s\n' 'FortiClient with IPsec support is required; no package was installed.' >&2
  exit 4
fi

list_output="$(forticlient vpn list 2>&1 || true)"
if printf '%s' "$list_output" | grep -qi 'trial has expired'; then
  emit "DEPENDENCY_MISSING"
  printf '%s\n' 'FortiClient is installed, but its VPN feature is unavailable because the trial/license has expired.' >&2
  exit 4
fi
if printf '%s' "$list_output" | grep -Eqi 'unavailable|unable to|error:'; then
  emit "DEPENDENCY_MISSING"
  printf '%s\n' 'FortiClient VPN CLI is unavailable.' >&2
  exit 4
fi

status_output="$(forticlient vpn status 2>&1 || true)"
if printf '%s' "$status_output" | grep -Eqi 'connected|up'; then
  if printf '%s' "$status_output" | grep -Fqi "$profile_name"; then
    emit "VPN_ALREADY_CONNECTED"
    exit 0
  fi
  emit "VPN_CONNECTION_FAILED"
  printf '%s\n' 'Another VPN session appears active; refusing to create a conflicting session.' >&2
  exit 5
fi

if ! printf '%s\n' "$list_output" | grep -Fq "$profile_name"; then
  if [[ ! -r /dev/tty ]]; then
    emit "VPN_CONNECTION_FAILED"
    printf '%s\n' 'Profile import requires an interactive TTY.' >&2
    exit 5
  fi
  printf '%s' 'FortiClient backup/import password: ' >/dev/tty
  IFS= read -r -s import_password </dev/tty
  printf '\n' >/dev/tty
  import_output="$(forticlient vpn import "$CONFIG_FILE" --password "$import_password" 2>&1 || true)"
  import_password=""
  unset import_password
  if printf '%s' "$import_output" | grep -Eqi 'trial has expired|unavailable|unable to|error:|failed'; then
    emit "VPN_CONNECTION_FAILED"
    if printf '%s' "$import_output" | grep -Eqi 'invalid password|incorrect password|wrong password'; then
      printf '%s\n' 'IMPORT_AUTHENTICATION: FortiClient rejected the backup/import password.' >&2
    else
      printf '%s\n' 'IMPORT: FortiClient could not import the external profile.' >&2
    fi
    exit 5
  fi
  list_output="$(forticlient vpn list 2>&1 || true)"
  if ! printf '%s\n' "$list_output" | grep -Fq "$profile_name"; then
    emit "VPN_CONNECTION_FAILED"
    printf '%s\n' 'Import returned without exposing the expected profile.' >&2
    exit 5
  fi
fi

# Connect interactively: FortiClient obtains XAuth credentials itself. The
# script deliberately does not accept, echo, save or place them on argv.
if ! forticlient vpn connect "$profile_name" --username "$VPN_USERNAME"; then
  emit "VPN_CONNECTION_FAILED"
  exit 5
fi

status_output="$(forticlient vpn status 2>&1 || true)"
if printf '%s' "$status_output" | grep -Eqi 'connected|up' && printf '%s' "$status_output" | grep -Fqi "$profile_name"; then
  emit "VPN_CONNECTED"
  exit 0
fi
emit "VPN_CONNECTION_FAILED"
exit 5
