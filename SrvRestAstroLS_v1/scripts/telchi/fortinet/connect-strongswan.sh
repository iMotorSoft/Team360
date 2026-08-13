#!/usr/bin/env bash
# Headless IKEv1/XAuth-PSK connector for the received VPN-TELCHI profile.
# Secrets are read without echo and streamed to charon; they are never saved.
set -uo pipefail
set +x
umask 077

DEFAULT_TELCHI_ROOT="/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi"
TELCHI_ROOT="${TELCHI_DATA_ROOT:-$DEFAULT_TELCHI_ROOT}"
CONFIG_FILE="$TELCHI_ROOT/access/fortinet/InsidingConfig.conf.txt"
VPN_USERNAME="insiding_vpn"
SAP_HANA_HOST="192.168.20.20"

ike_psk=""
xauth_password=""
credentials_config=""
cleanup() {
  ike_psk=""
  xauth_password=""
  credentials_config=""
  unset ike_psk xauth_password credentials_config
}
trap cleanup EXIT HUP INT TERM

for dependency in python3 sudo swanctl; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'DEPENDENCY_MISSING: %s\n' "$dependency" >&2
    exit 4
  fi
done
if [[ ! -f "$CONFIG_FILE" || -L "$CONFIG_FILE" ]]; then
  printf 'CONFIG_INVALID\n' >&2
  exit 3
fi

# Produce only non-secret strongSwan connection data. The FortiClient ENC PSK
# is deliberately rejected because it is not the original IKE shared secret.
if ! connection_config="$(python3 - "$CONFIG_FILE" "$SAP_HANA_HOST" <<'PY'
import ipaddress
import sys
import xml.etree.ElementTree as ET

path, hana_host = sys.argv[1:]
root = ET.parse(path).getroot()
connection = root.find("./vpn/ipsecvpn/connections/connection")
if connection is None:
    raise SystemExit(2)

def value(path):
    return (connection.findtext(path) or "").strip()

if value("name") != "VPN-TELCHI":
    raise SystemExit(3)
if value("ike_settings/version") != "1":
    raise SystemExit(4)
if value("ike_settings/authentication_method").lower() != "preshared key":
    raise SystemExit(5)
if not value("ike_settings/auth_data/preshared_key").lower().startswith("enc "):
    raise SystemExit(6)

gateway = value("ike_settings/server")
if not gateway:
    raise SystemExit(7)

selectors = []
for network in connection.findall("ipsec_settings/remote_networks/network"):
    address = (network.findtext("addr") or "").strip()
    mask = (network.findtext("mask") or "").strip()
    if not address:
        continue
    try:
        selectors.append(ipaddress.ip_network(f"{address}/{mask or '255.255.255.255'}", strict=False))
    except ValueError:
        continue
target = ipaddress.ip_address(hana_host)
if not selectors or not any(target in network for network in selectors):
    raise SystemExit(8)

ike_pairs = []
for proposal in connection.findall("ike_settings/proposals/proposal"):
    parts = [part.strip().lower() for part in (proposal.text or "").split("|")]
    if len(parts) == 2 and all(parts):
        ike_pairs.append("-".join(parts))
dh_map = {"5": "modp1536", "14": "modp2048"}
dh_groups = [dh_map[item] for item in value("ike_settings/dhgroup").split(";") if item in dh_map]
ike_proposals = [f"{pair}-{group}" for pair in ike_pairs for group in dh_groups]

esp_pairs = []
for proposal in connection.findall("ipsec_settings/proposals/proposal"):
    parts = [part.strip().lower() for part in (proposal.text or "").split("|")]
    if len(parts) == 2 and all(parts):
        esp_pairs.append("-".join(parts))
esp_dh = dh_map.get(value("ipsec_settings/dhgroup"), "modp1536")
esp_proposals = [f"{pair}-{esp_dh}" for pair in esp_pairs]
if not ike_proposals or not esp_proposals:
    raise SystemExit(9)

remote_ts = ",".join(str(network) for network in selectors)
ike_lifetime = value("ike_settings/key_life") or "86400"
print("connections {")
print("  vpn-telchi {")
print("    version = 1")
print("    aggressive = no")
print(f"    remote_addrs = {gateway}")
print("    vips = 0.0.0.0")
print(f"    proposals = {','.join(ike_proposals)}")
print(f"    reauth_time = {ike_lifetime}s")
print("    dpd_delay = 5s")
print("    local-psk { auth = psk }")
print("    local-xauth {")
print("      auth = xauth")
print("      xauth_id = insiding_vpn")
print("    }")
print("    remote-psk { auth = psk }")
print("    children {")
print("      telchi {")
print(f"        remote_ts = {remote_ts}")
print(f"        esp_proposals = {','.join(esp_proposals)}")
print("        mode = tunnel")
print("        start_action = none")
print("        dpd_action = clear")
print("      }")
print("    }")
print("  }")
print("}")
PY
)"; then
  printf '%s\n' 'CONFIG_INVALID: FortiClient profile cannot be mapped safely to strongSwan.' >&2
  exit 3
fi

sudo -v </dev/tty
printf '%s' 'Original IKE pre-shared key (not backup password): ' >/dev/tty
IFS= read -r -s ike_psk </dev/tty
printf '\n' >/dev/tty
printf '%s' 'VPN XAuth password: ' >/dev/tty
IFS= read -r -s xauth_password </dev/tty
printf '\n' >/dev/tty
if [[ -z "$ike_psk" || -z "$xauth_password" ]]; then
  printf '%s\n' 'AUTHENTICATION_INPUT_MISSING' >&2
  exit 5
fi

swan_quote() {
  local input="$1"
  input="${input//\\/\\\\}"
  input="${input//\"/\\\"}"
  printf '"%s"' "$input"
}

credentials_config=$'secrets {\n  ike-telchi {\n    secret = '
credentials_config+="$(swan_quote "$ike_psk")"
credentials_config+=$'\n  }\n  xauth-telchi {\n    id = "'
credentials_config+="$VPN_USERNAME"
credentials_config+=$'"\n    secret = '
credentials_config+="$(swan_quote "$xauth_password")"
credentials_config+=$'\n  }\n}\n'

printf '%s' "$connection_config" | sudo -n swanctl --load-conns --file /dev/stdin
printf '%s' "$credentials_config" | sudo -n swanctl --load-creds --file /dev/stdin --noprompt
cleanup

if sudo -n swanctl --initiate --child telchi --timeout 30; then
  printf '%s\n' 'STRONGSWAN_CONNECTED'
  exit 0
fi
printf '%s\n' 'STRONGSWAN_CONNECTION_FAILED'
exit 5
