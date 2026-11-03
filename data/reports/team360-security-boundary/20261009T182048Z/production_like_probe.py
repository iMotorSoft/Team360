"""Production-like boundary probe: synthetic, no lifespan, DB, provider or delivery."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "SrvRestAstroLS_v1/backend"
sys.path.insert(0, str(BACKEND))

os.environ.update(
    TEAM360_ENV="production",
    TEAM360_FLOW_ACCESS_MODE="authenticated",
    AUTOMATION_DIAGNOSIS_REPOSITORY="memory",
    TEAM360_AI_PROVIDER="mock",
    TEAM360_PASETO_ENABLED="true",
)
os.environ.pop("TEAM360_MESSAGING_WEBHOOK_TOKEN", None)

import httpx
import ls_iMotorSoft_Srv05 as srv

DEV_PAYLOAD = {
    "session_id": "security_boundary_probe",
    "message": "synthetic boundary probe",
    "assistant_instance_code": "team360_sales_diagnosis",
    "package_code": "pkg_sales_diagnosis",
    "knowledge_scope_code": "ks_team360_sales_diagnosis",
    "metadata": {"channel": "probe"},
}
TOKEN = "synthetic-gupshup-boundary-token-0000000000"


async def main() -> None:
    transport = httpx.ASGITransport(app=srv.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://boundary") as client:
        results = {}
        response = await client.post("/api/dev/sales-diagnosis-runtime/turn", json=DEV_PAYLOAD)
        results["dev_adapter_production"] = response.status_code

        response = await client.post(
            "/api/console/bootstrap",
            json={"workspace_id": "synthetic-workspace", "user_id": "synthetic-user"},
        )
        results["bootstrap_anonymous_production"] = response.status_code

        response = await client.post("/webhooks/messaging/gupshup/whatsapp", json={})
        results["gupshup_missing_auth_config"] = response.status_code

        os.environ["TEAM360_MESSAGING_WEBHOOK_TOKEN"] = TOKEN
        response = await client.post(
            "/webhooks/messaging/gupshup/whatsapp",
            json={},
            headers={"x-team360-webhook-token": "invalid"},
        )
        results["gupshup_invalid_credential"] = response.status_code
        response = await client.post(
            "/webhooks/messaging/gupshup/whatsapp",
            json={},
            headers={"x-team360-webhook-token": TOKEN},
        )
        results["gupshup_valid_ignored_event"] = response.status_code
        results["gupshup_valid_event_type"] = response.json().get("event_type")

        results["flow_unauthenticated"] = (
            await client.get("/api/team360-flow/configuration")
        ).status_code
        results["console_me_unauthenticated"] = (
            await client.get("/api/console/me")
        ).status_code
        results["health"] = (await client.get("/health")).status_code

        schema = (await client.get("/schema/openapi.json")).json()
        operations = sorted(
            (method.upper(), path)
            for path, item in schema["paths"].items()
            for method in item
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        )
        results["openapi_operations"] = len(operations)
        results["dev_route_still_documented"] = (
            "POST", "/api/dev/sales-diagnosis-runtime/turn"
        ) in operations

    expected = {
        "dev_adapter_production": 404,
        "bootstrap_anonymous_production": 404,
        "gupshup_missing_auth_config": 503,
        "gupshup_invalid_credential": 401,
        "gupshup_valid_ignored_event": 200,
        "gupshup_valid_event_type": "ignored",
        "flow_unauthenticated": 401,
        "console_me_unauthenticated": 401,
        "health": 200,
        "openapi_operations": 28,
        "dev_route_still_documented": True,
    }
    report = {
        "environment": "production",
        "scope": "ASGI without lifespan; synthetic token and ignored event; no DB/provider/delivery I/O",
        "results": results,
        "expected": expected,
        "status": "PASS" if results == expected else "FAIL",
    }
    output = Path(__file__).with_name("production-like-probe.json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


asyncio.run(main())
