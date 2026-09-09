#!/usr/bin/env bash
# Read-only strongSwan/Telchi diagnostics. Never prints VPN secrets or keys.
set -uo pipefail
set +x

: "${TEAM360_TELCHI_SECRET_ROOT:?TEAM360_TELCHI_SECRET_ROOT must point to the external Telchi private root}"
if [[ "$TEAM360_TELCHI_SECRET_ROOT" != /* ]]; then
  printf '%s\n' 'SECRET_ROOT_INVALID: TEAM360_TELCHI_SECRET_ROOT must be absolute.' >&2
  exit 3
fi
CONFIG_FILE="$TEAM360_TELCHI_SECRET_ROOT/fortinet/InsidingConfig.conf.txt"
SAP_HANA_HOST="192.168.20.20"
SAP_HANA_PORT="30015"

config_ok=0
client_ok=0
service_ok=0
loaded_ok=0
ike_ok=0
xauth_ok=0
child_ok=0
xfrm_state_ok=0
xfrm_policy_ok=0
routes_ok=0
hana_tcp_ok=0
network_state="PENDING"

status() {
  printf '%-18s %s\n' "$1" "$2"
}

if [[ -f "$CONFIG_FILE" && ! -L "$CONFIG_FILE" ]] && python3 - "$CONFIG_FILE" "$SAP_HANA_HOST" <<'PY' >/dev/null 2>&1
import ipaddress
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
connection = root.find("./vpn/ipsecvpn/connections/connection")
if connection is None:
    raise SystemExit(2)
value = lambda path: (connection.findtext(path) or "").strip()
if value("name") != "VPN-TELCHI" or value("ike_settings/version") != "1":
    raise SystemExit(3)
if value("ike_settings/authentication_method").lower() != "preshared key":
    raise SystemExit(4)
target = ipaddress.ip_address(sys.argv[2])
selectors = []
for node in connection.findall("ipsec_settings/remote_networks/network"):
    address = (node.findtext("addr") or "").strip()
    mask = (node.findtext("mask") or "").strip()
    if address:
        try:
            selectors.append(ipaddress.ip_network(f"{address}/{mask or '255.255.255.255'}", strict=False))
        except ValueError:
            continue
if not any(target in selector for selector in selectors):
    raise SystemExit(5)
PY
then
  config_ok=1
  status "CONFIG" "PASS (VPN-TELCHI; IKEv1; HANA selector covered)"
else
  status "CONFIG" "FAIL"
fi

if command -v swanctl >/dev/null 2>&1 && dpkg-query -W charon-systemd strongswan-swanctl libcharon-extra-plugins >/dev/null 2>&1; then
  client_ok=1
  version="$(dpkg-query -W -f='${Version}' strongswan-swanctl 2>/dev/null | cut -d- -f1)"
  status "STRONGSWAN CLIENT" "PASS (${version:-installed})"
else
  status "STRONGSWAN CLIENT" "FAIL (DEPENDENCY_MISSING)"
fi

if systemctl is-active --quiet strongswan.service 2>/dev/null; then
  service_ok=1
  status "STRONGSWAN SERVICE" "PASS (active)"
else
  status "STRONGSWAN SERVICE" "FAIL (inactive)"
fi

list_conns=""
list_sas=""
privileged=0
if (( service_ok )) && [[ -r /dev/tty ]]; then
  sudo -v </dev/tty >/dev/null 2>&1 || true
fi
if (( service_ok )) && sudo -n true >/dev/null 2>&1; then
  privileged=1
  list_conns="$(sudo -n swanctl --list-conns 2>/dev/null || true)"
  list_sas="$(sudo -n swanctl --list-sas 2>/dev/null || true)"
fi

if printf '%s\n' "$list_conns" | grep -Eq '^vpn-telchi:'; then
  loaded_ok=1
  status "CONFIG LOADED" "PASS"
else
  status "CONFIG LOADED" "FAIL"
fi

if printf '%s\n' "$list_sas" | grep -Eq '^vpn-telchi:.*ESTABLISHED'; then
  ike_ok=1
  status "IKE SA" "PASS"
else
  status "IKE SA" "FAIL"
fi
status "IKE VERSION" "IKEv1"

if (( ike_ok )); then
  status "PSK AUTH" "PASS"
else
  status "PSK AUTH" "FAIL"
fi
if (( ike_ok )) && printf '%s\n' "$list_conns" | grep -Eqi 'xauth'; then
  xauth_ok=1
  status "XAUTH" "PASS"
else
  status "XAUTH" "FAIL"
fi

if printf '%s\n' "$list_sas" | grep -Eq '^[[:space:]]+telchi:.*INSTALLED'; then
  child_ok=1
  status "CHILD SA" "PASS"
else
  status "CHILD SA" "FAIL"
fi

if (( privileged )) && sudo -n ip xfrm state 2>/dev/null | grep -q '^src '; then
  xfrm_state_ok=1
  status "XFRM STATE" "PASS"
else
  status "XFRM STATE" "FAIL"
fi

if (( privileged )) && sudo -n ip xfrm policy 2>/dev/null | python3 -c '
import ipaddress, re, sys
target = ipaddress.ip_address("192.168.20.20")
text = sys.stdin.read()
networks = []
for value in re.findall(r"\bdst\s+([0-9.]+/[0-9]+)", text):
    try:
        networks.append(ipaddress.ip_network(value, strict=False))
    except ValueError:
        pass
raise SystemExit(0 if any(target in network for network in networks) else 1)
'; then
  xfrm_policy_ok=1
  status "XFRM POLICY" "PASS (covers $SAP_HANA_HOST)"
else
  status "XFRM POLICY" "FAIL"
fi

route_220="$(ip -4 route show table 220 2>&1 || true)"
effective_route="$(ip -4 route get "$SAP_HANA_HOST" 2>&1 || true)"
if (( xfrm_policy_ok )) && [[ -n "$route_220" ]] && printf '%s' "$route_220" | grep -Eq '\bsrc [0-9.]+' && ! printf '%s' "$effective_route" | grep -Eqi 'error|unreachable|prohibit|blackhole'; then
  routes_ok=1
  status "ROUTES" "PASS (table 220 + XFRM)"
  status "SAP HANA ROUTE" "PASS (policy-based IPsec)"
else
  status "ROUTES" "FAIL"
  status "SAP HANA ROUTE" "FAIL (NO_ROUTE_VIA_VPN)"
fi

status "SAP HANA TARGET" "$SAP_HANA_HOST:$SAP_HANA_PORT"
if (( ike_ok && xauth_ok && child_ok && xfrm_state_ok && xfrm_policy_ok && routes_ok )); then
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

if (( config_ok && client_ok && service_ok && loaded_ok && ike_ok && xauth_ok && child_ok && xfrm_state_ok && xfrm_policy_ok && routes_ok && hana_tcp_ok )); then
  exit 0
fi
exit 2
