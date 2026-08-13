#!/usr/bin/env bash
# Read-only Fortinet/Telchi connectivity diagnostics. Never prints VPN secrets.
set -uo pipefail

DEFAULT_TELCHI_ROOT="/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi"
TELCHI_ROOT="${TELCHI_DATA_ROOT:-$DEFAULT_TELCHI_ROOT}"
CONFIG_FILE="$TELCHI_ROOT/access/fortinet/InsidingConfig.conf.txt"
SAP_HANA_HOST="192.168.20.20"
SAP_HANA_PORT="30015"

config_ok=0
client_ok=0
session_ok=0
tunnel_ok=0
routes_ok=0
network_state="PENDING"
hana_route_ok=0
hana_tcp_ok=0
profile_name=""
config_networks_known=0

status() {
  printf '%-18s %s\n' "$1" "$2"
}

redact_forticlient_output() {
  sed -E \
    -e 's/((password|passwd|token|secret|psk|cookie|private[_ -]?key)[=: ]+)[^ ]+/\1[REDACTED]/Ig' \
    -e 's/(--(password|passwd|token|otp|cookie)[= ]+)[^ ]+/\1[REDACTED]/Ig'
}

parse_output=""
if [[ -f "$CONFIG_FILE" && ! -L "$CONFIG_FILE" ]]; then
  if parse_output="$(python3 - "$CONFIG_FILE" <<'PY'
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
try:
    root = ET.parse(path).getroot()
except (ET.ParseError, OSError):
    raise SystemExit(2)
if root.tag != "forticlient_configuration":
    raise SystemExit(3)
connections = root.findall("./vpn/ipsecvpn/connections/connection")
if len(connections) != 1:
    raise SystemExit(4)
connection = connections[0]
name = (connection.findtext("name") or "").strip()
gateway = (connection.findtext("ike_settings/server") or "").strip()
auth = (connection.findtext("ike_settings/authentication_method") or "").strip()
psk = (connection.findtext("ike_settings/auth_data/preshared_key") or "").strip()
username = (connection.findtext("ike_settings/xauth/username") or "").strip()
if not name or not gateway or not auth or not psk or not username:
    raise SystemExit(5)
networks = []
for network in connection.findall("ipsec_settings/remote_networks/network"):
    address = (network.findtext("addr") or "").strip()
    mask = (network.findtext("mask") or "").strip()
    if address:
        networks.append((address, mask))
specific = [(a, m) for a, m in networks if a not in {"0.0.0.0", "::/0"}]
# Only emit non-sensitive control metadata. Never emit gateway, username or PSK.
print("PROFILE=" + name)
print("SPECIFIC_NETWORKS=" + ("1" if specific else "0"))
PY
)"; then
    profile_name="$(printf '%s\n' "$parse_output" | awk -F= '$1 == "PROFILE" {print substr($0, index($0, "=") + 1); exit}')"
    config_networks_known="$(printf '%s\n' "$parse_output" | awk -F= '$1 == "SPECIFIC_NETWORKS" {print $2; exit}')"
    config_ok=1
    status "CONFIG" "PASS (FortiClient XML; profile $profile_name)"
  else
    status "CONFIG" "FAIL (CONFIG_INVALID)"
  fi
else
  status "CONFIG" "FAIL (missing or symlink rejected: $CONFIG_FILE)"
fi

vpn_probe=""
if command -v forticlient >/dev/null 2>&1; then
  vpn_probe="$(forticlient vpn list 2>&1 || true)"
  if printf '%s' "$vpn_probe" | grep -qi 'trial has expired'; then
    status "VPN CLIENT" "FAIL (FortiClient installed but VPN trial/license unavailable)"
  elif printf '%s' "$vpn_probe" | grep -Eqi 'unavailable|unable to|error:'; then
    status "VPN CLIENT" "FAIL (FortiClient VPN CLI unavailable)"
  else
    client_ok=1
    version_output="$(forticlient version 2>&1 || true)"
    version="$(printf '%s\n' "$version_output" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)"
    status "VPN CLIENT" "PASS (FortiClient${version:+ $version})"
  fi
elif command -v openfortivpn >/dev/null 2>&1; then
  # The received file is IPsec/IKEv1, not an SSL-VPN openfortivpn profile.
  status "VPN CLIENT" "FAIL (openfortivpn cannot consume the received IPsec profile)"
else
  status "VPN CLIENT" "FAIL (DEPENDENCY_MISSING)"
fi

vpn_status=""
if (( client_ok )); then
  vpn_status="$(forticlient vpn status 2>&1 || true)"
  if printf '%s' "$vpn_status" | grep -Eqi 'connected|up'; then
    if [[ -z "$profile_name" ]] || printf '%s' "$vpn_status" | grep -Fqi "$profile_name"; then
      session_ok=1
    fi
  fi
fi
if (( session_ok )); then
  status "VPN SESSION" "PASS"
else
  status "VPN SESSION" "FAIL (not connected or status unavailable)"
fi

# FortiClient IPsec commonly exposes ppp/forti interfaces; require both an
# active session and a non-physical candidate to avoid treating Docker as VPN.
tunnel_name=""
while IFS= read -r candidate; do
  [[ -n "$candidate" ]] || continue
  tunnel_name="$candidate"
  break
done < <(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -E '^(ppp|tun|tap|forti|fct|ipsec|xfrm)' || true)
if (( session_ok )) && [[ -n "$tunnel_name" ]]; then
  tunnel_ok=1
  status "TUNNEL" "PASS ($tunnel_name)"
else
  status "TUNNEL" "FAIL (no active Fortinet tunnel identified)"
fi

if (( tunnel_ok )) && ip -4 route show dev "$tunnel_name" 2>/dev/null | grep -q .; then
  routes_ok=1
  route_count="$(ip -4 route show dev "$tunnel_name" 2>/dev/null | wc -l)"
  status "ROUTES" "PASS ($route_count route(s) via tunnel)"
else
  status "ROUTES" "FAIL (no routes via an identified tunnel)"
fi

status "SAP HANA TARGET" "$SAP_HANA_HOST:$SAP_HANA_PORT"

hana_route="$(ip -4 route get "$SAP_HANA_HOST" 2>&1 || true)"
hana_route_interface="$(printf '%s\n' "$hana_route" | awk '{for (i = 1; i <= NF; i++) if ($i == "dev") {print $(i + 1); exit}}')"
if (( session_ok && tunnel_ok )) && [[ -n "$hana_route_interface" && "$hana_route_interface" == "$tunnel_name" ]] && ! printf '%s' "$hana_route" | grep -Eqi 'unreachable|prohibit|blackhole'; then
  hana_route_ok=1
  status "SAP HANA ROUTE" "PASS (interface $hana_route_interface)"
else
  status "SAP HANA ROUTE" "FAIL (NO_ROUTE via active VPN tunnel)"
fi

if (( hana_route_ok )); then
  tcp_output="$(timeout 6 nc -vz -w 5 "$SAP_HANA_HOST" "$SAP_HANA_PORT" 2>&1)"
  tcp_rc=$?
  if (( tcp_rc == 0 )); then
    hana_tcp_ok=1
    network_state="PASS"
    status "SAP HANA TCP" "PASS"
  elif printf '%s' "$tcp_output" | grep -qi 'refused'; then
    network_state="FAIL"
    status "SAP HANA TCP" "FAIL (CONNECTION_REFUSED)"
  elif printf '%s' "$tcp_output" | grep -Eqi 'no route'; then
    network_state="FAIL"
    status "SAP HANA TCP" "FAIL (NO_ROUTE)"
  elif printf '%s' "$tcp_output" | grep -Eqi 'unreachable'; then
    network_state="FAIL"
    status "SAP HANA TCP" "FAIL (HOST_UNREACHABLE)"
  else
    network_state="FAIL"
    status "SAP HANA TCP" "FAIL (TIMEOUT)"
  fi
else
  status "SAP HANA TCP" "FAIL (NO_ROUTE)"
fi
status "TELCHI NETWORK" "$network_state"

if (( config_ok && client_ok && session_ok && tunnel_ok && routes_ok && hana_route_ok && hana_tcp_ok )) && [[ "$network_state" == "PASS" ]]; then
  exit 0
fi
exit 2
