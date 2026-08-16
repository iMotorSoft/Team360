"""Unit tests for the model evaluation harness. No real model calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from modules.automation_diagnosis.litellm_client import LiteLLMClientError
from modules.flow.intake.ai import FlowIntakeAIError
from modules.flow.model_eval.benchmark import decision_signature, preflight_alias, run_case_once
from modules.flow.model_eval.contracts import FAILURE_TYPES, MODEL_ALIASES, PRIMARY_COMPARISON
from modules.flow.model_eval.dataset import consistency_subset, load_cases, validate_cases
from modules.flow.model_eval.evaluator import (
    KIND_CLASSIFICATION,
    KIND_HALLUCINATION,
    KIND_MISSING_INFO,
    CaseEvaluation,
    aggregate_metrics,
    canonical_missing,
    classify_failure,
    escalation_from_evaluations,
    evaluate_case,
    evaluate_intake,
    magnitude_label,
    normalize_text,
    recommend,
)


def _case(**overrides):
    case = {
        "id": "flow_eval_test",
        "contract": "intake",
        "category": "test",
        "message": "Hay una luminaria apagada en Olleros 2200.",
        "weight": 1.0,
        "expected": {
            "request_count": 1,
            "requests": [
                {
                    "description_contains": ["luminaria"],
                    "sector": "alumbrado",
                    "location_contains": ["olleros"],
                    "missing_data": [],
                    "missing_data_no_extra": True,
                }
            ],
        },
    }
    case.update(overrides)
    return case


def _raw_ok(**overrides):
    raw = {
        "requests": [
            {
                "description": "Reparar luminaria apagada",
                "tentative_category": "alumbrado",
                "location_text": "Olleros 2200",
                "missing_data": [],
                "context_notes": None,
                "confidence": 0.95,
            }
        ],
        "clarification_question": None,
    }
    raw.update(overrides)
    return raw


def _evaluation(case, raw, *, success=True, error_type=None, contract_valid=True, latency_ms=100, usage=None, score_override=None):
    checks, score = evaluate_case(case, raw, contract_valid=contract_valid)
    if score_override is not None:
        score = score_override
    return CaseEvaluation(
        case_id=case["id"],
        contract=case["contract"],
        category=case["category"],
        model_alias="openai_gpt-5.4-nano",
        timestamp="2026-08-16T00:00:00Z",
        success=success,
        error_type=error_type,
        error_detail=None,
        raw_result=raw,
        contract_valid=contract_valid,
        checks=tuple(checks),
        score=score,
        weight=case["weight"],
        expected_checks_total=len(checks),
        latency_ms=latency_ms,
        usage=usage if usage is not None else {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


# --------------------------------------------------------------------------- dataset


def test_dataset_loads_both_contracts():
    cases = load_cases()
    ids = {case["id"] for case in cases}
    assert any(case["contract"] == "intake" for case in cases)
    assert any(case["contract"] == "operational" for case in cases)
    assert len(ids) == len(cases)
    assert any(case["id"].startswith("flow_eval_op_") for case in cases)
    assert 20 <= len(cases) <= 30


def test_dataset_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate case id"):
        validate_cases([_case(id="dup"), _case(id="dup")])


def test_dataset_operational_requires_valid_action():
    case = _case(id="op_bad", contract="operational", expected={"action": "NOPE"})
    with pytest.raises(ValueError, match="invalid expected action"):
        validate_cases([case])


def test_dataset_intake_without_expectations_rejected():
    case = _case(expected={"requests": []})
    with pytest.raises(ValueError, match="without verifiable expectations"):
        validate_cases([case])


def test_consistency_subset_nonempty():
    subset = consistency_subset(load_cases())
    assert subset
    assert all(case.get("consistency_subset") for case in subset)


# --------------------------------------------------------------------- evaluator


def test_normalize_text_strips_accents_and_case():
    assert normalize_text("  Áv. Maipú 850  ") == "av. maipu 850"
    assert normalize_text(None) is None


def test_canonical_missing_synonyms():
    assert canonical_missing("Dirección") == "ubicacion"
    assert canonical_missing("descripción del problema") == "detalle"
    assert canonical_missing("numero de contacto") == "numero_contacto"


def test_intake_full_pass():
    case = _case()
    checks, score = evaluate_case(case, _raw_ok(), contract_valid=True)
    assert score == 1.0
    assert all(check.passed for check in checks)


def test_intake_wrong_sector_fails():
    raw = _raw_ok()
    raw["requests"][0]["tentative_category"] = "bache"
    checks, score = evaluate_case(_case(), raw, contract_valid=True)
    assert score < 1.0
    sector = [c for c in checks if c.name == "request[0].sector"][0]
    assert not sector.passed


def test_intake_invented_location_fails():
    raw = _raw_ok()
    raw["requests"][0]["location_text"] = "Olleros 9999"
    checks, score = evaluate_case(_case(expected={"request_count": 1, "requests": [{"location_text": None}]}), raw, contract_valid=True)
    assert score < 1.0
    location = [c for c in checks if c.name == "request[0].location_text"][0]
    assert not location.passed
    assert location.kind == KIND_HALLUCINATION


def test_intake_extra_missing_data_fails_no_extra():
    raw = _raw_ok()
    raw["requests"][0]["missing_data"] = ["ubicación", "teléfono"]
    checks, score = evaluate_case(_case(), raw, contract_valid=True)
    assert score < 1.0
    assert any(c.name == "request[0].missing_data_no_extra" and not c.passed for c in checks)


def test_intake_missing_data_synonyms_pass():
    case = _case(expected={"request_count": 1, "requests": [{"missing_data": ["ubicacion"]}]})
    raw = _raw_ok()
    raw["requests"][0]["missing_data"] = ["Dirección"]
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0


def test_intake_description_contains_any():
    case = _case(
        expected={"request_count": 1, "requests": [{"description_contains_any": ["luces", "luz"]}]}
    )
    raw = _raw_ok()
    raw["requests"][0]["description"] = "Consulta por un tema de luces de la calle"
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0
    raw["requests"][0]["description"] = "Consulta sobre la vereda"
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 0.5
    assert any(c.name == "request[0].description_contains_any" and not c.passed for c in checks)


def test_intake_location_any_check_passes():
    case = _case(expected={"request_count": 1, "requests": [{"location_text": "any"}]})
    raw = _raw_ok()
    raw["requests"][0]["location_text"] = "la cuadra"
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0


def test_intake_request_count_range_zero_skips_per_request_checks():
    case = _case(expected={"request_count": [0, 1], "clarification_required": True})
    raw = {"requests": [], "clarification_question": "¿Podrías indicar la dirección?"}
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0


def test_intake_request_count_range():
    case = _case(expected={"request_count": [0, 1], "clarification_required": True})
    raw = _raw_ok()
    raw["requests"] = []
    raw["clarification_question"] = "¿Podrías indicar la dirección?"
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0


def test_intake_multi_topic_location_or_context():
    case = _case(
        expected={
            "request_count": 2,
            "requests": [
                {"description_contains": ["luminaria"], "sector": "alumbrado"},
                {"description_contains": ["arbol"], "sector": None, "location_or_context_contains": ["misma cuadra"]},
            ],
        }
    )
    raw = {
        "requests": [
            {"description": "Reparar luminaria", "tentative_category": "alumbrado", "location_text": "Av. de los Inmigrantes 2400", "missing_data": [], "context_notes": None, "confidence": 0.9},
            {"description": "Retirar árbol caído", "tentative_category": "arbolado", "location_text": None, "missing_data": [], "context_notes": "en la misma cuadra", "confidence": 0.8},
        ],
        "clarification_question": None,
    }
    checks, score = evaluate_case(case, raw, contract_valid=True)
    assert score == 1.0


def test_contract_invalid_scores_zero():
    checks, score = evaluate_case(_case(), None, contract_valid=False)
    assert score == 0.0
    assert all(not check.passed for check in checks)


def test_operational_action_pass_and_fail():
    case = _case(id="op1", contract="operational", expected={"action": "RESOLUTION_PROPOSED"})
    checks, score = evaluate_case(case, {"action": "RESOLUTION_PROPOSED", "summary": "ok"}, contract_valid=True)
    assert score == 1.0
    checks, score = evaluate_case(case, {"action": "ACK_OR_PROGRESS", "summary": "ok"}, contract_valid=True)
    assert score == 0.0


# ------------------------------------------------------------ failure taxonomy


def test_classify_litellm_failure():
    error = FlowIntakeAIError("LiteLLM Flow intake request failed.")
    error.__cause__ = LiteLLMClientError("LiteLLM HTTP 429: rate limited")
    assert classify_failure(error) == ("LITELLM_FAILURE", "LiteLLM HTTP 429: rate limited")


def test_classify_environment_missing_key():
    error = FlowIntakeAIError("LiteLLM Flow intake request failed.")
    error.__cause__ = LiteLLMClientError("LiteLLM API key not configured")
    assert classify_failure(error)[0] == "ENVIRONMENT_FAILURE"


def test_classify_invalid_json_model_output():
    error = FlowIntakeAIError("Flow intake AI returned invalid JSON.")
    assert classify_failure(error) == ("MODEL_OUTPUT_FAILURE", "response contained invalid JSON")


def test_classify_schema_violation_model_output():
    error = FlowIntakeAIError("Flow intake AI initial schema validation failed.")
    assert classify_failure(error)[0] == "MODEL_OUTPUT_FAILURE"


def test_failure_types_are_consistent():
    assert set(FAILURE_TYPES) >= {"MODEL_OUTPUT_FAILURE", "LITELLM_FAILURE", "ENVIRONMENT_FAILURE"}


# --------------------------------------------------------------------- metrics


def _completed(case, raw, score_override=None, usage=None):
    evaluation = _evaluation(case, raw, usage=usage)
    if score_override is not None:
        checks = evaluation.checks
        evaluation = CaseEvaluation(
            case_id=evaluation.case_id,
            contract=evaluation.contract,
            category=evaluation.category,
            model_alias=evaluation.model_alias,
            timestamp=evaluation.timestamp,
            success=evaluation.success,
            error_type=evaluation.error_type,
            error_detail=evaluation.error_detail,
            raw_result=evaluation.raw_result,
            contract_valid=evaluation.contract_valid,
            checks=checks,
            score=score_override,
            weight=evaluation.weight,
            expected_checks_total=evaluation.expected_checks_total,
            latency_ms=evaluation.latency_ms,
            usage=evaluation.usage,
            provider_model=evaluation.provider_model,
        )
    return evaluation


def test_aggregate_json_valid_and_tokens_na():
    evaluations = [
        _evaluation(_case(), _raw_ok(), usage={"total_tokens": 30}),
        _evaluation(_case(), None, success=False, error_type="MODEL_OUTPUT_FAILURE", contract_valid=False, usage={}),
    ]
    metrics = aggregate_metrics("openai_gpt-5.4-nano", evaluations)
    assert metrics["json_valid_rate"] == 0.5
    assert metrics["errors"] == {"MODEL_OUTPUT_FAILURE": 1}
    assert metrics["tokens"]["total"] == 30
    assert metrics["cost"] == "N/A"


def test_aggregate_tokens_na_when_usage_absent():
    evaluation = _evaluation(_case(), _raw_ok(), usage={})
    metrics = aggregate_metrics("openai_gpt-5.4-nano", [evaluation])
    assert metrics["tokens"]["present"] is False
    assert metrics["tokens"]["total"] == 0


def test_aggregate_latency_percentiles():
    evaluations = [
        _evaluation(_case(), _raw_ok(), latency_ms=100),
        _evaluation(_case(), _raw_ok(), latency_ms=200),
        _evaluation(_case(), _raw_ok(), latency_ms=300),
    ]
    metrics = aggregate_metrics("openai_gpt-5.4-nano", evaluations)
    assert metrics["latency"]["p50"] == 200
    assert metrics["latency"]["p95"] == 300
    assert metrics["latency"]["average"] == 200.0


def test_escalation_fp_fn_metrics():
    op_cases = [
        _case(id="op_a", contract="operational", expected={"action": "ACK_OR_PROGRESS"}),
        _case(id="op_b", contract="operational", expected={"action": "RESOLUTION_PROPOSED"}),
        _case(id="op_c", contract="operational", expected={"action": "RESOLUTION_PROPOSED"}),
    ]
    evaluations = [
        _evaluation(op_cases[0], {"action": "RESOLUTION_PROPOSED", "summary": "x"}),  # FP
        _evaluation(op_cases[1], {"action": "RESOLUTION_PROPOSED", "summary": "x"}),  # TP
        _evaluation(op_cases[2], {"action": "ACK_OR_PROGRESS", "summary": "x"}),      # FN
    ]
    escalation = escalation_from_evaluations(evaluations, op_cases)
    assert escalation["tp"] == 1
    assert escalation["fp"] == 1
    assert escalation["fn"] == 1
    assert escalation["tn"] == 0
    assert escalation["error_rate"] == round(2 / 3, 4)


def test_weighted_score_priority():
    normal = _evaluation(_case(), _raw_ok(), score_override=1.0)
    critical = _evaluation(
        _case(id="crit", contract="operational", weight=2.0, expected={"action": "ACK_OR_PROGRESS"}),
        {"action": "RESOLUTION_PROPOSED", "summary": "x"},
        score_override=0.0,
    )
    metrics = aggregate_metrics("openai_gpt-5.4-nano", [normal, critical])
    assert metrics["score"] == round(1 / 3, 4)


def test_failed_case_counts_as_zero_in_score():
    ok_eval = _evaluation(_case(), _raw_ok(), score_override=1.0)
    failed = _evaluation(
        _case(id="f1", expected={"request_count": 1}),
        None,
        success=False,
        error_type="MODEL_OUTPUT_FAILURE",
        contract_valid=False,
        score_override=0.0,
    )
    metrics = aggregate_metrics("openai_gpt-5.4-nano", [ok_eval, failed])
    assert metrics["score"] == 0.5
    assert metrics["score_completed"] == 1.0
    assert metrics["json_valid_rate"] == 0.5


def test_hallucination_violations_counted():
    case = _case(expected={"request_count": 1, "requests": [{"location_text": None}]})
    raw = _raw_ok()
    raw["requests"][0]["location_text"] = "Olleros 9999"
    evaluation = _evaluation(case, raw)
    metrics = aggregate_metrics("openai_gpt-5.4-nano", [evaluation])
    assert metrics["hallucination"]["violations"] == 1


# ------------------------------------------------------------- recommendation


def test_magnitude_labels():
    assert magnitude_label(0.06) == "material"
    assert magnitude_label(0.03) == "moderada"
    assert magnitude_label(0.01) == "marginal"
    assert magnitude_label(0.001) == "inexistente"
    assert magnitude_label(-0.01) == "peor"


def test_recommend_keeps_nano_when_close():
    nano = {"score": 0.80, "escalation": {"error_rate": 0.10}}
    luna = {"score": 0.81, "escalation": {"error_rate": 0.09}}
    assert recommend(nano, luna)[0] == "openai_gpt-5.4-nano"


def test_recommend_luna_when_material_and_not_worse():
    nano = {"score": 0.70, "escalation": {"error_rate": 0.20}}
    luna = {"score": 0.78, "escalation": {"error_rate": 0.10}}
    assert recommend(nano, luna)[0] == "openai_gpt-5.6-luna-medium"


def test_recommend_rejects_luna_when_escalation_worse():
    nano = {"score": 0.70, "escalation": {"error_rate": 0.05}}
    luna = {"score": 0.78, "escalation": {"error_rate": 0.30}}
    assert recommend(nano, luna)[0] == "openai_gpt-5.4-nano"


# ------------------------------------------------------------------- benchmark


def test_decision_signature_stable():
    case = _case(contract="operational", expected={"action": "RESOLUTION_PROPOSED"})
    assert decision_signature(case, {"action": "RESOLUTION_PROPOSED", "summary": "x"}) == "action=RESOLUTION_PROPOSED"
    assert decision_signature(case, None) == "error"


def test_preflight_alias_reports_failure_without_network():
    class _BrokenClient:
        def chat_completion(self, *args, **kwargs):
            raise LiteLLMClientError("LiteLLM request failed: connection refused")

    result = preflight_alias(_BrokenClient(), "openai_gpt-5.4-nano")  # type: ignore[arg-type]
    assert result["status"] == "FAIL"


def test_primary_comparison_aliases_are_litellm_aliases():
    assert set(PRIMARY_COMPARISON) <= set(MODEL_ALIASES)
    assert len(PRIMARY_COMPARISON) == 2


def test_run_case_once_uses_real_interpreter_with_fake_client():
    from modules.automation_diagnosis.litellm_client import LiteLLMResponse

    class _FakeClient:
        def text_completion(self, model, messages, **kwargs):
            self.calls = getattr(self, "calls", [])
            self.calls.append((model, messages))
            return LiteLLMResponse(
                content=json.dumps(_raw_ok(), ensure_ascii=False),
                model=model,
                usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                latency_ms=7,
            )

    client = _FakeClient()
    evaluation = run_case_once(_case(), "openai_gpt-5.4-nano", client)  # type: ignore[arg-type]
    assert evaluation.success
    assert evaluation.score == 1.0
    assert evaluation.latency_ms == 7
    assert evaluation.usage["total_tokens"] == 12
