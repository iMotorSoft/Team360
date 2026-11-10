"""Bounded, fail-closed updater for the accredited Team360 Meta DEV callback."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[6]
LAB = ROOT.parent.parent / "lab/evolution-api"
APP = "1595188049069929"
WABA = "2641368569628887"
PHONE = "1376913155505594"


class Blocked(Exception):
    """Safe diagnostic: never include raw provider responses or request URLs."""


def base_url(value):
    if not re.fullmatch(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com/?", value):
        raise Blocked("URL_INVALID: require an HTTPS Quick Tunnel origin, no path/query/port")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials or a verification token elsewhere.


class Transport:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, url, token=None, data=None, label="HTTP"):
        headers = {"Authorization": "Bearer " + token} if token else {}
        body = urlencode(data).encode() if data is not None else None
        request = Request(url, data=body, headers=headers,
                          method="POST" if body is not None else "GET")
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise Blocked(label + ": RESPONSE_TOO_LARGE")
                return raw.decode("utf-8")
        except HTTPError as exc:
            # Meta error descriptions may echo sensitive parameters. Never print them.
            code = subcode = None
            try:
                error = json.loads(exc.read(262144)).get("error", {})
                code, subcode = error.get("code"), error.get("error_subcode")
            except (ValueError, AttributeError):
                pass
            raise Blocked(f"{label}: HTTP_{exc.code} code={code} subcode={subcode}; "
                          "check existing credentials/permissions; no automatic retry") from None
        except (URLError, TimeoutError, OSError, UnicodeError):
            raise Blocked(label + ": CONNECTIVITY_OR_TLS_FAILURE; no automatic retry") from None


def configuration(env):
    for key, expected in (("APP_ID", APP), ("WABA_ID", WABA), ("PHONE_NUMBER_ID", PHONE)):
        if env.get("META_TEAM360_" + key) != expected:
            raise Blocked("IDENTITY_MISMATCH: accredited Team360 DEV assets required")
    for key in ("APP_SECRET", "VERIFY_TOKEN", "WABA_TOKEN", "GRAPH_VERSION"):
        if not env.get("META_TEAM360_" + key):
            raise Blocked("MISSING_CREDENTIAL: META_TEAM360_" + key)
    version = env["META_TEAM360_GRAPH_VERSION"]
    if not re.fullmatch(r"v[0-9]+\.0", version):
        raise Blocked("GRAPH_VERSION_INVALID")
    if env.get("TEAM360_ENV", "dev") not in ("dev", "development"):
        raise Blocked("ENVIRONMENT_NOT_DEV")
    return "https://graph.facebook.com/" + version


class Updater:
    def __init__(self, env, transport):
        self.graph = configuration(env)
        self.env, self.transport = env, transport
        self.app_token = APP + "|" + env["META_TEAM360_APP_SECRET"]

    def graph_request(self, edge, token, data=None):
        raw = self.transport.request(self.graph + "/" + edge, token, data, "META")
        try:
            result = json.loads(raw)
        except ValueError:
            raise Blocked("META: INVALID_JSON") from None
        if not isinstance(result, dict) or "error" in result:
            raise Blocked("META: INVALID_RESPONSE")
        return result

    def inventory(self):
        app = self.graph_request(APP + "/subscriptions", self.app_token)
        waba = self.graph_request(WABA + "/subscribed_apps", self.env["META_TEAM360_WABA_TOKEN"])
        for result in (app, waba):
            if not isinstance(result.get("data"), list) or result.get("paging", {}).get("next"):
                raise Blocked("INVENTORY_INCOMPLETE: manual review required")
        rows = [row for row in app["data"] if row.get("object") == "whatsapp_business_account"]
        if len(rows) != 1:
            raise Blocked("APP_SUBSCRIPTION_MISSING_OR_AMBIGUOUS: no automatic creation")
        row = rows[0]
        callback = row.get("callback_url", "")
        if not callback.endswith("/webhook/meta"):
            raise Blocked("EXISTING_CALLBACK_NOT_DEV")
        base_url(callback[:-len("/webhook/meta")])
        if row.get("active") is not True or row.get("fields") is None:
            raise Blocked("APP_SUBSCRIPTION_INACTIVE_OR_INVALID")
        if {field.get("name") for field in row["fields"]} != {"messages"}:
            raise Blocked("UNEXPECTED_FIELDS: refusing to remove or add subscriptions")
        own = [r for r in waba["data"] if r.get("whatsapp_business_api_data", {}).get("id") == APP]
        if len(own) != 1:
            raise Blocked("WABA_SUBSCRIPTION_MISSING_OR_AMBIGUOUS: not created by this tool")
        if own[0].get("override_callback_uri") or own[0].get("override_callback_url"):
            raise Blocked("WABA_OVERRIDE_PRESENT: app callback update would not prove routing")
        return row, own[0]

    def challenge(self, origin, label):
        challenge = secrets.token_hex(16)
        query = urlencode({"hub.mode": "subscribe", "hub.verify_token": self.env["META_TEAM360_VERIFY_TOKEN"],
                           "hub.challenge": challenge})
        raw = self.transport.request(origin + "/webhook/meta?" + query, label=label)
        if raw != challenge:
            raise Blocked(label + ": CHALLENGE_MISMATCH")

    def run(self, origin, apply=False):
        before = self.inventory()
        print("MECHANISM=APP_SUBSCRIPTION; WABA_SUBSCRIBED=YES; WABA_OVERRIDE=NONE")
        print("REGISTERED_CALLBACK=" + before[0]["callback_url"])
        print("REQUESTED_CALLBACK=" + origin + "/webhook/meta")
        self.transport.request(origin + "/", label="PUBLIC_ROOT")
        self.challenge("http://127.0.0.1:18180", "LOCAL_CALLBACK")
        self.challenge(origin, "PUBLIC_CALLBACK")
        print("PUBLIC_HTTP=OK; LOCAL_CHALLENGE=PASS; PUBLIC_CHALLENGE=PASS")
        desired = origin + "/webhook/meta"
        if not apply:
            print("DRY_RUN=READY; META_WRITES=0; UPDATE_REQUIRED=" +
                  ("NO" if before[0]["callback_url"] == desired else "YES"))
            print("META_VERIFICATION=NOT_EXECUTED; WHATSAPP_E2E=NOT_TESTED")
            return
        if self.inventory() != before:
            raise Blocked("CONCURRENT_META_CHANGE: nothing written; rerun dry-run")
        changed = before[0]["callback_url"] != desired
        if changed:
            print("APPLY_STARTED: on interruption inspect with --dry-run; no automatic rollback", flush=True)
            result = self.graph_request(APP + "/subscriptions", self.app_token, {
                "object": "whatsapp_business_account", "callback_url": desired,
                "verify_token": self.env["META_TEAM360_VERIFY_TOKEN"], "fields": "messages"})
            if result.get("success") is not True:
                raise Blocked("META_WRITE_NOT_CONFIRMED: inspect with --dry-run before retry")
        after = self.inventory()
        if after[0]["callback_url"] != desired:
            raise Blocked("POST_WRITE_VERIFICATION_FAILED: inspect Meta; no automatic rollback")
        self.challenge(origin, "POST_APPLY_CALLBACK")
        print("REGISTERED_CALLBACK_VERIFIED=YES; APP_ACTIVE=YES; FIELD_MESSAGES=YES; WABA_SUBSCRIBED=YES")
        print("META_WRITE=" + ("SUCCESS" if changed else "NOT_NEEDED"))
        print("META_VERIFICATION=" + ("UPDATE_ACCEPTED_BY_META" if changed else "NOT_REEXECUTED"))
        print("WHATSAPP_E2E=NOT_TESTED; RUNTIME_ACTIVATION=NOT_PERFORMED")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Runbook: SrvRestAstroLS_v1/backend/modules/messaging/providers/evolution/DEV_STARTUP.md",
    )
    parser.add_argument("url", help="current HTTPS Quick Tunnel origin")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="default: GET only, no Meta writes")
    mode.add_argument("--apply", action="store_true", help="explicitly update the DEV app callback")
    args = parser.parse_args(argv)
    try:
        origin = base_url(args.url)
        try:
            current = base_url((LAB / "data/cloudflared.url").read_text().strip())
        except OSError:
            raise Blocked("TUNNEL_STATE_UNAVAILABLE: run cloudflare-status.sh") from None
        if origin != current:
            raise Blocked("TUNNEL_URL_MISMATCH: use data/cloudflared.url; no writes")
        Updater(os.environ, Transport()).run(origin, args.apply)
        return 0
    except Blocked as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # Never expose a traceback containing credentials/URLs from network libraries.
        print("BLOCKED: UNEXPECTED_RESPONSE_OR_ENVIRONMENT; inspect safely, no automatic retry", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
