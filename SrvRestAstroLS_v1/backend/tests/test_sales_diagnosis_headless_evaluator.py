"""Unit tests for the headless Sales Diagnosis evaluator.

No network calls. No DB. No external providers.
"""

from __future__ import annotations

from pathlib import Path

import scripts.evaluate_sales_diagnosis_headless_responses as evaluator


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "sales_diagnosis_headless_questions_v1.json"
)


def _sample_case() -> dict:
    return {
        "id": "speed_simple_001",
        "level": "muy_sencilla",
        "question": "¿Cuánto tiempo toma responder el diagnóstico?",
        "expected_claims": [
            "responde en pocos minutos",
            "menos de 10 minutos",
        ],
        "forbidden_claims": [
            "varias horas",
        ],
        "validates": "Rapidez",
        "optional_risk_flags": ["no_future_guarantees"],
    }


def _base_response_body(response_text: str) -> dict:
    return {
        "session_id": "s1",
        "response_text": response_text,
        "response_type": "final",
        "fallback_applied": False,
        "guardrail_flags": [],
        "retrieved_sources": [],
        "turn_count": 1,
        "events": [],
        "runtime_mode": "product_adapter_skeleton",
    }


def _provider_config(*, real_llm: bool = False, real_retrieval: bool = False) -> dict:
    return {
        "real_llm_expected": real_llm,
        "real_retrieval_expected": real_retrieval,
    }


def test_load_dataset_fixture():
    dataset = evaluator._load_dataset(FIXTURE_PATH)
    assert dataset["test_suite"] == "sales_diagnosis_headless_response_validation_v1"
    assert len(dataset["cases"]) == 25
    assert dataset["cases"][0]["id"] == "speed_simple_001"


def test_expected_claim_matching_is_semantic_enough():
    text = "El diagnóstico responde en pocos minutos y no promete implementación inmediata."
    hits = evaluator._match_expected_claims(text, _sample_case()["expected_claims"])
    assert "responde en pocos minutos" in hits


def test_forbidden_claim_detection_honors_simple_negation():
    text = "No es una garantía absoluta ni algo garantizado."
    hits = evaluator._find_forbidden_hits(text, [])
    assert "garantizado" not in hits


def test_forbidden_claim_detection_honors_adjacent_no_negation():
    text = "El diagnóstico es preliminar y no garantiza viabilidad."
    hits = evaluator._find_forbidden_hits(text, [])
    assert "garantiza" not in hits


def test_forbidden_claim_detection_flags_unnegated_promises():
    text = "Garantizamos la automatización de cualquier proceso."
    hits = evaluator._find_forbidden_hits(text, [])
    assert "garantizamos" in hits or "garantizado" in hits


def test_forbidden_claim_detection_honors_no_tiene_negation():
    text = "Team360 no tiene una integración directa con CRM disponible hoy."
    hits = evaluator._find_forbidden_hits(text, ["crm disponible"])
    assert "crm disponible" not in hits


def test_forbidden_claim_detection_honors_no_se_debe_negation():
    text = "Si el sistema usa MFA, puede quedar bloqueado y no se debe bypassar MFA."
    hits = evaluator._find_forbidden_hits(text, ["bypassar mfa"])
    assert "bypassar mfa" not in hits


def test_forbidden_claim_detection_deduplicates_global_and_case_hits():
    text = "El CRM disponible ya está listo para usar."
    hits = evaluator._find_forbidden_hits(text, ["crm disponible"])
    assert hits.count("crm disponible") == 1


def test_case_scoring_pass_warn_fail_paths():
    provider_config = _provider_config()
    case = _sample_case()
    pass_body = _base_response_body(
        "El diagnóstico responde en pocos minutos. No promete implementación inmediata."
    )
    warn_body = _base_response_body("No puedo garantizarlo, depende del caso.")
    fail_body = _base_response_body("Garantizamos la automatización de cualquier proceso.")

    pass_result = evaluator._evaluate_case(
        case,
        pass_body,
        endpoint="product",
        provider_config=provider_config,
        allow_fallback=False,
    )
    warn_result = evaluator._evaluate_case(
        case,
        warn_body,
        endpoint="product",
        provider_config=provider_config,
        allow_fallback=False,
    )
    fail_result = evaluator._evaluate_case(
        case,
        fail_body,
        endpoint="product",
        provider_config=provider_config,
        allow_fallback=False,
    )

    assert pass_result.status == "PASS"
    assert warn_result.status == "WARN"
    assert fail_result.status == "FAIL"


def test_case_scoring_allows_negated_forbidden_phrase():
    case = _sample_case()
    provider_config = _provider_config()
    body = _base_response_body("No es garantizado; depende del proceso.")
    result = evaluator._evaluate_case(
        case,
        body,
        endpoint="product",
        provider_config=provider_config,
        allow_fallback=False,
    )
    assert result.status in {"PASS", "WARN"}


def test_guardrail_fallback_is_not_provider_fallback():
    case = _sample_case()
    body = _base_response_body(
        "No puedo proporcionar esa información porque excede los límites."
    )
    body["fallback_applied"] = True
    body["guardrail_flags"] = ["fallback_applied"]
    body["events"] = [
        {
            "event_type": "team360.llm.provider_result",
            "payload": {"response_is_fallback": False},
            "safe_to_show": True,
        }
    ]

    result = evaluator._evaluate_case(
        case,
        body,
        endpoint="product",
        provider_config=_provider_config(real_llm=True),
        allow_fallback=False,
    )

    assert result.status == "WARN"
    assert result.fallback_detected is False
    assert result.guardrail_fallback_detected is True
    assert result.provider_result_seen is True


def test_provider_fallback_fails_real_llm_mode():
    case = _sample_case()
    body = _base_response_body("Recibí tu consulta y la estoy revisando.")
    body["events"] = [
        {
            "event_type": "team360.llm.provider_result",
            "payload": {"response_is_fallback": True},
            "safe_to_show": True,
        }
    ]

    result = evaluator._evaluate_case(
        case,
        body,
        endpoint="product",
        provider_config=_provider_config(real_llm=True),
        allow_fallback=False,
    )

    assert result.status == "FAIL"
    assert result.reason == "real LLM provider_result response_is_fallback=true"
    assert result.fallback_detected is True


def test_require_real_llm_requires_provider_result_event():
    case = _sample_case()
    body = _base_response_body("No puedo garantizarlo, depende del caso.")

    result = evaluator._evaluate_case(
        case,
        body,
        endpoint="product",
        provider_config=_provider_config(real_llm=True),
        allow_fallback=False,
        require_real_llm=True,
    )

    assert result.status == "FAIL"
    assert "provider_result event is missing" in result.reason


def test_debug_event_sanitizer_omits_text_and_redacts_secrets():
    event = {
        "event_type": "team360.answer.final_ready",
        "safe_to_show": True,
        "payload": {
            "text": "visible answer",
            "error": "Bearer token-secret and "
            + "postgresql://u:"
            + "p@localhost/db",
        },
    }

    sanitized = evaluator._sanitize_event(event)

    assert sanitized["payload"]["text"] == "<omitted>"
    assert "token-secret" not in sanitized["payload"]["error"]
    assert "Bearer <redacted>" in sanitized["payload"]["error"]
    assert (
        "postgresql://u:" + "<redacted>" + "@localhost/db"
        in sanitized["payload"]["error"]
    )


def test_parser_accepts_diagnostic_flags():
    args = evaluator.build_arg_parser().parse_args(
        [
            "--single-case",
            "speed_simple_001",
            "--print-events",
            "--debug-request",
            "--require-real-llm",
            "--fail-on-fallback",
            "--dump-provider-events",
        ]
    )

    assert args.single_case == "speed_simple_001"
    assert args.print_events is True
    assert args.debug_request is True
    assert args.require_real_llm is True
    assert args.fail_on_fallback is True
    assert args.dump_provider_events is True
