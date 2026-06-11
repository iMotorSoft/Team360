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


def test_load_dataset_fixture():
    dataset = evaluator._load_dataset(FIXTURE_PATH)
    assert dataset["test_suite"] == "sales_diagnosis_headless_response_validation_v1"
    assert len(dataset["cases"]) == 10
    assert dataset["cases"][0]["id"] == "speed_simple_001"


def test_expected_claim_matching_is_semantic_enough():
    text = "El diagnóstico responde en pocos minutos y no promete implementación inmediata."
    hits = evaluator._match_expected_claims(text, _sample_case()["expected_claims"])
    assert "responde en pocos minutos" in hits


def test_forbidden_claim_detection_honors_simple_negation():
    text = "No es una garantía absoluta ni algo garantizado."
    hits = evaluator._find_forbidden_hits(text, [])
    assert "garantizado" not in hits


def test_forbidden_claim_detection_flags_unnegated_promises():
    text = "Garantizamos la automatización de cualquier proceso."
    hits = evaluator._find_forbidden_hits(text, [])
    assert "garantizamos" in hits or "garantizado" in hits


def test_case_scoring_pass_warn_fail_paths():
    provider_config = {
        "real_llm_expected": False,
        "real_retrieval_expected": False,
    }
    case = _sample_case()
    pass_body = {
        "session_id": "s1",
        "response_text": "El diagnóstico responde en pocos minutos. No promete implementación inmediata.",
        "response_type": "final",
        "fallback_applied": False,
        "guardrail_flags": [],
        "retrieved_sources": [],
        "turn_count": 1,
        "events": [],
        "runtime_mode": "product_adapter_skeleton",
    }
    warn_body = {
        "session_id": "s1",
        "response_text": "No puedo garantizarlo, depende del caso.",
        "response_type": "final",
        "fallback_applied": False,
        "guardrail_flags": [],
        "retrieved_sources": [],
        "turn_count": 1,
        "events": [],
        "runtime_mode": "product_adapter_skeleton",
    }
    fail_body = {
        "session_id": "s1",
        "response_text": "Garantizamos la automatización de cualquier proceso.",
        "response_type": "final",
        "fallback_applied": False,
        "guardrail_flags": [],
        "retrieved_sources": [],
        "turn_count": 1,
        "events": [],
        "runtime_mode": "product_adapter_skeleton",
    }

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
    provider_config = {
        "real_llm_expected": False,
        "real_retrieval_expected": False,
    }
    body = {
        "session_id": "s1",
        "response_text": "No es garantizado; depende del proceso.",
        "response_type": "final",
        "fallback_applied": False,
        "guardrail_flags": [],
        "retrieved_sources": [],
        "turn_count": 1,
        "events": [],
        "runtime_mode": "product_adapter_skeleton",
    }
    result = evaluator._evaluate_case(
        case,
        body,
        endpoint="product",
        provider_config=provider_config,
        allow_fallback=False,
    )
    assert result.status in {"PASS", "WARN"}
