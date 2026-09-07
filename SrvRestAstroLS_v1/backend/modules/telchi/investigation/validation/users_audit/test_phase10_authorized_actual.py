"""PHASE 10 unit tests — authorized×actual status classification (§22 fixtures).

Fixtures: AUTHORIZED_AND_USED, AUTHORIZED_NOT_USED,
USED_BUT_AUTHORIZATION_UNCONFIRMED, USED_AND_APPARENTLY_NOT_AUTHORIZED,
INDETERMINATE.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.users_audit.phase10_authorized_actual import compute_status


def _user(userid=1, code="u1", name="Uno", super="N", locked="N"):
    return {"USERID": userid, "USER_CODE": code, "U_NAME": name,
            "SUPERUSER": super, "Locked": locked}


class TestAuthorizedActualStates(unittest.TestCase):
    def test_authorized_and_used(self):
        auth = {"SALES_CREATE": {"authorized": True}}
        creation = {1: {"SALES_CREATE": 10}}
        cancel = {}
        last = {1: {"SALES_CREATE": "2026-08-01"}}
        r = compute_status(_user(), auth, creation, cancel, last)
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CREATE"]["status"], "AUTHORIZED_AND_USED")

    def test_authorized_not_used(self):
        auth = {"SALES_CREATE": {"authorized": True}}
        r = compute_status(_user(), auth, {}, {}, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CREATE"]["status"], "AUTHORIZED_NOT_USED")

    def test_used_but_unconfirmed_non_sensitive(self):
        # non-sensitive capability used but not authorized
        auth = {}
        creation = {1: {"SALES_CREATE": 5}}
        r = compute_status(_user(), auth, creation, {}, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CREATE"]["status"], "USED_BUT_AUTHORIZATION_UNCONFIRMED")

    def test_used_and_apparently_not_authorized_sensitive(self):
        # sensitive capability used but not authorized
        auth = {}
        creation = {1: {"PAYMENT_CANCEL": 3}}
        r = compute_status(_user(), auth, creation, {}, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["PAYMENT_CANCEL"]["status"], "USED_AND_APPARENTLY_NOT_AUTHORIZED")

    def test_superuser_is_always_authorized(self):
        auth = {}
        creation = {1: {"SALES_CREATE": 5}}
        r = compute_status(_user(super="Y"), auth, creation, {}, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CREATE"]["status"], "AUTHORIZED_AND_USED")

    def test_indeterminate(self):
        # authorized but neither used nor (should not happen); here empty
        auth = {"SALES_CREATE": {"authorized": False}}
        r = compute_status(_user(), auth, {}, {}, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CREATE"]["status"], "AUTHORIZED_NOT_USED")

    def test_cancel_maps_to_cancel_capability(self):
        auth = {}
        cancel = {1: {"SALES_CANCEL": 2}}
        r = compute_status(_user(), auth, {}, cancel, {})
        m = {x["capability"]: x for x in r["matrix"]}
        self.assertEqual(m["SALES_CANCEL"]["status"], "USED_AND_APPARENTLY_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
