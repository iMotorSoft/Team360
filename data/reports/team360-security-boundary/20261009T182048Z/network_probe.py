"""Probe a dedicated loopback Srv05 listener without external side effects."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import httpx

base_url = sys.argv[1]
token = os.environ["TEAM360_MESSAGING_WEBHOOK_TOKEN"]
results = {}
with httpx.Client(base_url=base_url, timeout=5) as client:
    results["health"] = client.get("/health").status_code
    results["dev_adapter_production"] = client.post(
        "/api/dev/sales-diagnosis-runtime/turn",
        json={
            "session_id": "network_boundary_probe",
            "message": "synthetic",
            "assistant_instance_code": "team360_sales_diagnosis",
            "package_code": "pkg_sales_diagnosis",
            "knowledge_scope_code": "ks_team360_sales_diagnosis",
            "metadata": {},
        },
    ).status_code
    results["bootstrap_anonymous_production"] = client.post(
        "/api/console/bootstrap",
        json={"workspace_id": "synthetic", "user_id": "synthetic"},
    ).status_code
    results["gupshup_missing_credential"] = client.post(
        "/webhooks/messaging/gupshup/whatsapp", json={}
    ).status_code
    valid = client.post(
        "/webhooks/messaging/gupshup/whatsapp",
        json={},
        headers={"x-team360-webhook-token": token},
    )
    results["gupshup_valid_ignored"] = valid.status_code
    results["gupshup_event_type"] = valid.json().get("event_type")
    results["flow_unauthenticated"] = client.get(
        "/api/team360-flow/configuration"
    ).status_code
    results["console_me_unauthenticated"] = client.get("/api/console/me").status_code

expected = {
    "health": 200,
    "dev_adapter_production": 404,
    "bootstrap_anonymous_production": 404,
    "gupshup_missing_credential": 401,
    "gupshup_valid_ignored": 200,
    "gupshup_event_type": "ignored",
    "flow_unauthenticated": 401,
    "console_me_unauthenticated": 401,
}
report = {
    "scope": "Uvicorn loopback, Srv05, production env, lifespan off, synthetic ignored webhook",
    "results": results,
    "expected": expected,
    "status": "PASS" if results == expected else "FAIL",
}
Path(__file__).with_name("network-probe.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
