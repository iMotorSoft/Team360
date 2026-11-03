"""Production-env boundary probes with official synthetic fixtures; no DB/keys/users.
No lifespan, real delivery, providers or production runtime are used.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "SrvRestAstroLS_v1/backend"
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
os.environ.update(TEAM360_ENV="production", AUTOMATION_DIAGNOSIS_REPOSITORY="memory", TEAM360_AI_PROVIDER="mock", TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER="fake", TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER="fake", TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY="inmemory")
from modules.security.paseto_tokens import PasetoKeyPair
from test_console_bootstrap_service import _service
from routes import console_bootstrap
import ls_iMotorSoft_Srv05 as srv
import httpx

class FixturePool:
    @asynccontextmanager
    async def connection(self):
        yield object()

async def main():
    pair = PasetoKeyPair.generate("readiness-exposure-fixture")
    key_env = {"TEAM360_PASETO_ENABLED": "true", "TEAM360_PASETO_KEY_ID": pair.key_id,
               "TEAM360_PASETO_PRIVATE_KEY_B64": base64.b64encode(pair.private_pem.encode()).decode(),
               "TEAM360_PASETO_PUBLIC_KEY_B64": base64.b64encode(pair.public_pem.encode()).decode()}
    report = {"environment": "production", "scope": "official synthetic repositories and fresh keys; no real identity/tenant, no lifespan", "surfaces": {}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=srv.app), base_url="http://fixture") as client:
        with patch.dict(os.environ, key_env), patch.object(console_bootstrap, "get_pool", lambda: FixturePool()), patch.object(console_bootstrap, "_SERVICE", _service(permissions=["package.view"], features=["events.basic"])):
            response = await client.post("/api/console/bootstrap", json={"workspace_id": "workspace-1", "user_id": "user-1"})
            assert response.status_code == 201
            token = response.json()["access_token"]
            assert token.startswith("v4.public.")
            me = await client.get("/api/console/me", headers={"Authorization": "Bearer " + token})
            missing = await client.get("/api/console/me")
            assert me.status_code == 200 and missing.status_code == 401
            report["surfaces"]["console_bootstrap"] = {"unauthenticated_status": response.status_code, "ephemeral_valid_token_issued": True, "me_with_issued_token": me.status_code, "me_without_token": missing.status_code, "classification": "EXPOSURE_RISK", "blocking": True, "condition": "If enabled and reachable without authenticated upstream boundary, caller-supplied identity can mint a token. No upstream boundary is established by this app."}
        dev = await client.post("/api/dev/sales-diagnosis-runtime/turn", json={"session_id": "readiness_exposure_fixture", "message": "Sonda sintética sin acciones externas."})
        assert dev.status_code == 201
        report["surfaces"]["diagnosis_dev"] = {"production_env_status": dev.status_code, "classification": "EXPOSURE_RISK", "blocking": True, "condition": "DEV naming is not an environment/identity guard; actual production-env Srv05 mounts and executes fake adapter."}
        ignored = await client.post("/webhooks/messaging/gupshup/whatsapp", json={})
        assert ignored.status_code == 200
        report["surfaces"]["gupshup"] = {"unsigned_empty_status": ignored.status_code, "classification": "EXPOSURE_RISK", "condition": "Source has no signature/env gate before inbound claim and Flow bridge. No inbound mutation was attempted."}
        report["surfaces"]["flow"] = {"classification": "AUTH_GUARDED", "evidence": "Full Gate hardening tests: non-DEV default_admin rejected; authenticated default"}
        report["surfaces"]["embed"] = {"classification": "AUTH_GUARDED", "evidence": "HMAC/origin deny, tamper, override tests; real browser HMAC passes"}
        report["surfaces"]["evolution"] = {"classification": "DEV_GUARDED", "evidence": "Disabled consumer 503; real transport NOT_REQUIRED"}
        report["surfaces"]["debug_schema_health"] = {"classification": "CONDITIONAL", "evidence": "debug default off; OpenAPI and health mounted; ingress policy must be explicit"}
    Path(__file__).with_name("surface-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

asyncio.run(main())
