"""Pure scoring, failure classification and aggregation for model evaluation.

This module contains no network calls. The benchmark orchestrates real LiteLLM
calls and delegates all judgement here, keeping the harness testable offline.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from modules.automation_diagnosis.litellm_client import LiteLLMClientError
from modules.flow.domain.routing import resolve_sector_id

from .contracts import PRIMARY_COMPARISON

KIND_CLASSIFICATION = "classification"
KIND_MISSING_INFO = "missing_info"
KIND_HALLUCINATION = "hallucination"
KIND_OTHER = "other"

# Canonical missing-data vocabulary with tolerant synonyms. The intake contract
# has no canonical vocabulary; production stores whatever the model returns.
_MISSING_SYNONYMS: dict[str, frozenset[str]] = {
    "ubicacion": frozenset(
        {
            "ubicacion",
            "direccion",
            "domicilio",
            "calle",
            "lugar",
            "zona",
            "direccion exacta",
            "donde",
        }
    ),
    "detalle": frozenset(
        {
            "detalle",
            "descripcion",
            "problema",
            "que ocurre",
            "que sucede",
            "que pasa",
            "motivo",
            "mas informacion",
            "informacion adicional",
        }
    ),
    "numero_contacto": frozenset(
        {"numero de contacto", "telefono", "contacto", "nombre y telefono"}
    ),
    "categoria": frozenset({"categoria", "tipo", "sector", "tipo de problema"}),
    "nombre": frozenset({"nombre", "nombre del solicitante"}),
}
_INVERTED_SYNONYMS: dict[str, str] = {}
for _canonical, _variants in _MISSING_SYNONYMS.items():
    for _variant in _variants:
        _INVERTED_SYNONYMS[_variant] = _canonical
    _INVERTED_SYNONYMS[_canonical] = _canonical


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def canonical_missing(token: str) -> str:
    normalized = normalize_text(token) or ""
    if normalized in _INVERTED_SYNONYMS:
        return _INVERTED_SYNONYMS[normalized]
    for variant, canonical in _INVERTED_SYNONYMS.items():
        if len(variant) >= 5 and variant in normalized:
            return canonical
    return normalized


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    kind: str = KIND_OTHER


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    contract: str
    category: str
    model_alias: str
    timestamp: str
    success: bool
    error_type: str | None
    error_detail: str | None
    raw_result: dict[str, Any] | None
    contract_valid: bool
    checks: tuple[CheckResult, ...]
    score: float
    weight: float
    expected_checks_total: int
    latency_ms: int | None
    usage: dict[str, Any]
    provider_model: str | None = None

    def to_line(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_alias": self.model_alias,
            "contract": self.contract,
            "category": self.category,
            "timestamp": self.timestamp,
            "success": self.success,
            "error_type": self.error_type,
            "error_detail": self.error_detail,
            "contract_valid": self.contract_valid,
            "raw_result": self.raw_result,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail, "kind": c.kind}
                for c in self.checks
            ],
            "score": self.score,
            "weight": self.weight,
            "expected_checks_total": self.expected_checks_total,
            "latency_ms": self.latency_ms,
            "usage": self.usage,
            "provider_model": self.provider_model,
        }


def _check(name: str, passed: bool, kind: str, detail: str = "") -> CheckResult:
    return CheckResult(name=name, passed=bool(passed), kind=kind, detail=detail)


def _intake_request(raw: dict[str, Any], index: int) -> dict[str, Any] | None:
    requests = raw.get("requests")
    if not isinstance(requests, list) or index >= len(requests):
        return None
    item = requests[index]
    return item if isinstance(item, dict) else None


def evaluate_intake(
    case: dict[str, Any],
    raw: dict[str, Any] | None,
    *,
    contract_valid: bool,
) -> list[CheckResult]:
    """Check an intake interpretation against expected values (pure function)."""
    expected = case["expected"]
    checks: list[CheckResult] = []

    if not contract_valid or raw is None:
        checks.append(_check("contract_valid", False, KIND_OTHER, "invalid JSON or schema"))
        return checks

    actual_requests = raw.get("requests")
    if not isinstance(actual_requests, list):
        checks.append(_check("contract_valid", False, KIND_OTHER, "requests is not a list"))
        return checks

    count_expectation = expected.get("request_count")
    if count_expectation is not None:
        passed = _count_matches(len(actual_requests), count_expectation)
        checks.append(
            _check(
                "request_count",
                passed,
                KIND_CLASSIFICATION,
                f"expected={count_expectation!r} actual={len(actual_requests)}",
            )
        )
    range_allows_zero = (
        isinstance(count_expectation, list) and count_expectation[0] == 0
    )

    clarification = expected.get("clarification_required")
    if clarification is not None:
        actual_q = raw.get("clarification_question")
        if clarification is True:
            passed = isinstance(actual_q, str) and bool(actual_q.strip())
            detail = "expected a clarification question"
        else:
            passed = actual_q is None
            detail = "expected no clarification question"
        checks.append(
            _check("clarification_question", passed, KIND_MISSING_INFO, detail)
        )

    for index, request_expectation in enumerate(expected.get("requests") or []):
        actual = _intake_request(raw, index)
        prefix = f"request[{index}]"
        if actual is None:
            if range_allows_zero and not actual_requests:
                continue  # zero-request response is explicitly permitted by the range
            checks.append(
                _check(
                    f"{prefix}.present",
                    False,
                    KIND_CLASSIFICATION,
                    "expected request not produced",
                )
            )
            continue

        for needle in request_expectation.get("description_contains") or []:
            checks.append(
                _check(
                    f"{prefix}.description_contains",
                    _contains(actual.get("description"), needle),
                    KIND_OTHER,
                    f"needle={needle!r}",
                )
            )
        any_needles = request_expectation.get("description_contains_any") or []
        if any_needles:
            checks.append(
                _check(
                    f"{prefix}.description_contains_any",
                    any(_contains(actual.get("description"), needle) for needle in any_needles),
                    KIND_OTHER,
                    f"needles={any_needles!r}",
                )
            )
        for needle in request_expectation.get("description_not_contains") or []:
            checks.append(
                _check(
                    f"{prefix}.description_not_contains",
                    not _contains(actual.get("description"), needle),
                    KIND_HALLUCINATION,
                    f"forbidden={needle!r}",
                )
            )

        if "sector" in request_expectation:
            sector_expectation = request_expectation["sector"]
            if sector_expectation == "any":
                passed = True
            else:
                actual_sector = resolve_sector_id(actual.get("tentative_category"))
                passed = actual_sector == sector_expectation
            checks.append(
                _check(
                    f"{prefix}.sector",
                    passed,
                    KIND_CLASSIFICATION,
                    f"expected={sector_expectation!r} actual={resolve_sector_id(actual.get('tentative_category'))!r}",
                )
            )

        if "tentative_category" in request_expectation:
            category_expectation = request_expectation["tentative_category"]
            if category_expectation == "any":
                passed = True
            elif category_expectation is None:
                passed = actual.get("tentative_category") is None
            else:
                passed = normalize_text(actual.get("tentative_category")) == normalize_text(
                    category_expectation
                )
            checks.append(
                _check(
                    f"{prefix}.tentative_category",
                    passed,
                    KIND_CLASSIFICATION,
                    f"expected={category_expectation!r}",
                )
            )

        if "location_text" in request_expectation:
            location_expectation = request_expectation["location_text"]
            actual_location = actual.get("location_text")
            detail = ""
            if location_expectation == "any":
                passed = True
            elif location_expectation is None:
                passed = actual_location is None
                detail = "must not invent a location"
            else:
                passed = normalize_text(actual_location) == normalize_text(
                    location_expectation
                )
                detail = f"expected={location_expectation!r}"
            checks.append(
                _check(
                    f"{prefix}.location_text",
                    passed,
                    KIND_HALLUCINATION if location_expectation is None else KIND_OTHER,
                    detail,
                )
            )
        for needle in request_expectation.get("location_contains") or []:
            checks.append(
                _check(
                    f"{prefix}.location_contains",
                    _contains(actual.get("location_text"), needle),
                    KIND_OTHER,
                    f"needle={needle!r}",
                )
            )
        for needle in request_expectation.get("location_or_context_contains") or []:
            location = actual.get("location_text") or ""
            context = actual.get("context_notes") or ""
            passed = _contains(location, needle) or _contains(context, needle)
            checks.append(
                _check(
                    f"{prefix}.location_or_context_contains",
                    passed,
                    KIND_OTHER,
                    f"needle={needle!r}",
                )
            )

        if "missing_data" in request_expectation:
            expected_missing = {
                canonical_missing(token) for token in request_expectation["missing_data"]
            }
            actual_missing = {
                canonical_missing(token)
                for token in (actual.get("missing_data") or [])
                if isinstance(token, str)
            }
            coverage = expected_missing <= actual_missing
            extra = actual_missing - expected_missing
            no_extra = not extra
            checks.append(
                _check(
                    f"{prefix}.missing_data",
                    coverage,
                    KIND_MISSING_INFO,
                    f"expected={sorted(expected_missing)} actual={sorted(actual_missing)}",
                )
            )
            if request_expectation.get("missing_data_no_extra"):
                checks.append(
                    _check(
                        f"{prefix}.missing_data_no_extra",
                        no_extra,
                        KIND_HALLUCINATION,
                        f"invented={sorted(extra)}",
                    )
                )

        for needle in request_expectation.get("context_notes_contains") or []:
            checks.append(
                _check(
                    f"{prefix}.context_notes_contains",
                    _contains(actual.get("context_notes"), needle),
                    KIND_OTHER,
                    f"needle={needle!r}",
                )
            )

    return checks


def evaluate_operational(
    case: dict[str, Any],
    raw: dict[str, Any] | None,
    *,
    contract_valid: bool,
) -> list[CheckResult]:
    expected_action = case["expected"]["action"]
    if not contract_valid or raw is None:
        return [
            _check("contract_valid", False, KIND_OTHER, "invalid JSON or schema"),
            _check("action", False, KIND_CLASSIFICATION, f"expected={expected_action}"),
        ]
    actual_action = raw.get("action")
    passed = actual_action == expected_action
    return [
        _check(
            "action",
            passed,
            KIND_CLASSIFICATION,
            f"expected={expected_action} actual={actual_action!r}",
        )
    ]


def evaluate_case(
    case: dict[str, Any],
    raw: dict[str, Any] | None,
    *,
    contract_valid: bool,
) -> tuple[list[CheckResult], float]:
    if case["contract"] == "operational":
        checks = evaluate_operational(case, raw, contract_valid=contract_valid)
    else:
        checks = evaluate_intake(case, raw, contract_valid=contract_valid)
    passed = sum(1 for check in checks if check.passed)
    total = len(checks)
    score = passed / total if total else 1.0
    return checks, score


def _count_matches(actual: int, expectation: Any) -> bool:
    if isinstance(expectation, list):
        minimum, maximum = expectation
        return minimum <= actual <= maximum
    return actual == expectation


def _contains(haystack: Any, needle: str) -> bool:
    if not isinstance(haystack, str):
        return False
    normalized_needle = normalize_text(needle) or ""
    if not normalized_needle:
        return True
    return normalized_needle in (normalize_text(haystack) or "")


def classify_failure(exc: BaseException) -> tuple[str, str]:
    """Map any harness exception to (failure_type, detail). Pure function."""
    cause = exc.__cause__
    if isinstance(cause, LiteLLMClientError):
        message = str(cause)
        if "not configured" in message.lower():
            return "ENVIRONMENT_FAILURE", message
        return "LITELLM_FAILURE", message
    if isinstance(exc, LiteLLMClientError):
        message = str(exc)
        if "not configured" in message.lower():
            return "ENVIRONMENT_FAILURE", message
        return "LITELLM_FAILURE", message
    message = str(exc)
    lowered = message.lower()
    if "did not contain json" in lowered:
        return "MODEL_OUTPUT_FAILURE", "response did not contain JSON"
    if "invalid json" in lowered:
        return "MODEL_OUTPUT_FAILURE", "response contained invalid JSON"
    if "schema validation failed" in lowered:
        return "MODEL_OUTPUT_FAILURE", "schema violation"
    if "request failed" in lowered or "http" in lowered or "litellm" in lowered:
        return "LITELLM_FAILURE", message
    return "MODEL_EVAL_CODE_FAILURE", message


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((percentile / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def aggregate_metrics(
    alias: str,
    evaluations: Sequence[CaseEvaluation],
    *,
    escalation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed = [e for e in evaluations if e.success]
    failed = [e for e in evaluations if not e.success]

    error_counts: dict[str, int] = {}
    for evaluation in failed:
        error_counts[evaluation.error_type or "MODEL_EVAL_CODE_FAILURE"] = (
            error_counts.get(evaluation.error_type or "MODEL_EVAL_CODE_FAILURE", 0) + 1
        )

    json_valid = sum(1 for e in completed if e.contract_valid)
    json_valid_rate = json_valid / len(evaluations) if evaluations else 0.0

    # The primary score includes failed cases as 0 so reliability (e.g. empty
    # content from reasoning models) cannot be masked by dropping failures.
    weighted_score = _weighted_score(evaluations)
    score_completed = _weighted_score(completed)
    intake_evals = [e for e in evaluations if e.contract == "intake"]
    operational_evals = [e for e in evaluations if e.contract == "operational"]
    score_intake = _weighted_score(intake_evals)
    score_operational = _weighted_score(operational_evals)

    classification_checks = 0
    classification_passed = 0
    for evaluation in completed:
        for check in evaluation.checks:
            if check.kind == KIND_CLASSIFICATION:
                classification_checks += 1
                classification_passed += int(check.passed)
    classification_accuracy = (
        classification_passed / classification_checks if classification_checks else None
    )

    missing_info = _missing_info_metrics(intake_evals)
    hallucination = _hallucination_metrics(completed)

    latencies = [e.latency_ms for e in completed if e.latency_ms is not None]
    latency = {
        "count": len(latencies),
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
        "average": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }

    tokens = {"prompt": 0, "completion": 0, "total": 0, "count": 0, "present": False}
    for evaluation in completed:
        usage = evaluation.usage or {}
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        if prompt is not None or completion is not None or total is not None:
            tokens["present"] = True
            tokens["count"] += 1
        if isinstance(prompt, int):
            tokens["prompt"] += prompt
        if isinstance(completion, int):
            tokens["completion"] += completion
        if isinstance(total, int):
            tokens["total"] += total

    return {
        "alias": alias,
        "cases_total": len(evaluations),
        "completed": len(completed),
        "failed": len(failed),
        "errors": error_counts,
        "json_valid_rate": round(json_valid_rate, 4),
        "score": round(weighted_score, 4),
        "score_completed": round(score_completed, 4),
        "score_intake": round(score_intake, 4),
        "score_operational": round(score_operational, 4),
        "classification_accuracy": (
            round(classification_accuracy, 4) if classification_accuracy is not None else None
        ),
        "escalation": escalation if escalation is not None else {},
        "missing_info": missing_info,
        "hallucination": hallucination,
        "latency": latency,
        "tokens": tokens,
        "cost": "N/A",
    }


def _weighted_score(evaluations: Sequence[CaseEvaluation]) -> float:
    total_weight = sum(e.weight for e in evaluations)
    if not total_weight:
        return 0.0
    return sum(e.score * e.weight for e in evaluations) / total_weight


def _missing_info_metrics(intake_evals: Sequence[CaseEvaluation]) -> dict[str, Any]:
    covered = 0
    checks_total = 0
    for evaluation in intake_evals:
        for check in evaluation.checks:
            if check.kind == KIND_MISSING_INFO:
                checks_total += 1
                covered += int(check.passed)
    return {
        "coverage_rate": round(covered / checks_total, 4) if checks_total else None,
        "checks": checks_total,
    }


def _hallucination_metrics(evaluations: Sequence[CaseEvaluation]) -> dict[str, Any]:
    violations = 0
    checks_total = 0
    for evaluation in evaluations:
        for check in evaluation.checks:
            if check.kind == KIND_HALLUCINATION:
                checks_total += 1
                violations += int(not check.passed)
    return {
        "violations": violations,
        "checks": checks_total,
        "violation_rate": round(violations / checks_total, 4) if checks_total else None,
    }


def escalation_from_evaluations(
    evaluations: Sequence[CaseEvaluation], cases: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Escalation accuracy: RESOLUTION_PROPOSED is the closure/supervisor trigger."""
    by_id = {case["id"]: case for case in cases}
    tp = fp = fn = tn = 0
    contract_failures = 0
    for evaluation in evaluations:
        case = by_id.get(evaluation.case_id)
        if case is None or case["contract"] != "operational":
            continue
        if not evaluation.success or not evaluation.contract_valid:
            contract_failures += 1
            continue
        expected = case["expected"]["action"]
        actual = (evaluation.raw_result or {}).get("action")
        if expected == "RESOLUTION_PROPOSED":
            if actual == "RESOLUTION_PROPOSED":
                tp += 1
            else:
                fn += 1
        else:
            if actual == "RESOLUTION_PROPOSED":
                fp += 1
            else:
                tn += 1
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "contract_failures": contract_failures,
        "error_rate": round((fp + fn) / total, 4) if total else None,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def magnitude_label(delta: float) -> str:
    if delta < -0.005:
        return "peor"
    if delta >= 0.05:
        return "material"
    if delta >= 0.02:
        return "moderada"
    if delta >= 0.005:
        return "marginal"
    return "inexistente"


def recommend(nano: dict[str, Any], luna: dict[str, Any]) -> tuple[str, str]:
    """Decision rule: Luna only if consistent and material improvement."""
    delta = (luna["score"] or 0.0) - (nano["score"] or 0.0)
    label = magnitude_label(delta)
    nano_esc = nano["escalation"].get("error_rate")
    luna_esc = luna["escalation"].get("error_rate")
    escalation_not_worse = True
    if nano_esc is not None and luna_esc is not None:
        escalation_not_worse = luna_esc <= nano_esc + 0.02
    if delta >= 0.05 and escalation_not_worse:
        return "openai_gpt-5.6-luna-medium", label
    return "openai_gpt-5.4-nano", label
