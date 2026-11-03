"""Read-only active LiteLLM audit; output whitelist excludes keys/full bodies."""
import json
from pathlib import Path
import sys
import httpx
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "SrvRestAstroLS_v1/backend"))
from modules.automation_diagnosis.litellm_client import LiteLLMClient
client = LiteLLMClient(base_url="http://127.0.0.1:4000")
fields = ("fallbacks", "default_fallbacks", "context_window_fallbacks", "content_policy_fallbacks")
report = {"mode": "read-only authenticated GET; no upstream failure injection or routing change"}
with httpx.Client(timeout=10) as http:
    for endpoint in ("/model/info", "/router/settings"):
        response = http.get("http://127.0.0.1:4000" + endpoint, headers={"Authorization": "Bearer " + client.api_key})
        assert response.status_code == 200
        payload = response.json()
        if endpoint == "/model/info":
            report[endpoint] = {"status": 200, "models": [{"alias": m.get("model_name"), "upstream": (m.get("litellm_params") or {}).get("model")} for m in payload.get("data", []) if m.get("model_name") in {"openai_gpt-5.4-nano", "openai_text_embedding_3_small"}]}
        else:
            settings = payload.get("current_values", {})
            report[endpoint] = {"status": 200, "routing_strategy": settings.get("routing_strategy"), "fallbacks": {key: {"present": key in settings, "nonempty": bool(settings.get(key))} for key in fields}, "model_group_alias_nonempty": bool(settings.get("model_group_alias")), "default_params_fallback_nonempty": bool((settings.get("default_litellm_params") or {}).get("fallbacks"))}
Path(__file__).with_name("litellm-audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
