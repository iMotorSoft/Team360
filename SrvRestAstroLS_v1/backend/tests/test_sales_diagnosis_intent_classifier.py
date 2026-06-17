"""Tests for sales diagnosis intent classifier.

Covers:
- High-confidence rules (fast path, no AI)
- Objective expressed vs diagnosis request (Point 3)
- Stop interview vs policy rejection (Point 4)
- Real correction vs vague mention (Point 5)
- Factual answers without AI (Point 7)
- Classifier fallback (Point 12)
- Multi-language (es, en, he)

No network calls. No DB. No LLM.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime.intent_classifier import (
    CLASSIFIER_CONFIDENCE_MODERATE,
    CLASSIFIER_CONFIDENCE_STRONG,
    HIGH_CONFIDENCE_RULES,
    IntentClassification,
    IntentClassifier,
    IntentScope,
    IntentSource,
    IntentStateSummary,
    IntentType,
    LiteLLMIntentClassifier,
    NullIntentClassifier,
    is_clear_factual_answer,
    match_high_confidence,
    parse_classifier_response,
)


# ── Deterministic fake classifier for route injection tests ──────────────

class RecordingIntentClassifier:
    """Records calls and returns a known classification."""

    def __init__(self, intent: IntentType = IntentType.PROVIDE_INFORMATION,
                 scope: IntentScope = IntentScope.NOT_APPLICABLE,
                 confidence: float = 0.95) -> None:
        self.calls: list[tuple[str, IntentStateSummary]] = []
        self._intent = intent
        self._scope = scope
        self._confidence = confidence

    def classify(self, message: str, state_summary: IntentStateSummary) -> IntentClassification:
        self.calls.append((message, state_summary))
        return IntentClassification(
            intent=self._intent,
            scope=self._scope,
            confidence=self._confidence,
            source=IntentSource.AI_CLASSIFIER,
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def called(self) -> bool:
        return len(self.calls) > 0


# ── Summary builder helper ─────────────────────────────────────────────

def _summary(**overrides: int | bool | str) -> IntentStateSummary:
    defaults: dict = {
        "diagnosis_status": "gathering",
        "has_process": False,
        "has_channels": False,
        "has_systems": False,
        "has_human_approval": False,
        "has_volume": False,
        "turn_count": 1,
        "last_question_intent": "",
        "current_language": "es",
    }
    defaults.update(overrides)
    return IntentStateSummary(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# 1. High-confidence rules (fast path, no AI call)
# ═══════════════════════════════════════════════════════════════════════

class TestHighConfidenceRules:
    def _check(self, message: str, expected_intent: IntentType) -> None:
        result = match_high_confidence(message)
        assert result is not None, f"Expected match for: {message!r}"
        assert result.intent == expected_intent, (
            f"Expected {expected_intent.value}, got {result.intent.value} for {message!r}"
        )
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE
        assert result.matched_rule is not None

    def _no_match(self, message: str) -> None:
        result = match_high_confidence(message)
        assert result is None, (
            f"Expected no match for {message!r}, got {result!r}"
        )

    # --- request_diagnosis ---
    @pytest.mark.parametrize("msg", [
        "dame el diagnóstico",
        "dame un diagnóstico",
        "Dame el diagnóstico",
        "dame una orientación",
        "dame una orientación inicial",
        "cerrá con una recomendación",
        "cerra con recomendación",
        "qué harías primero",
        "qué conviene con todo esto",
        "con esto ya está",
        "con lo que te dije alcanza",
        "con lo que te dije quiero",
        "con esto empecemos",
        "podés decirme si se puede",
        "podés decirme qué harías",
        "give me a diagnosis",
        "give me an assessment",
        "what would you do",
        "tell me if this can be automated",
        "tell me what to do first",
        "is this sufficient",
        "tell me what you would do",
        "תן לי אבחון",
        "תני לי הערכה",
        "מה אתה ממליץ",
    ])
    def test_request_diagnosis_matches(self, msg: str) -> None:
        self._check(msg, IntentType.REQUEST_DIAGNOSIS)

    # --- provide_information (expressions of automation intent) ---
    @pytest.mark.parametrize("msg", [
        "quiero automatizar las consultas de venta",
        "quiero mejorar el proceso",
        "quiero optimizar la atención",
        "quiero digitalizar los formularios",
        "necesito automatizar ventas",
        "necesito mejorar los tiempos",
        "buscamos automatizar respuestas",
        "necesitamos simplificar el proceso",
        "quiero ordenar las consultas",
        "quiero agilizar la atención",
        "queremos automatizar todo",
        "vamos a automatizar ventas",
        "i want to automate customer inquiries",
        "i need to improve our process",
        "we need to automate everything",
        "we're looking to digitize forms",
        "i want to simplify operations",
        "אני רוצה אוטומציה",
        "אני רוצה לייעל",
        "אני צריך לשפר",
        "no quiero responder ese mensaje",
        "no quiero responder ese mensaje automáticamente",
        "i don't want to respond that message automatically",
    ])
    def test_provide_information_matches(self, msg: str) -> None:
        self._check(msg, IntentType.PROVIDE_INFORMATION)

    # --- stop_interview ---
    @pytest.mark.parametrize("msg", [
        "no quiero seguir respondiendo",
        "no quiero continuar",
        "no quiero contestar más",
        "i don't want to continue",
        "i don't want to answer more",
        "i don't want to answer anymore",
        "אני לא רוצה להמשיך",
        "אני לא רוצה לענות יותר",
    ])
    def test_stop_interview_matches(self, msg: str) -> None:
        self._check(msg, IntentType.STOP_INTERVIEW)

    # --- provide_information - "no quiero responder ese mensaje" must NOT be stop_interview ---
    @pytest.mark.parametrize("msg", [
        "no quiero responder ese mensaje automáticamente",
        "No quiero responder ese mensaje",
        "I don't want to respond that message",
    ])
    def test_policy_rejection_not_stop_interview(self, msg: str) -> None:
        """'No quiero responder ese mensaje' is provide_information, not stop_interview."""
        result = match_high_confidence(msg)
        assert result is not None
        assert result.intent == IntentType.PROVIDE_INFORMATION, (
            f"Expected provide_information for {msg!r}, got {result.intent.value}"
        )

    # --- correct_previous_information ---
    @pytest.mark.parametrize("msg", [
        "mejor dicho, son 120",
        "rectifico, son 120",
        "rectificamos los datos",
        "actually i meant 120",
        "correction: it's 120",
        "let me correct that",
        "בעצם 120",
        "אני מתקן",
    ])
    def test_correction_matches(self, msg: str) -> None:
        self._check(msg, IntentType.CORRECT_PREVIOUS_INFORMATION)

    # --- Non-matches ---
    @pytest.mark.parametrize("msg", [
        "hola",
        "Hola",
        "hi",
        "שלום",
        "ok",
        "sí",
        "si",
        "no",
        "yes",
        "Quiero saber si es viable",
        "¿Podés decirme si Gmail se puede conectar?",
        "¿Qué conviene usar para leer una planilla?",
        "Con lo que te dije de Gmail, ¿se puede responder solo?",
        "El diagnóstico que me mandaron antes estaba incompleto.",
        "Antes dije 80, pero en realidad son 120.",
        "En realidad usamos Outlook, no Gmail.",
        "Tell me if Gmail can be connected",
    ])
    def test_no_match_cases(self, msg: str) -> None:
        self._no_match(msg)


# ═══════════════════════════════════════════════════════════════════════
# 2. Objective expressed vs diagnosis request (Point 3)
# ═══════════════════════════════════════════════════════════════════════

class TestObjectiveVsDiagnosisRequest:
    """Distinguishing 'I want to automate X' from 'Tell me if I should automate X'."""

    # These should match high-confidence provide_information rules
    @pytest.mark.parametrize("msg", [
        "quiero automatizar las consultas de venta",
        "Quiero automatizar el proceso de ventas",
        "quiero mejorar la gestión de leads",
        "necesito automatizar respuestas de clientes",
        "buscamos automatizar el seguimiento",
        "i want to automate customer inquiries",
        "i need to improve our response time",
        "we need to automate sales follow-up",
    ])
    def test_objective_expression_provide_information(self, msg: str) -> None:
        result = match_high_confidence(msg)
        assert result is not None
        assert result.intent == IntentType.PROVIDE_INFORMATION

    # These should be passed to AI or handled by other rules
    @pytest.mark.parametrize("msg", [
        "Quiero que me digas si conviene automatizar las consultas",
        "Decime si conviene automatizar",
        "Can you assess whether I should automate customer inquiries?",
        "¿Qué conviene automatizar?",
    ])
    def test_diagnosis_request_not_matched_high_confidence(self, msg: str) -> None:
        """These require AI or are explicit diagnosis requests."""
        result = match_high_confidence(msg)
        # These may match other rules (e.g., request_diagnosis_es_04)
        if result is None:
            return
        # If matched, it should NOT be provide_information
        assert result.intent != IntentType.PROVIDE_INFORMATION, (
            f"{msg!r} should not be provide_information, got {result!r}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 3. Stop interview vs policy rejection (Point 4)
# ═══════════════════════════════════════════════════════════════════════

class TestStopVsPolicyRejection:
    @pytest.mark.parametrize("msg,expected", [
        ("No quiero seguir respondiendo preguntas.", IntentType.STOP_INTERVIEW),
        ("No quiero contestar más.", IntentType.STOP_INTERVIEW),
        ("i don't want to continue.", IntentType.STOP_INTERVIEW),
        ("I don't want to answer anymore.", IntentType.STOP_INTERVIEW),
        ("No quiero responder ese mensaje automáticamente.", IntentType.PROVIDE_INFORMATION),
        ("No quiero responder ese mensaje.", IntentType.PROVIDE_INFORMATION),
        ("I don't want to respond that message automatically.", IntentType.PROVIDE_INFORMATION),
        ("¿Conviene responder ese mensaje automáticamente?", None),
    ])
    def test_classification(self, msg: str, expected: IntentType | None) -> None:
        result = match_high_confidence(msg)
        if expected is None:
            assert result is None, f"Expected no match for {msg!r}, got {result!r}"
        else:
            assert result is not None, f"Expected match for {msg!r}"
            assert result.intent == expected, (
                f"Expected {expected.value}, got {result.intent.value} for {msg!r}"
            )


# ═══════════════════════════════════════════════════════════════════════
# 4. Real correction vs vague mention (Point 5)
# ═══════════════════════════════════════════════════════════════════════

class TestCorrectionVsVague:
    """Only explicit fact corrections should be CORRECT_PREVIOUS_INFORMATION."""

    # These ARE explicit corrections (high-confidence rules)
    @pytest.mark.parametrize("msg", [
        "mejor dicho, son 120",
        "rectifico, son 120",
        "actually i meant 120",
        "correction: it's 120",
        "let me correct that",
        "בעצם 120",
        "אני מתקן",
    ])
    def test_explicit_correction(self, msg: str) -> None:
        result = match_high_confidence(msg)
        assert result is not None
        assert result.intent == IntentType.CORRECT_PREVIOUS_INFORMATION

    # These are NOT corrections - they need AI or fallback
    @pytest.mark.parametrize("msg", [
        "El diagnóstico que me mandaron antes estaba incompleto.",
        "El diagnóstico anterior estaba incompleto.",
        "La información que dí antes no era correcta.",
        "Los datos que mandé están mal.",
    ])
    def test_vague_mention_not_correction(self, msg: str) -> None:
        """Vague mentions of incompleteness or wrongness are not corrections."""
        result = match_high_confidence(msg)
        assert result is None or result.intent != IntentType.CORRECT_PREVIOUS_INFORMATION, (
            f"Vague mention {msg!r} should not be correction, got {result!r}"
        )

    # These ARE real corrections (with specific fact contradictions)
    @pytest.mark.parametrize("msg", [
        "En realidad no son 80, son 120.",
        "Antes dije Gmail, pero usamos Outlook.",
        "Los descuentos también necesitan aprobación.",
    ])
    def test_real_correction_with_specifics(self, msg: str) -> None:
        """These contain specific fact contradictions, but use 'en realidad' pattern
        which is NO LONGER in high-confidence rules (was too broad)."""
        result = match_high_confidence(msg)
        # These use 'en realidad' which we removed from correction rules
        # They should fall to AI classifier
        assert result is None or result.intent != IntentType.CORRECT_PREVIOUS_INFORMATION, (
            f"Expected no high-confidence correction for {msg!r}, got {result!r}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 5. Factual answers without AI (Point 7)
# ═══════════════════════════════════════════════════════════════════════

class TestFactualAnswerDetection:
    @pytest.mark.parametrize("msg,expected", [
        ("80", True),
        ("80 por día", True),
        ("120", True),
        ("unos 80", False),
        ("Sí", True),
        ("sí", True),
        ("No", True),
        ("no", True),
        ("WhatsApp", True),
        ("Gmail", True),
        ("whatsapp", True),
        ("email", True),
        ("sistema", True),
        ("planilla", True),
        ("excel", True),
        ("hola", False),
        ("Quiero automatizar", False),
        ("Dame el diagnóstico", False),
        ("Usamos Gmail y WhatsApp", False),
    ])
    def test_is_clear_factual_answer(self, msg: str, expected: bool) -> None:
        assert is_clear_factual_answer(msg) == expected, (
            f"is_clear_factual_answer({msg!r}) should be {expected}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 6. Classifier fallback (Point 12)
# ═══════════════════════════════════════════════════════════════════════

class TestParseClassifierResponse:
    def test_valid_response(self) -> None:
        raw = '{"intent": "provide_information", "scope": "not_applicable", "confidence": 0.92}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.scope == IntentScope.NOT_APPLICABLE
        assert result.confidence == 0.92
        assert result.source == IntentSource.AI_CLASSIFIER

    def test_valid_request_diagnosis(self) -> None:
        raw = '{"intent": "request_diagnosis", "scope": "global", "confidence": 0.88}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.REQUEST_DIAGNOSIS
        assert result.scope == IntentScope.GLOBAL
        assert result.confidence == 0.88

    def test_valid_point_question(self) -> None:
        raw = '{"intent": "ask_point_question", "scope": "point_question", "confidence": 0.75}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.ASK_POINT_QUESTION
        assert result.scope == IntentScope.POINT_QUESTION

    def test_valid_stop_interview(self) -> None:
        raw = '{"intent": "stop_interview", "scope": "global", "confidence": 0.95}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.STOP_INTERVIEW

    def test_valid_correction(self) -> None:
        raw = '{"intent": "correct_previous_information", "scope": "not_applicable", "confidence": 0.9}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.CORRECT_PREVIOUS_INFORMATION

    def test_invalid_json_fallback(self) -> None:
        result = parse_classifier_response("not json")
        assert result.intent == IntentType.UNCLEAR
        assert result.source == IntentSource.RUNTIME_FALLBACK

    def test_unknown_intent_fallback(self) -> None:
        raw = '{"intent": "unknown_intent", "scope": "not_applicable", "confidence": 0.9}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.UNCLEAR
        assert result.source == IntentSource.AI_CLASSIFIER

    def test_invalid_scope_fallback(self) -> None:
        raw = '{"intent": "provide_information", "scope": "invalid_scope", "confidence": 0.9}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.scope == IntentScope.NOT_APPLICABLE

    def test_invalid_confidence_clamped(self) -> None:
        raw = '{"intent": "unclear", "scope": "not_applicable", "confidence": 99.0}'
        result = parse_classifier_response(raw)
        assert result.confidence == 1.0

    def test_negative_confidence_clamped(self) -> None:
        raw = '{"intent": "unclear", "scope": "not_applicable", "confidence": -5.0}'
        result = parse_classifier_response(raw)
        assert result.confidence == 0.0

    def test_empty_response_fallback(self) -> None:
        result = parse_classifier_response("")
        assert result.intent == IntentType.UNCLEAR
        assert result.source == IntentSource.RUNTIME_FALLBACK

    def test_missing_fields(self) -> None:
        raw = '{}'
        result = parse_classifier_response(raw)
        assert result.intent == IntentType.UNCLEAR
        assert result.confidence == 0.0


# ═══════════════════════════════════════════════════════════════════════
# 7. NullIntentClassifier (safety fallback)
# ═══════════════════════════════════════════════════════════════════════

class TestNullIntentClassifier:
    def test_null_returns_fallback(self) -> None:
        classifier = NullIntentClassifier()
        result = classifier.classify("test message", _summary())
        assert result.intent == IntentType.UNCLEAR
        assert result.source == IntentSource.RUNTIME_FALLBACK
        assert result.confidence == 0.0

    def test_null_no_side_effects(self) -> None:
        classifier = NullIntentClassifier()
        result1 = classifier.classify("msg1", _summary())
        result2 = classifier.classify("msg2", _summary())
        assert result1.intent == IntentType.UNCLEAR
        assert result2.intent == IntentType.UNCLEAR

    def test_null_never_triggers_diagnose(self) -> None:
        """Null classifier should never request_diagnose."""
        classifier = NullIntentClassifier()
        result = classifier.classify("dame el diagnóstico", _summary())
        assert result.intent != IntentType.REQUEST_DIAGNOSIS


# ═══════════════════════════════════════════════════════════════════════
# 8. RecordingIntentClassifier (for route injection tests)
# ═══════════════════════════════════════════════════════════════════════

class TestRecordingIntentClassifier:
    def test_records_call(self) -> None:
        classifier = RecordingIntentClassifier()
        result = classifier.classify("test", _summary())
        assert classifier.called
        assert classifier.call_count == 1
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.source == IntentSource.AI_CLASSIFIER

    def test_records_multiple_calls(self) -> None:
        classifier = RecordingIntentClassifier()
        classifier.classify("msg1", _summary(turn_count=1))
        classifier.classify("msg2", _summary(turn_count=2))
        assert classifier.call_count == 2
        msg1, sum1 = classifier.calls[0]
        msg2, sum2 = classifier.calls[1]
        assert msg1 == "msg1"
        assert msg2 == "msg2"
        assert sum1.turn_count == 1
        assert sum2.turn_count == 2

    def test_custom_return(self) -> None:
        classifier = RecordingIntentClassifier(
            intent=IntentType.ASK_POINT_QUESTION,
            scope=IntentScope.POINT_QUESTION,
            confidence=0.8,
        )
        result = classifier.classify("test", _summary())
        assert result.intent == IntentType.ASK_POINT_QUESTION
        assert result.scope == IntentScope.POINT_QUESTION
        assert result.confidence == 0.8


# ═══════════════════════════════════════════════════════════════════════
# 9. Edge cases and boundary behaviors
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_message(self) -> None:
        assert match_high_confidence("") is None

    def test_whitespace_message(self) -> None:
        assert match_high_confidence("   ") is None

    def test_special_characters(self) -> None:
        assert match_high_confidence("¿?¡!") is None

    def test_factual_empty(self) -> None:
        assert is_clear_factual_answer("") is False

    def test_factual_whitespace(self) -> None:
        assert is_clear_factual_answer("  ") is False

    def test_factual_numbers_with_context(self) -> None:
        assert is_clear_factual_answer("80 consultas por día") is False
        assert is_clear_factual_answer("Son 80") is False


# ═══════════════════════════════════════════════════════════════════════
# 10. Meta: verify rule count and coverage
# ═══════════════════════════════════════════════════════════════════════

def _rule_lang(rule_id: str) -> str:
    """Extract language code from rule ID like 'request_diagnosis_es_01'."""
    parts = rule_id.split("_")
    for candidate in parts:
        if candidate in ("es", "en", "he"):
            return candidate
    return ""


class TestRuleCoverage:
    def test_high_confidence_rules_have_all_fields(self) -> None:
        """Meta-test: every rule must have id, intent, scope, pattern."""
        for rule in HIGH_CONFIDENCE_RULES:
            assert "id" in rule, f"Rule missing id: {rule}"
            assert "intent" in rule, f"Rule {rule['id']} missing intent"
            assert "scope" in rule, f"Rule {rule['id']} missing scope"
            assert "pattern" in rule, f"Rule {rule['id']} missing pattern"
            assert isinstance(rule["pattern"], type(re.compile(""))), (
                f"Rule {rule['id']} pattern not compiled"
            )

    def test_all_intents_have_at_least_one_rule(self) -> None:
        """Every IntentType (except ask_point_question, unclear) should have
        at least one high-confidence rule. ask_point_question is intentionally
        handled by the AI classifier due to its subtle distinction from
        request_diagnosis."""
        skip = {IntentType.ASK_POINT_QUESTION, IntentType.UNCLEAR}
        covered: set[str] = {r["intent"].value for r in HIGH_CONFIDENCE_RULES}
        for intent in IntentType:
            if intent in skip:
                continue
            assert intent.value in covered, (
                f"IntentType.{intent.name} ({intent.value}) has no high-confidence rule"
            )

    def test_all_languages_have_request_diagnosis(self) -> None:
        langs_found: set[str] = set()
        for r in HIGH_CONFIDENCE_RULES:
            if r["intent"] == IntentType.REQUEST_DIAGNOSIS:
                lang = _rule_lang(r["id"])
                if lang:
                    langs_found.add(lang)
        for lang in ("es", "en", "he"):
            assert lang in langs_found, f"No request_diagnosis rule for {lang}"

    def test_all_languages_have_stop_interview(self) -> None:
        langs_found: set[str] = set()
        for r in HIGH_CONFIDENCE_RULES:
            if r["intent"] == IntentType.STOP_INTERVIEW:
                lang = _rule_lang(r["id"])
                if lang:
                    langs_found.add(lang)
        for lang in ("es", "en", "he"):
            assert lang in langs_found, f"No stop_interview rule for {lang}"

    def test_provide_information_not_asking_diagnosis(self) -> None:
        """Expressions like 'quiero automatizar' must NOT collide with request_diagnosis."""
        for r in HIGH_CONFIDENCE_RULES:
            if r["intent"] == IntentType.PROVIDE_INFORMATION and "_a0" in r["id"]:
                msg = r["id"]
                # Verify the pattern doesn't match "dame" or "decime"
                assert not r["pattern"].search("dame el diagnóstico"), (
                    f"Rule {msg} incorrectly matches 'dame el diagnóstico'"
                )


# ═══════════════════════════════════════════════════════════════════════
# 11. LiteLLMIntentClassifier integration (no real network)
# ═══════════════════════════════════════════════════════════════════════

class TestLiteLLMIntentClassifierNoNetwork:
    def test_high_confidence_shortcut_no_network(self) -> None:
        """Messages matching high-confidence rules should NOT call the LLM."""
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("dame el diagnóstico", _summary())
        assert result.intent == IntentType.REQUEST_DIAGNOSIS
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_high_confidence_provide_info_no_network(self) -> None:
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("quiero automatizar las consultas", _summary())
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_high_confidence_stop_no_network(self) -> None:
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("no quiero seguir respondiendo", _summary())
        assert result.intent == IntentType.STOP_INTERVIEW
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_factual_answer_no_network(self) -> None:
        """Factual short answers should NOT call the LLM."""
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("80 por día", _summary())
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_factual_yes_no_network(self) -> None:
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("sí", _summary())
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_factual_channel_no_network(self) -> None:
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify("WhatsApp", _summary())
        assert result.intent == IntentType.PROVIDE_INFORMATION
        assert result.source == IntentSource.HIGH_CONFIDENCE_RULE

    def test_classifier_fallback_on_timeout(self, monkeypatch) -> None:
        """Simulate a failed AI call and verify runtime_fallback.
        Uses a message that doesn't match any high-confidence rule."""
        def _fail(*args, **kwargs):
            raise RuntimeError("connection timeout")

        monkeypatch.setattr(
            "modules.automation_diagnosis.litellm_client.LiteLLMClient.chat_completion",
            _fail,
        )
        classifier = LiteLLMIntentClassifier()
        result = classifier.classify(
            "We want to centralize all our customer inquiries into one system",
            _summary()
        )
        assert result.intent == IntentType.UNCLEAR
        assert result.source == IntentSource.RUNTIME_FALLBACK
