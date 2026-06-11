"""Headless semantic evaluator for Sales Diagnosis responses.

The evaluator sends a dataset of diagnostic questions to the backend and
scores the answers semantically with conservative heuristics. It is meant
for backend validation, not UI testing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_BACKEND_URL = "http://127.0.0.1:8018"
PRODUCT_ENDPOINT = "/api/sales-diagnosis-runtime/turn"
DEV_ENDPOINT = "/api/dev/sales-diagnosis-runtime/turn"
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "tests/fixtures/sales_diagnosis_headless_questions_v1.json"
DEFAULT_TIMEOUT = 45.0

PRODUCT_ROUTE_ENABLED_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
PRODUCT_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER"
PRODUCT_RETRIEVAL_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER"

DEV_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY"
DEV_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER"
DEV_RETRIEVAL_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER"

GLOBAL_FORBIDDEN_PATTERNS = (
    "garantizado",
    "garantizada",
    "garantizamos",
    "garantiza",
    "siempre automatizable",
    "100 seguro",
    "100% seguro",
    "sin riesgos",
    "sin costo de error",
    "no hace falta consultoria",
    "no hace falta validacion tecnica",
    "la ia decide sola",
    "implementacion inmediata garantizada",
    "whatsapp handoff listo",
    "lead capture listo",
    "crm integrado listo",
    "diagnostic_code disponible",
    "diagnostic code disponible",
    "step to action disponible",
    "step-to-action disponible",
    "podemos automatizar cualquier proceso",
    "siempre te diremos que si",
    "rentable decir que si aunque no sea cierto",
)

NEGATION_PHRASES = (
    "no es",
    "no son",
    "no estamos",
    "no estoy",
    "no podemos",
    "no puedo",
    "no garantizamos",
    "no garantizo",
    "no promete",
    "no prometemos",
    "no requiere",
    "no requieren",
    "no hace falta",
    "no hay",
    "no contamos",
    "no contamos con",
    "no tenemos",
    "no esta",
    "no siempre",
    "todavia no",
    "aun no",
    "depende",
)

STOPWORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "o",
    "en",
    "para",
    "con",
    "sin",
    "que",
    "un",
    "una",
    "unos",
    "unas",
    "por",
    "al",
    "a",
    "es",
    "son",
    "sea",
    "si",
    "sí",
    "siempre",
}

RISK_HINTS = {
    "mfa": ("mfa", "permisos", "acceso", "bloqueado", "aprobacion humana"),
    "human_review_required": ("revisión humana", "revision humana", "consultar", "equipo humano"),
    "partner_fit": ("partner", "consultoria", "derivar", "conviene"),
    "scope_honesty": ("no promet", "limite", "futuro"),
    "commercial_trust": ("no es un formulario", "no es lead", "honesto"),
    "hallucination_control": ("no garantiza", "no afirma", "limite", "depende"),
    "implementation_risk": ("validacion", "preliminar", "riesgo"),
    "liability": ("no promete", "no asume", "responsabilidad"),
    "input_integrity": ("calidad de la informacion", "honesto"),
    "commercial_honesty": ("no siempre", "caso por caso", "no automatizar"),
}


@dataclass
class CaseEvaluation:
    id: str
    level: str
    validates: str
    status: str
    reason: str
    response_preview: str
    expected_coverage: str
    forbidden_hits: list[str] = field(default_factory=list)
    matched_expected_claims: list[str] = field(default_factory=list)
    optional_risk_flags: list[str] = field(default_factory=list)
    fallback_detected: bool = False
    guardrail_fallback_detected: bool = False
    provider_result_seen: bool = False
    contract_ok: bool = True


@dataclass
class RunSummary:
    total: int = 0
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> list[str]:
    return [token for token in _normalize_text(text).split() if token]


def _is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _has_tokens(text: str, phrase: str) -> bool:
    text_norm = _normalize_text(text)
    phrase_norm = _normalize_text(phrase)
    if not phrase_norm:
        return False
    if phrase_norm in text_norm:
        return True
    phrase_tokens = [token for token in _tokenize(phrase_norm) if token not in STOPWORDS]
    if not phrase_tokens:
        return False
    text_tokens = set(_tokenize(text_norm))
    if len(phrase_tokens) == 1:
        return phrase_tokens[0] in text_tokens
    matched = sum(1 for token in phrase_tokens if token in text_tokens)
    required = max(1, math.ceil(len(phrase_tokens) * 0.67))
    return matched >= required


def _phrase_negated(text_norm: str, phrase_norm: str) -> bool:
    index = text_norm.find(phrase_norm)
    if index < 0:
        return False
    window = text_norm[max(0, index - 70):index]
    if window.rstrip().endswith("no"):
        return True
    return any(neg in window for neg in NEGATION_PHRASES)


def _find_forbidden_hits(text: str, forbidden_claims: list[str]) -> list[str]:
    text_norm = _normalize_text(text)
    hits: list[str] = []
    for claim in list(GLOBAL_FORBIDDEN_PATTERNS) + list(forbidden_claims):
        claim_norm = _normalize_text(claim)
        if not claim_norm:
            continue
        if claim_norm not in text_norm:
            continue
        if _phrase_negated(text_norm, claim_norm):
            continue
        hits.append(claim)
    return hits


def _match_expected_claims(text: str, expected_claims: list[str]) -> list[str]:
    hits: list[str] = []
    for claim in expected_claims:
        if _has_tokens(text, claim):
            hits.append(claim)
    return hits


def _detect_risk_support(text: str, risk_flags: list[str]) -> list[str]:
    text_norm = _normalize_text(text)
    supported: list[str] = []
    for flag in risk_flags:
        hints = RISK_HINTS.get(flag, ())
        if any(_normalize_text(hint) in text_norm for hint in hints):
            supported.append(flag)
    return supported


def _truncate(text: str, limit: int = 240) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _redact_sensitive_text(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-<redacted>", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
    text = re.sub(
        r"(postgresql://[^:\s]+:)[^@\s]+@",
        r"\1<redacted>@",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _response_preview(body: dict[str, Any]) -> str:
    preview = body.get("response_text")
    if not isinstance(preview, str):
        preview = json.dumps(body, ensure_ascii=False)
    return _truncate(_redact_sensitive_text(preview))


def _load_dataset(dataset_path: Path) -> dict[str, Any]:
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Dataset must be a JSON object.")
    if payload.get("test_suite") != "sales_diagnosis_headless_response_validation_v1":
        raise ValueError("Unexpected test_suite in dataset.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset cases must be a non-empty list.")
    return payload


def _resolve_request_mode(endpoint: str) -> tuple[str, str]:
    if endpoint == "product":
        return PRODUCT_ENDPOINT, "product"
    if endpoint == "dev":
        return DEV_ENDPOINT, "dev"
    raise ValueError(f"Unsupported endpoint mode: {endpoint}")


def _resolve_provider_config(endpoint: str) -> dict[str, Any]:
    if endpoint == "product":
        state_repository = os.environ.get(PRODUCT_STATE_REPOSITORY_ENV, "").strip().lower()
        llm_provider = os.environ.get(PRODUCT_LLM_PROVIDER_ENV, "").strip().lower() or "fake"
        retrieval_provider = os.environ.get(PRODUCT_RETRIEVAL_PROVIDER_ENV, "").strip().lower() or "fake"
        return {
            "route_enabled": _is_truthy_env(PRODUCT_ROUTE_ENABLED_ENV),
            "state_repository": state_repository,
            "llm_provider": llm_provider,
            "retrieval_provider": retrieval_provider,
            "real_llm_expected": llm_provider in {"openai", "litellm"},
            "real_retrieval_expected": retrieval_provider == "milvus",
        }

    state_repository = os.environ.get(DEV_STATE_REPOSITORY_ENV, "").strip().lower() or "inmemory"
    llm_provider = os.environ.get(DEV_LLM_PROVIDER_ENV, "").strip().lower() or "fake"
    retrieval_provider = os.environ.get(DEV_RETRIEVAL_PROVIDER_ENV, "").strip().lower() or "fake"
    return {
        "route_enabled": True,
        "state_repository": state_repository,
        "llm_provider": llm_provider,
        "retrieval_provider": retrieval_provider,
        "real_llm_expected": llm_provider == "litellm",
        "real_retrieval_expected": retrieval_provider == "milvus",
    }


def _has_llm_config(llm_provider: str) -> bool:
    if llm_provider == "openai":
        try:
            from globalVar import get_team360_openai_key

            return bool(get_team360_openai_key())
        except Exception:
            return bool(
                os.environ.get("TEAM360_OPENAI_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )
    if llm_provider == "litellm":
        return bool(
            os.environ.get("TEAM360_LITELLM_BASE_URL")
            and (
                os.environ.get("TEAM360_LITELLM_API_KEY")
                or os.environ.get("LITELLM_API_KEY")
                or os.environ.get("LITELLM_MASTER_KEY")
            )
        )
    return True


def _has_milvus_config() -> bool:
    return bool(
        os.environ.get("TEAM360_MILVUS_URI")
        or os.environ.get("TEAM360_MILVUS_HOST")
    )


def _needs_skip(endpoint: str, provider_config: dict[str, Any]) -> tuple[bool, str]:
    if endpoint == "product":
        if not provider_config["route_enabled"]:
            return True, (
                f"{PRODUCT_ROUTE_ENABLED_ENV} is not enabled. "
                "Set TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 and "
                "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test "
                "or postgres to run the product adapter evaluator."
            )
        if not provider_config["state_repository"]:
            return True, (
                f"{PRODUCT_STATE_REPOSITORY_ENV} is required for the product adapter. "
                "Use inmemory_test for baseline evaluation or postgres for the DB-backed mode."
            )
    if provider_config["real_llm_expected"] and not _has_llm_config(provider_config["llm_provider"]):
        return True, (
            f"Real LLM mode {provider_config['llm_provider']!r} is enabled, but the required "
            "key/config is missing. Set the provider envs or use fake LLM defaults."
        )
    if provider_config["real_retrieval_expected"] and not _has_milvus_config():
        return True, (
            "Milvus retrieval mode is enabled, but TEAM360_MILVUS_URI or TEAM360_MILVUS_HOST "
            "is missing. Set the Milvus envs or use fake retrieval."
        )
    return False, ""


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    *,
    timeout: float,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            return exc.code, body_text
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc


def _build_payload(case: dict[str, Any], session_id: str, endpoint: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "message": case["question"],
        "assistant_instance_code": "team360_sales_diagnosis",
        "package_code": "pkg_sales_diagnosis",
        "knowledge_scope_code": "ks_team360_sales_diagnosis",
        "metadata": {
            "channel": "api",
            "source": "headless_evaluator",
            "case_id": case["id"],
            "dataset": "sales_diagnosis_headless_response_validation_v1",
            "endpoint": endpoint,
        },
    }


def _find_provider_result_events(body: dict[str, Any]) -> list[dict[str, Any]]:
    events = body.get("events")
    if not isinstance(events, list):
        return []
    provider_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "team360.llm.provider_result":
            continue
        provider_events.append(event)
    return provider_events


def _response_has_provider_fallback(body: dict[str, Any]) -> bool:
    for event in _find_provider_result_events(body):
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("response_is_fallback") is True:
            return True
    return False


def _response_has_guardrail_fallback(body: dict[str, Any]) -> bool:
    return body.get("fallback_applied") is True


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "event_type": event.get("event_type"),
        "safe_to_show": event.get("safe_to_show"),
    }
    payload = event.get("payload")
    if isinstance(payload, dict):
        sanitized_payload: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "text":
                sanitized_payload[key] = "<omitted>"
            elif isinstance(value, str):
                sanitized_payload[key] = _truncate(_redact_sensitive_text(value), 160)
            else:
                sanitized_payload[key] = value
        sanitized["payload"] = sanitized_payload
    return sanitized


def _validate_contract(body: dict[str, Any], endpoint: str) -> list[str]:
    expected_keys = {
        "session_id",
        "response_text",
        "response_type",
        "fallback_applied",
        "guardrail_flags",
        "retrieved_sources",
        "turn_count",
        "events",
        "runtime_mode",
    }
    errors: list[str] = []
    missing = expected_keys - set(body.keys())
    extra = set(body.keys()) - expected_keys
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected keys: {sorted(extra)}")
    if not isinstance(body.get("response_text"), str):
        errors.append("response_text must be string")
    if body.get("response_type") not in {"final", "skeleton_ack", "unsafe_blocked"}:
        errors.append(f"invalid response_type: {body.get('response_type')!r}")
    expected_runtime_mode = "product_adapter_skeleton" if endpoint == "product" else "dev_fake"
    if body.get("runtime_mode") != expected_runtime_mode:
        errors.append(f"unexpected runtime_mode: {body.get('runtime_mode')!r}")
    if not isinstance(body.get("retrieved_sources"), list):
        errors.append("retrieved_sources must be list")
    if not isinstance(body.get("events"), list):
        errors.append("events must be list")
    if not isinstance(body.get("guardrail_flags"), list):
        errors.append("guardrail_flags must be list")
    if not isinstance(body.get("turn_count"), int):
        errors.append("turn_count must be int")
    return errors


def _evaluate_case(
    case: dict[str, Any],
    body: dict[str, Any],
    *,
    endpoint: str,
    provider_config: dict[str, Any],
    allow_fallback: bool,
    fail_on_fallback: bool = False,
    require_real_llm: bool = False,
) -> CaseEvaluation:
    response_text = body.get("response_text", "")
    response_preview = _response_preview(body)
    expected_claims = case.get("expected_claims", [])
    forbidden_claims = case.get("forbidden_claims", [])
    risk_flags = case.get("optional_risk_flags", [])

    expected_hits = _match_expected_claims(response_text, expected_claims)
    forbidden_hits = _find_forbidden_hits(response_text, forbidden_claims)
    risk_hits = _detect_risk_support(response_text, risk_flags)
    provider_events = _find_provider_result_events(body)
    provider_fallback_detected = _response_has_provider_fallback(body)
    guardrail_fallback_detected = _response_has_guardrail_fallback(body)
    contract_errors = _validate_contract(body, endpoint)

    def build_result(status: str, reason: str, *, contract_ok: bool = True) -> CaseEvaluation:
        return CaseEvaluation(
            id=case["id"],
            level=case["level"],
            validates=case["validates"],
            status=status,
            reason=reason,
            response_preview=response_preview,
            expected_coverage=f"{len(expected_hits)}/{len(expected_claims)}",
            forbidden_hits=forbidden_hits,
            matched_expected_claims=expected_hits,
            optional_risk_flags=risk_hits,
            fallback_detected=provider_fallback_detected,
            guardrail_fallback_detected=guardrail_fallback_detected,
            provider_result_seen=bool(provider_events),
            contract_ok=contract_ok,
        )

    if contract_errors:
        return build_result(
            "FAIL",
            "contract invalid: " + "; ".join(contract_errors),
            contract_ok=False,
        )

    if require_real_llm and not provider_config["real_llm_expected"]:
        return build_result(
            "FAIL",
            "real LLM required, but selected client env does not request a real LLM provider",
        )

    if (
        require_real_llm
        and not provider_events
        and body.get("response_type") != "unsafe_blocked"
    ):
        return build_result(
            "FAIL",
            "real LLM required, but provider_result event is missing; "
            "backend may be running without the expected real LLM envs",
        )

    if (
        provider_fallback_detected
        and not allow_fallback
        and (provider_config["real_llm_expected"] or fail_on_fallback or require_real_llm)
    ):
        return build_result(
            "FAIL",
            "real LLM provider_result response_is_fallback=true",
        )

    if body.get("response_type") == "unsafe_blocked":
        reason = "response blocked by guardrails"
        if require_real_llm and not provider_events:
            reason += "; provider_result event not returned on unsafe_blocked response"
        return build_result("FAIL", reason)

    if forbidden_hits:
        return build_result("FAIL", f"forbidden claims hit: {', '.join(forbidden_hits)}")

    response_norm = _normalize_text(response_text)
    has_honesty_cue = any(
        cue in response_norm
        for cue in (
            "no garant",
            "depende",
            "limite",
            "no puedo afirmar",
            "no tengo informacion",
            "caso por caso",
            "no siempre",
            "no conviene",
            "revisar",
            "validacion",
        )
    )

    if expected_hits:
        status = "PASS"
        reason = f"matched expected claims: {', '.join(expected_hits[:2])}"
        if risk_flags and risk_hits:
            reason = reason + f"; risk cues seen: {', '.join(risk_hits)}"
        if provider_config["real_retrieval_expected"]:
            retrieved_sources = body.get("retrieved_sources", [])
            if not retrieved_sources:
                status = "WARN" if status == "PASS" else status
                reason = reason + "; real Milvus retrieval returned no sources"
            elif any(
                isinstance(source, dict)
                and str(source.get("chunk_id", "")).startswith("dev_doc_")
                for source in retrieved_sources
            ):
                return build_result(
                    "FAIL",
                    "real Milvus retrieval leaked fake dev_doc_* sources",
                )
        return build_result(status, reason)

    if response_text.strip() and has_honesty_cue:
        status = "WARN"
        reason = "response is honest but only partially covers expected claims"
    elif response_text.strip():
        status = "WARN"
        reason = "response is generic or insufficiently specific"
    else:
        status = "FAIL"
        reason = "empty response_text"

    if provider_config["real_retrieval_expected"]:
        retrieved_sources = body.get("retrieved_sources", [])
        if any(
            isinstance(source, dict)
            and str(source.get("chunk_id", "")).startswith("dev_doc_")
            for source in retrieved_sources
        ):
            return build_result(
                "FAIL",
                "real Milvus retrieval leaked fake dev_doc_* sources",
            )

    return build_result(status, reason)


def _print_case_result(result: CaseEvaluation, verbose: bool) -> None:
    print(f"- {result.id} [{result.level}] {result.status}")
    print(f"  validates: {result.validates}")
    print(f"  reason: {result.reason}")
    print(f"  expected coverage: {result.expected_coverage}")
    print(f"  forbidden hits: {', '.join(result.forbidden_hits) if result.forbidden_hits else '-'}")
    if result.optional_risk_flags:
        print(f"  risk flags: {', '.join(result.optional_risk_flags)}")
    if result.fallback_detected:
        print("  provider_result response_is_fallback: true")
    elif result.provider_result_seen:
        print("  provider_result response_is_fallback: false")
    if result.guardrail_fallback_detected:
        print("  guardrail fallback_applied: true")
    print(f"  response: {result.response_preview}")
    if verbose and result.matched_expected_claims:
        print(f"  matched claims: {', '.join(result.matched_expected_claims)}")


def _print_provider_config(provider_config: dict[str, Any]) -> None:
    print("Provider config (client env):")
    print(f"  route_enabled: {provider_config['route_enabled']}")
    print(f"  state_repository: {provider_config['state_repository'] or '-'}")
    print(f"  llm_provider: {provider_config['llm_provider']}")
    print(f"  retrieval_provider: {provider_config['retrieval_provider']}")
    print(f"  real_llm_expected: {provider_config['real_llm_expected']}")
    print(f"  real_retrieval_expected: {provider_config['real_retrieval_expected']}")
    if provider_config["llm_provider"] == "litellm":
        model_alias = os.environ.get("TEAM360_LITELLM_MODEL_ALIAS", "").strip()
        has_key = bool(
            os.environ.get("TEAM360_LITELLM_API_KEY")
            or os.environ.get("LITELLM_API_KEY")
            or os.environ.get("LITELLM_MASTER_KEY")
        )
        print(f"  TEAM360_LITELLM_BASE_URL configured: {bool(os.environ.get('TEAM360_LITELLM_BASE_URL'))}")
        print(f"  TEAM360_LITELLM_MODEL_ALIAS: {model_alias or 'openai_gpt-5-nano (default)'}")
        print(f"  LiteLLM API key configured: {has_key}")
    if provider_config["llm_provider"] == "openai":
        print(f"  OpenAI API key configured: {_has_llm_config('openai')}")


def _print_debug_request(
    *,
    case: dict[str, Any],
    payload: dict[str, Any],
    url: str,
    timeout: float,
) -> None:
    print("Request debug:")
    print("  method: POST")
    print(f"  url: {url}")
    print("  headers: Content-Type=application/json")
    print("  auth headers: none sent by evaluator")
    print(f"  timeout_seconds: {timeout}")
    print(f"  case_id: {case['id']}")
    print(f"  session_id: {payload['session_id']}")
    print(f"  message: {_truncate(case['question'], 160)}")
    print(f"  metadata: {json.dumps(payload.get('metadata', {}), ensure_ascii=False, sort_keys=True)}")


def _print_events(body: dict[str, Any], *, provider_only: bool) -> None:
    events = body.get("events")
    if not isinstance(events, list):
        print("  events: <missing or invalid>")
        return
    label = "Provider events" if provider_only else "Events"
    print(f"{label}:")
    matched = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if provider_only and event.get("event_type") != "team360.llm.provider_result":
            continue
        matched += 1
        print(f"  {json.dumps(_sanitize_event(event), ensure_ascii=False, sort_keys=True)}")
    if matched == 0:
        print("  -")


def _print_summary(summary: RunSummary) -> None:
    print()
    print(f"Total cases: {summary.total}")
    print(f"PASS: {summary.pass_count}")
    print(f"WARN: {summary.warn_count}")
    print(f"FAIL: {summary.fail_count}")
    print(f"SKIP: {summary.skip_count}")


def _run(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = (Path.cwd() / dataset_path).resolve()

    try:
        dataset = _load_dataset(dataset_path)
    except Exception as exc:
        print(f"SKIP: could not load dataset: {type(exc).__name__}: {exc}")
        return 0

    endpoint_path, endpoint_mode = _resolve_request_mode(args.endpoint)
    provider_config = _resolve_provider_config(endpoint_mode)
    should_skip, skip_reason = _needs_skip(endpoint_mode, provider_config)

    print("=== Sales Diagnosis Headless Response Validation ===")
    print(f"Base URL: {args.base_url}")
    print(f"Endpoint: {endpoint_mode} -> {endpoint_path}")
    print(f"Dataset: {dataset_path}")
    print(f"Dataset suite: {dataset.get('test_suite')}")
    print(f"Allow fallback: {args.allow_fallback}")
    print(f"Fail on fallback: {args.fail_on_fallback}")
    print(f"Fail on warn: {args.fail_on_warn}")
    print(f"Require real LLM: {args.require_real_llm}")
    print(f"Verbose: {args.verbose}")
    print(f"Single case: {args.single_case or '-'}")
    _print_provider_config(provider_config)
    print()

    if args.require_real_llm and not provider_config["real_llm_expected"]:
        print("FAIL: --require-real-llm was set, but client env selects a non-real LLM provider.")
        print(f"LLM provider: {provider_config['llm_provider']}")
        return 1

    if should_skip:
        print("SKIP: endpoint/provider mode is not ready.")
        print(f"Reason: {skip_reason}")
        print("Result: SKIPPED (not a failure)")
        return 0

    cases = dataset["cases"]
    if args.single_case:
        cases = [case for case in cases if case.get("id") == args.single_case]
        if not cases:
            print(f"FAIL: --single-case {args.single_case!r} was not found in dataset.")
            return 1

    summary = RunSummary(total=len(cases))
    any_fail = False
    any_warn = False

    for case in cases:
        session_id = f"headless_{case['id']}_{uuid4().hex[:10]}"
        payload = _build_payload(case, session_id, endpoint_mode)
        url = f"{args.base_url}{endpoint_path}"
        if args.debug_request:
            _print_debug_request(
                case=case,
                payload=payload,
                url=url,
                timeout=args.timeout,
            )
            print()
        try:
            status_code, body = _request_json("POST", url, payload, timeout=args.timeout)
        except ConnectionError as exc:
            print("SKIP: backend endpoint is not reachable.")
            print(f"Reason: {exc}")
            print("Result: SKIPPED (not a failure)")
            return 0
        except Exception as exc:
            print(f"FAIL: unexpected request error: {type(exc).__name__}: {exc}")
            return 1

        if status_code != 201:
            print("FAIL: endpoint returned an error instead of 201.")
            print(f"Status: {status_code}")
            print(f"Body: {_truncate(str(body))}")
            return 1

        if not isinstance(body, dict):
            print("FAIL: response body is not a JSON object.")
            print(f"Body: {_truncate(str(body))}")
            return 1

        result = _evaluate_case(
            case,
            body,
            endpoint=endpoint_mode,
            provider_config=provider_config,
            allow_fallback=args.allow_fallback,
            fail_on_fallback=args.fail_on_fallback,
            require_real_llm=args.require_real_llm,
        )
        if result.status == "PASS":
            summary.pass_count += 1
        elif result.status == "WARN":
            summary.warn_count += 1
            any_warn = True
        else:
            summary.fail_count += 1
            any_fail = True
        _print_case_result(result, args.verbose)
        if args.print_events:
            _print_events(body, provider_only=False)
        elif args.dump_provider_events:
            _print_events(body, provider_only=True)
        print()

    _print_summary(summary)

    if any_fail:
        return 1
    if any_warn and args.fail_on_warn:
        return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Headless semantic evaluator for Sales Diagnosis responses."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BACKEND_URL,
        help="Backend base URL (default: http://127.0.0.1:8018).",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help="Path to the JSON dataset with headless questions.",
    )
    parser.add_argument(
        "--endpoint",
        choices=("product", "dev"),
        default="product",
        help="Select product adapter or dev endpoint.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Return exit code 1 if any case is WARN.",
    )
    parser.add_argument(
        "--fail-on-fallback",
        action="store_true",
        help=(
            "Return FAIL when provider_result response_is_fallback=true. "
            "Does not treat guardrail fallback_applied as provider fallback."
        ),
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Do not fail when a real LLM mode falls back to a safe ack.",
    )
    parser.add_argument(
        "--require-real-llm",
        action="store_true",
        help=(
            "Require a real LLM provider in client env and a provider_result event "
            "in each response; useful to detect a backend started with old envs."
        ),
    )
    parser.add_argument(
        "--single-case",
        help="Run only one dataset case by id.",
    )
    parser.add_argument(
        "--debug-request",
        action="store_true",
        help="Print endpoint, sanitized request body metadata and timeout per case.",
    )
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Print sanitized runtime events for each response.",
    )
    parser.add_argument(
        "--dump-provider-events",
        action="store_true",
        help="Print only sanitized team360.llm.provider_result events.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print matched claims per case.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
