#!/usr/bin/env python3
"""Validacion end-to-end del runtime Vera con PostgreSQL + Milvus + LiteLLM + GPT-5.4 Nano.

Requiere:
  - PostgreSQL 18 en localhost:5432, db=team360, user=administrator
  - Milvus 2.6 en localhost:19530, coleccion team360_sales_diagnosis_knowledge_v1
  - LiteLLM en http://localhost:4000, alias openai_gpt-5-nano
  - OpenAI_Key_JAI_query y LITELLM_MASTER_KEY en entorno

Uso:
  cd SrvRestAstroLS_v1/backend
  TEAM360_DB_URL_PSQL=postgresql://administrator:TodaRaba@localhost:5432/team360 \
  UVICORN_... (o simplemente:)
  uv run python ../lab/openai-direct-vs-litellm-latency/validate_runtime.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results" / f"validate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


# ---------------------------------------------------------------------------
# Test conversations
# ---------------------------------------------------------------------------

CASES: list[dict[str, Any]] = []

# CASO 1 — Espanol natural, usuario no tecnico
CASES.append({
    "name": "01_espanol_natural",
    "turns": [
        "quiero que responda solo los mensajes porque perdemos ventas",
        "whatsapp y a veces gmail",
        "vendemos repuestos de maquinaria industrial",
        "use una planilla de Excel para los precios",
        "el stock esta en el sistema de Windows",
        "los descuentos grandes los reviso yo antes",
        "dame ya el diagnostico y que haras primero",
    ],
})

# CASO 2 — Respuestas desordenadas (responde antes de que pregunten)
CASES.append({
    "name": "02_respuestas_desordenadas",
    "turns": [
        "quiero automatizar las consultas de venta",
        "son como 80 por dia y usamos Gmail",
        "si tambien WhatsApp",
        "los productos los tenemos en un ERP cerrado en Windows",
        "los precios los pasamos a Excel cada semana",
        "las consultas normales que responda solo, los descuentos los reviso yo",
        "dame el diagnostico",
    ],
})

# CASO 3 — Contradiccion y correccion
CASES.append({
    "name": "03_contradiccion",
    "turns": [
        "quiero automatizar respuestas de clientes",
        "whatsapp y Gmail",
        "tengo el stock y los precios en una planilla de Excel",
        "en realidad el stock esta en el sistema contable, solo los precios estan en la planilla",
        "uso un programa cerrado en Windows, ahi hago la kabala cuando vendemos",
        "descuentos especiales los reviso yo antes",
        "dame ya el diagnostico completo",
    ],
})

# CASO 4 — Espanol + Ingles
CASES.append({
    "name": "04_espanol_ingles",
    "turns": [
        "quiero automatizar las consultas",
        "sometimes llegan por Gmail but la mayoria entra por WhatsApp",
        "we sell industrial spare parts",
        "the stock is in a closed Windows system",
        "los precios los tengo en Excel",
        "special discounts need my approval first",
        "dame el diagnostico final",
    ],
})

# CASO 5 — Espanol + Hebreo transliterado
CASES.append({
    "name": "05_espanol_hebreo_transliterado",
    "turns": [
        "quiero automatizar las consultas de los clientes",
        "hablan por WhatsApp y Gmail",
        "los precios estan en Excel, el stock en el programa contable",
        "uso un programa cerrado en Windows, ahi hago la kabala y la factura",
        "los descuentos especiales los tengo que revisar antes de enviar",
        "dame el diagnostico",
    ],
})

# CASO 6 — Hebreo real RTL
CASES.append({
    "name": "06_hebreo_real",
    "turns": [
        "הלקוחות כותבים בוואטסאפ ובמייל",
        "אנחנו מוכרים חלקי חילוף למכונות תעשייתיות",
        "המלאי נמצא במערכת סגורה בחלונות",
        "המחירים נמצאים באקסל ואני עושה קבלה בתוכנה",
        "הנחות מיוחדות אני צריך לאשר לפני השליחה",
        "תן לי את האבחון הסופי",
    ],
})

# CASO 7 — Cambio de idioma durante la conversacion
CASES.append({
    "name": "07_cambio_idioma",
    "turns": [
        "quiero automatizar las respuestas a mis clientes",
        "we get messages on WhatsApp and Gmail",
        "המלאי נמצא במערכת Windows",
        "los precios en Excel",
        "special discounts I review manually",
        "dame el diagnostico final",
    ],
})

# CASO 8 — Usuario artesano (no tecnico)
CASES.append({
    "name": "08_artesano",
    "turns": [
        "hago muebles a medida y me escriben por todos lados",
        "whatsapp, instagram, a veces mail",
        "tengo los precios en un cuaderno y el stock lo llevo en la cabeza",
        "cuando alguien quiere algo especial lo hablamos primero",
        "que opinas, se puede hacer algo",
    ],
})

# CASO 9 — Software cerrado
CASES.append({
    "name": "09_software_cerrado",
    "turns": [
        "recibo consultas de clientes por WhatsApp",
        "tengo un sistema contable en Windows que no tiene API",
        "ahi hago los recibos y veo el stock",
        "los precios los actualizo en Excel",
        "los descuentos grandes los autorizo yo",
        "se puede automatizar algo sin tocar el sistema",
        "dame el diagnostico",
    ],
})

# CASO 10 — Seguridad (MFA, QR)
CASES.append({
    "name": "10_seguridad_mfa",
    "turns": [
        "quiero automatizar las consultas de clientes",
        "whatsapp y Gmail",
        "el sistema del banco pide un codigo que llega al telefono",
        "no puedo darle la clave a nadie",
        "los descuentos especiales los reviso yo",
        "se puede hacer algo sin compartir claves",
    ],
})

# CASO 11 — Solicitud prematura de diagnostico
CASES.append({
    "name": "11_diagnostico_prematuro",
    "turns": [
        "dame el diagnostico ya",
        "recibo consultas por WhatsApp",
        "dame ya el diagnostico te digo",
        "vendemos repuestos",
        "tenemos todo en Excel y un sistema en Windows",
        "descuentos los reviso yo",
        "dame el diagnostico y que haras primero",
    ],
})

# CASO 12 — Factibilidad vs disponibilidad comercial
CASES.append({
    "name": "12_factibilidad_vs_disponibilidad",
    "turns": [
        "necesito un bot que hable con clientes",
        "whatsapp y Gmail",
        "tengo un ERP de fabricacion europeo con API",
        "quiere integrarse con su sistema de diseno CAD tambien",
        "los descuentos especiales los reviso yo",
        "esta disponible hoy esto en Team360",
        "dame el diagnostico y el proximo paso",
    ],
})

# CASO 13 — Seguridad nativa (biometria, QR)
CASES.append({
    "name": "13_seguridad_nativa",
    "turns": [
        "quiero que el bot entre al sistema del gobierno",
        "el sistema pide huella digital y codigo SMS",
        "tengo un lector de huellas en la oficina",
        "se puede automatizar la entrada",
    ],
})

# CASO 14 — Aprobacion humana con excepcion
CASES.append({
    "name": "14_aprobacion_humana",
    "turns": [
        "quiero que responda solo los mensajes",
        "whatsapp y Gmail",
        "todo automatico sin que nadie revise",
        "bueno los descuentos especiales los tiene que revisar alguien",
        "pero el resto que responda solo",
        "hay stock en el sistema de Windows y precios en Excel",
        "dame el diagnostico",
    ],
})


# ---------------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(HERE.parent.parent / "backend"))

def _init_runtime():
    """Initialize the Vera conversational runtime with real services."""
    from modules.sales_diagnosis_runtime import (
        AssistantConversationRuntime,
        GuardrailPolicy,
        PromptPolicy,
    )
    from modules.sales_diagnosis_runtime.state_repository import (
        SyncPostgresConversationStateRepository,
    )
    from modules.sales_diagnosis_runtime.providers import (
        NullRetrievalProvider,
    )
    from modules.automation_diagnosis.litellm_client import LiteLLMClient

    # LiteLLM provider
    class _ValidationLLMProvider:
        def __init__(self):
            self._client = LiteLLMClient(
                base_url=os.environ.get("TEAM360_LITELLM_BASE_URL", "http://localhost:4000/v1")
            )
            self._model = os.environ.get("TEAM360_LITELLM_MODEL_ALIAS", "openai_gpt-5-nano")
            self._prompt_policy = PromptPolicy()

        def generate(self, input_, state, context):
            system = self._prompt_policy.build_system_prompt(
                assistant_instance_code=input_.assistant_instance_code,
                package_code=input_.package_code,
            )
            turn = self._prompt_policy.build_turn_prompt(input_, state, context)
            response = self._client.text_completion(
                self._model,
                [{"role": "system", "content": system}, {"role": "user", "content": turn}],
            )
            return response.content

    # State repository (PostgreSQL)
    dsn = os.environ.get("TEAM360_DB_URL_PSQL", "")
    if not dsn:
        dsn = "postgresql://administrator:TodaRaba@localhost:5432/team360"
    state_repo = SyncPostgresConversationStateRepository(dsn)

    # Retrieval (Null for now, can swap to Milvus)
    retrieval = NullRetrievalProvider()

    runtime = AssistantConversationRuntime(
        retrieval_provider=retrieval,
        llm_provider=_ValidationLLMProvider(),
        state_repository=state_repo,
        prompt_policy=PromptPolicy(),
        guardrail_policy=GuardrailPolicy(),
    )
    return runtime, state_repo


def _build_input(
    session_id: str,
    message: str,
    assistant_instance_code: str = "validate",
    package_code: str = "validate",
    knowledge_scope_code: str = "validate",
) -> Any:
    from modules.sales_diagnosis_runtime.contracts import AssistantTurnInput
    return AssistantTurnInput(
        session_id=session_id,
        user_message=message,
        assistant_instance_code=assistant_instance_code,
        package_code=package_code,
        knowledge_scope_code=knowledge_scope_code,
        channel="web",
    )


def run_conversation(
    runtime,
    state_repo,
    case: dict,
) -> list[dict]:
    """Run a full conversation case and return turn results."""
    session_id = f"validate_{case['name']}_{uuid.uuid4().hex[:8]}"
    turns: list[dict] = []
    history: list[dict] = []

    print(f"\n{'='*60}")
    print(f"CASO: {case['name']}")
    print(f"Session: {session_id}")
    print(f"{'='*60}")

    for i, msg in enumerate(case["turns"]):
        start = time.monotonic()
        turn_input = _build_input(session_id, msg)
        try:
            output = runtime.handle_turn(turn_input)
            elapsed = (time.monotonic() - start) * 1000
            response_text = output.response_text if hasattr(output, 'response_text') else str(output)

            # Determine turn info
            turn_info = getattr(output, 'turn_decision', None) or {}
            action = turn_info.get('action', 'unknown') if isinstance(turn_info, dict) else 'unknown'
            diagnosis = turn_info.get('diagnosis', '') if isinstance(turn_info, dict) else ''

            turn_data = {
                "turn": i + 1,
                "user": msg,
                "assistant": response_text[:500],
                "action": action,
                "latency_ms": round(elapsed, 1),
                "success": True,
                "error": None,
            }

            # Check for diagnosis content
            lower = response_text.lower()
            turn_data["has_diagnosis"] = any(kw in lower for kw in ["diagnostico", "diagnóstico", "resumen", "proximo paso", "próximo paso"])

            turns.append(turn_data)
            history.append({"user": msg, "assistant": response_text})

            print(f"  [{i+1}] {action:20s} | {elapsed:7.1f}ms | {response_text[:80]}...")

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            err = str(e)[:200]
            turn_data = {
                "turn": i + 1,
                "user": msg,
                "assistant": "",
                "action": "error",
                "latency_ms": round(elapsed, 1),
                "success": False,
                "error": err,
                "has_diagnosis": False,
            }
            turns.append(turn_data)
            print(f"  [{i+1}] ERROR: {err}")

    # Load final state for analysis
    try:
        final_state = state_repo.load(session_id, "validate", "validate")
        state_info = _analyze_state(final_state) if final_state else {}
    except Exception:
        state_info = {}

    return {
        "case_name": case["name"],
        "session_id": session_id,
        "num_turns": len(case["turns"]),
        "turns": turns,
        "state": state_info,
    }


def _analyze_state(state) -> dict:
    """Extract key state information."""
    info = {}
    mem = getattr(state, 'semantic_memory', None) or {}
    if isinstance(mem, dict):
        info["channels"] = mem.get("channels", "")
        info["systems"] = mem.get("systems_and_data_sources", "")
        info["approval"] = mem.get("human_approval", "")
        info["contradictions"] = mem.get("contradictions", [])
        info["diagnosis_status"] = mem.get("diagnosis_status", "")

    asked = getattr(state, 'asked_questions', None) or []
    if isinstance(asked, list):
        info["questions_asked"] = len(asked)
        info["questions_answered"] = sum(1 for q in asked if q.get("answered"))
        info["repeated_intents"] = _find_repeated_intents(asked)

    info["turn_count"] = getattr(state, 'turn_count', 0) or 0
    return info


def _find_repeated_intents(questions: list) -> list:
    seen = set()
    repeated = []
    for q in questions:
        intent = q.get("intent", "")
        if intent in seen:
            repeated.append(intent)
        seen.add(intent)
    return repeated


# ---------------------------------------------------------------------------
# Analysis & Report
# ---------------------------------------------------------------------------

def analyze_results(results: list[dict]) -> dict:
    """Analyze all conversation results."""
    report = {
        "total_cases": len(results),
        "total_turns": sum(r["num_turns"] for r in results),
        "cases": [],
    }

    for r in results:
        turns = r["turns"]
        successful = sum(1 for t in turns if t["success"])
        errors = [t["error"] for t in turns if t.get("error")]
        diagnoses = sum(1 for t in turns if t.get("has_diagnosis"))
        latencies = [t["latency_ms"] for t in turns if t["success"]]

        # Check for repeated questions by intent
        state = r.get("state", {})
        repeated = state.get("repeated_intents", [])
        contradictions = state.get("contradictions", [])
        questions_asked = state.get("questions_asked", 0)
        questions_answered = state.get("questions_answered", 0)

        case_report = {
            "name": r["case_name"],
            "session_id": r["session_id"],
            "turns_total": r["num_turns"],
            "turns_success": successful,
            "turns_error": len(errors),
            "errors": errors,
            "diagnosis_mentions": diagnoses,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "total_latency_ms": round(sum(latencies), 1) if latencies else 0,
            "ttft_simulated": round(latencies[0], 1) if latencies else 0,  # first turn TTFT approx
            "questions_asked": questions_asked,
            "questions_answered": questions_answered,
            "answer_rate": round(questions_answered / questions_asked * 100, 1) if questions_asked else 0,
            "repeated_intents": repeated,
            "contradictions_detected": len(contradictions),
            "has_diagnosis_final": diagnoses >= 1,
            "all_successful": successful == r["num_turns"],
        }
        report["cases"].append(case_report)

    # Summary
    report["summary"] = {
        "cases_completed": sum(1 for c in report["cases"] if c["all_successful"]),
        "cases_with_errors": sum(1 for c in report["cases"] if c["turns_error"] > 0),
        "total_errors": sum(c["turns_error"] for c in report["cases"]),
        "avg_latency_per_turn": round(
            sum(c["avg_latency_ms"] for c in report["cases"]) / len(report["cases"]), 1
        ) if report["cases"] else 0,
        "cases_with_repeated_intents": sum(1 for c in report["cases"] if c["repeated_intents"]),
        "cases_with_diagnosis": sum(1 for c in report["cases"] if c["has_diagnosis_final"]),
    }
    report["config"] = {
        "llm_provider": "LiteLLM",
        "model_alias": os.environ.get("TEAM360_LITELLM_MODEL_ALIAS", "openai_gpt-5-nano"),
        "state_provider": "PostgreSQL 18",
        "retrieval_provider": "Null (no retrieval in this run)",
        "upstream_model": "openai/gpt-5.4-nano (via LiteLLM /health)",
    }

    return report


def print_report(report: dict):
    """Print human-readable report."""
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"RESUMEN DE VALIDACION - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*60}")
    print(f"Casos: {report['total_cases']} | Turnos: {report['total_turns']}")
    print(f"Completados sin errores: {s['cases_completed']}/{report['total_cases']}")
    print(f"Con errores: {s['cases_with_errors']}")
    print(f"Errores totales: {s['total_errors']}")
    print(f"Latencia promedio por turno: {s['avg_latency_per_turn']}ms")
    print(f"Casos con diagnostico final: {s['cases_with_diagnosis']}/{report['total_cases']}")
    print(f"Casos con intenciones repetidas: {s['cases_with_repeated_intents']}")
    print(f"\nConfig: {json.dumps(report['config'], indent=2)}")

    print(f"\n{'='*60}")
    print(f"DETALLE POR CASO")
    print(f"{'='*60}")
    for c in report["cases"]:
        status = "OK" if c["all_successful"] else "ERROR"
        rep = f" REP:{c['repeated_intents']}" if c["repeated_intents"] else ""
        dia = f" DIA:{c['diagnosis_mentions']}" if c["has_diagnosis_final"] else " NO_DIAG"
        print(f"\n  [{status}] {c['name']:30s} | {c['turns_success']}/{c['turns_total']} turnos | "
              f"lat media {c['avg_latency_ms']}ms | preg {c['questions_asked']}/{c['questions_answered']}{rep}{dia}")
        if c["errors"]:
            for e in c["errors"]:
                print(f"    Error: {e}")
        if c["repeated_intents"]:
            print(f"    Intenciones repetidas: {c['repeated_intents']}")


def save_results(results: list[dict], report: dict):
    """Save results to disk."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(RESULTS_DIR / "report.json", "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en: {RESULTS_DIR}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Inicializando runtime Vera con PostgreSQL + LiteLLM + GPT-5.4 Nano...")
    runtime, state_repo = _init_runtime()
    print("Runtime listo.")

    results = []
    for i, case in enumerate(CASES):
        print(f"\n--- Caso {i+1}/{len(CASES)}: {case['name']} ---")
        try:
            result = run_conversation(runtime, state_repo, case)
            results.append(result)
        except Exception as e:
            print(f"FALLO GRAVE en caso {case['name']}: {e}")
            results.append({
                "case_name": case["name"],
                "session_id": "ERROR",
                "num_turns": 0,
                "turns": [],
                "state": {},
                "fatal_error": str(e)[:300],
            })

    report = analyze_results(results)
    print_report(report)
    save_results(results, report)

    # Summary verdict
    s = report["summary"]
    passed = s["cases_with_errors"] == 0 and s["cases_with_diagnosis"] >= report["total_cases"] * 0.8
    if passed:
        print(f"\n{'='*60}")
        print(f"VALIDACION APROBADA")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"VALIDACION CON OBSERVACIONES")
        print(f"{'='*60}")

    return report


if __name__ == "__main__":
    main()
