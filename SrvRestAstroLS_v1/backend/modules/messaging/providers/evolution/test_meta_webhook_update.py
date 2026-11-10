"""Offline tests: no credentials, sockets, Meta writes or service lifecycle."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

SPEC = importlib.util.spec_from_file_location("meta_updater", Path(__file__).with_name("meta_webhook_update.py"))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
ORIGIN = "https://new-dev-tunnel.trycloudflare.com"
OLD = "https://old-dev-tunnel.trycloudflare.com/webhook/meta"
ENV = {"META_TEAM360_APP_ID": m.APP, "META_TEAM360_WABA_ID": m.WABA,
       "META_TEAM360_PHONE_NUMBER_ID": m.PHONE, "META_TEAM360_APP_SECRET": "fake-secret",
       "META_TEAM360_VERIFY_TOKEN": "fake-verify", "META_TEAM360_WABA_TOKEN": "fake-access",
       "META_TEAM360_GRAPH_VERSION": "v26.0"}


class FakeTransport:
    def __init__(self):
        self.row = {"object": "whatsapp_business_account", "callback_url": OLD,
                    "active": True, "fields": [{"name": "messages", "version": "v26.0"}]}
        self.waba = {"whatsapp_business_api_data": {"id": m.APP}}
        self.calls = []
        self.bad_challenge = False
        self.paging = False
        self.ignore_write = False
        self.success = True

    def request(self, url, token=None, data=None, label="HTTP"):
        self.calls.append((url, token, data))
        if data is not None:
            if not self.ignore_write:
                self.row["callback_url"] = data["callback_url"]
            return json.dumps({"success": self.success})
        if url.endswith("/subscriptions"):
            return json.dumps({"data": [self.row], "paging": {"next": "page2"} if self.paging else {}})
        if url.endswith("/subscribed_apps"):
            return json.dumps({"data": [self.waba]})
        if "/webhook/meta?" in url:
            return "incorrect" if self.bad_challenge else parse_qs(urlsplit(url).query)["hub.challenge"][0]
        return "healthy"

    @property
    def writes(self):
        return [c for c in self.calls if c[2] is not None]


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.updater = m.Updater(ENV, self.transport)
        self.output = io.StringIO()
        self.capture = redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def test_dry_run_get_only_no_secret_output(self):
        self.updater.run(ORIGIN)
        self.assertEqual(self.transport.writes, [])
        self.assertIn("DRY_RUN=READY", self.output.getvalue())
        for secret in ("fake-secret", "fake-verify", "fake-access"):
            self.assertNotIn(secret, self.output.getvalue())
        app_get = next(c for c in self.transport.calls if c[0].endswith("/subscriptions"))
        self.assertEqual(app_get[1], m.APP + "|fake-secret")

    def test_apply_and_second_apply_idempotent(self):
        self.updater.run(ORIGIN, apply=True)
        self.assertEqual(len(self.transport.writes), 1)
        url, token, data = self.transport.writes[0]
        self.assertTrue(url.endswith(m.APP + "/subscriptions"))
        self.assertEqual(data, {"object": "whatsapp_business_account", "callback_url": ORIGIN + "/webhook/meta",
                                "verify_token": "fake-verify", "fields": "messages"})
        self.updater.run(ORIGIN, apply=True)
        self.assertEqual(len(self.transport.writes), 1)
        self.assertIn("META_WRITE=NOT_NEEDED", self.output.getvalue())

    def test_bad_urls(self):
        for value in ("http://new.trycloudflare.com", "https://example.com", "https://x.trycloudflare.com.evil.com",
                      "https://x.trycloudflare.com:443", "https://user@x.trycloudflare.com",
                      "https://x.trycloudflare.com/webhook/meta", "https://x.trycloudflare.com?secret=x",
                      "https://x.trycloudflare.com#x", "https://x.trycloudflare.com\n"):
            with self.subTest(value=value), self.assertRaises(m.Blocked):
                m.base_url(value)

    def test_normalize_trailing_slash(self):
        self.assertEqual(m.base_url(ORIGIN + "/"), ORIGIN)

    def test_identity_and_env_fail_closed(self):
        for key in ("APP_ID", "WABA_ID", "PHONE_NUMBER_ID"):
            env = dict(ENV, **{"META_TEAM360_" + key: "other"})
            with self.assertRaises(m.Blocked):
                m.Updater(env, self.transport)
        with self.assertRaises(m.Blocked):
            m.Updater(dict(ENV, TEAM360_ENV="production"), self.transport)
        self.assertFalse(self.transport.calls)

    def test_missing_credentials_no_fallback(self):
        for key in ("APP_SECRET", "VERIFY_TOKEN", "WABA_TOKEN", "GRAPH_VERSION"):
            env = dict(ENV)
            env.pop("META_TEAM360_" + key)
            env["META_VERTICE360_" + key] = "must-not-use"
            with self.assertRaises(m.Blocked):
                m.Updater(env, self.transport)

    def test_override_blocks_writes(self):
        self.transport.waba["override_callback_uri"] = ORIGIN
        with self.assertRaisesRegex(m.Blocked, "WABA_OVERRIDE_PRESENT"):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_other_app_not_subscribed(self):
        self.transport.waba["whatsapp_business_api_data"]["id"] = "other"
        with self.assertRaisesRegex(m.Blocked, "WABA_SUBSCRIPTION_MISSING"):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_production_callback_protected(self):
        self.transport.row["callback_url"] = "https://production.example/webhook/meta"
        with self.assertRaises(m.Blocked):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_inactive_subscription(self):
        self.transport.row["active"] = False
        with self.assertRaises(m.Blocked):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_fields_not_removed(self):
        self.transport.row["fields"].append({"name": "other"})
        with self.assertRaisesRegex(m.Blocked, "UNEXPECTED_FIELDS"):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_incomplete_inventory(self):
        self.transport.paging = True
        with self.assertRaisesRegex(m.Blocked, "INVENTORY_INCOMPLETE"):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_failed_challenge_prevents_write(self):
        self.transport.bad_challenge = True
        with self.assertRaisesRegex(m.Blocked, "CHALLENGE_MISMATCH"):
            self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_readback_mismatch_is_not_success(self):
        self.transport.ignore_write = True
        with self.assertRaisesRegex(m.Blocked, "POST_WRITE_VERIFICATION_FAILED"):
            self.updater.run(ORIGIN, True)
        self.assertEqual(len(self.transport.writes), 1)

    def test_unconfirmed_write_is_not_success(self):
        self.transport.success = False
        with self.assertRaisesRegex(m.Blocked, "META_WRITE_NOT_CONFIRMED"):
            self.updater.run(ORIGIN, True)
        self.assertEqual(len(self.transport.writes), 1)

    def test_concurrent_update_blocks_write(self):
        before = self.updater.inventory()
        changed = copy.deepcopy(before)
        changed[0]["callback_url"] = ORIGIN + "/webhook/meta"
        with patch.object(self.updater, "inventory", side_effect=[before, changed]):
            with self.assertRaisesRegex(m.Blocked, "CONCURRENT_META_CHANGE"):
                self.updater.run(ORIGIN, True)
        self.assertFalse(self.transport.writes)

    def test_redirect_rejected(self):
        self.assertIsNone(m.NoRedirect().redirect_request(Request(ORIGIN), None, 302, "redirect", {}, "https://evil.com"))

    def test_main_url_mismatch_never_constructs_transport(self):
        with patch.object(Path, "read_text", return_value=ORIGIN), patch.object(m, "Transport") as transport:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(m.main(["https://other.trycloudflare.com", "--apply"]), 2)
            transport.assert_not_called()

    def test_main_default_is_dry_run(self):
        with patch.object(Path, "read_text", return_value=ORIGIN), patch.object(m, "Updater") as updater:
            self.assertEqual(m.main([ORIGIN]), 0)
            updater.return_value.run.assert_called_once_with(ORIGIN, False)


if __name__ == "__main__":
    unittest.main()
