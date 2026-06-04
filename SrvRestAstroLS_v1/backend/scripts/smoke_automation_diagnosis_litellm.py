"""Smoke test for automation_diagnosis using the real LiteLLM provider.

The backend must already be running with TEAM360_AI_PROVIDER=litellm.
This script only calls HTTP endpoints; it does not start servers, touch DBs,
or read secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


ANSWERS: list[tuple[str, dict[str, Any]]] = [
    ("process_to_automate", {"free_text": "Calificar leads entrantes desde el sitio web de Team360."}),
    ("business_pain", {"free_text": "El equipo comercial pierde tiempo entendiendo casos que no estan listos para automatizacion."}),
    ("systems_involved", {"selected": ["email", "whatsapp", "browser_portal"], "free_text": "Formulario web y seguimiento por WhatsApp."}),
    ("frequency_volume", {"selected": ["daily", "medium_volume"]}),
    ("rules_clarity", {"selected": ["partially_clear"], "free_text": "Hay criterios comerciales claros, pero falta ordenar excepciones."}),
    ("human_dependency", {"selected": ["medium"], "free_text": "Ventas debe revisar oportunidades de alto valor."}),
    ("access_security", {"selected": ["password", "role_permissions"]}),
    ("data_sensitivity", {"selected": ["personal_data"]}),
    ("expected_result", {"free_text": "Lead clasificado, paquete recomendado y proximo paso comercial sugerido."}),
    ("economic_impact", {"selected": ["high"]}),
]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {_truncate(raw_body, 1200)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {_truncate(raw_body, 1200)}") from exc


def run_smoke(base_url: str, timeout: float) -> dict[str, Any]:
    base = base_url.rstrip("/")
    session = _request_json(
        "POST",
        f"{base}/api/automation-diagnosis/session/start",
        {"source_url": "https://team360.live/smoke-litellm", "locale": "es"},
        timeout=timeout,
    )
    session_id = session["id"]

    for step_id, answer in ANSWERS:
        _request_json(
            "POST",
            f"{base}/api/automation-diagnosis/session/{session_id}/answer",
            {"step_id": step_id, "answer": answer},
            timeout=timeout,
        )

    result = _request_json(
        "POST",
        f"{base}/api/automation-diagnosis/session/{session_id}/classify",
        timeout=timeout,
    )
    interpretation = result.get("ai_interpretation") or {}
    return {
        "session_id": session_id,
        "classification": result.get("classification"),
        "score_total": result.get("score_total"),
        "automation_mode": result.get("automation_mode"),
        "provider": interpretation.get("provider"),
        "model": interpretation.get("model"),
        "latency_ms": interpretation.get("latency_ms"),
        "usage": interpretation.get("usage") or {},
    }


def verification_sql(session_id: str | None = None) -> str:
    where_clause = "WHERE ads.public_session_id = '<session_id>'"
    if session_id:
        where_clause = f"WHERE ads.public_session_id = '{session_id}'"
    return f"""SELECT ads.public_session_id, ads.status,
       adl.classification, adl.score_total,
       adl.automation_mode, adl.recommended_package_type,
       ads.updated_at_utc
FROM automation_diagnosis_sessions ads
LEFT JOIN automation_diagnosis_leads adl ON adl.session_id = ads.id
{where_clause}
ORDER BY ads.updated_at_utc DESC
LIMIT 10;"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke automation_diagnosis against a LiteLLM-backed backend.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--print-sql", action="store_true", help="Print the PostgreSQL verification query for this session.")
    args = parser.parse_args()

    try:
        summary = run_smoke(args.backend_url, args.timeout)
    except Exception as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1

    missing = [key for key in ("classification", "score_total", "provider", "model") if summary.get(key) in (None, "")]
    if missing:
        print(f"SMOKE FAILED: missing result fields: {', '.join(missing)}", file=sys.stderr)
        print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.print_sql:
        summary["postgres_verification_sql"] = verification_sql(str(summary.get("session_id") or ""))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
