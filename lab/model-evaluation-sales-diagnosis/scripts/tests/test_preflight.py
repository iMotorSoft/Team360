"""Unit tests for preflight_model_evaluation.py (pure logic only, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent dir (scripts/) to sys.path so preflight_module is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import preflight_model_evaluation as preflight  # noqa: E402


def test_direct_check_result_defaults():
    result = preflight.DirectCheckResult(alias="test_alias", status="PASS")
    assert result.alias == "test_alias"
    assert result.status == "PASS"
    assert result.content_length == 0
    assert result.finish_reason == ""
    assert result.latency_ms == 0
    assert result.error == ""


def test_backend_check_result_defaults():
    result = preflight.BackendCheckResult(status="PASS")
    assert result.status == "PASS"
    assert result.response_is_fallback is True
    assert result.model_alias == ""
    assert result.response_text_length == 0
    assert result.source_count == 0


def test_redact_sk_like_patterns():
    assert "sk-<redacted>" in preflight._redact("sk-test12345")
    assert "sk-" not in preflight._redact("Bearer sk-test12345")
    assert "<redacted>" in preflight._redact("Bearer sk-test12345")


def test_redact_postgres_dsn():
    raw = "postgresql://user:secret@localhost:5432/db"
    result = preflight._redact(raw)
    assert "secret" not in result
    assert "<redacted>" in result


def test_redact_does_not_leak_litellm_key():
    raw = "key=sk-litellm-secret-key-here"
    result = preflight._redact(raw)
    assert "sk-litellm-secret-key-here" not in result
    assert "sk-<redacted>" in result


def test_resolve_aliases_default():
    aliases = preflight._resolve_aliases(None)
    assert "openai_gpt-5-nano" in aliases
    assert "openai_gpt_4o_mini_2024_07_18" in aliases
    assert "openrouter_qwen3_30b_a3b_thinking_2507" in aliases
    assert "openrouter_deepseek_4_flash" in aliases
    assert "requesty_deepseek_4_flash" in aliases
    assert len(aliases) == 5


def test_resolve_aliases_custom():
    aliases = preflight._resolve_aliases("model_a,model_b")
    assert aliases == ["model_a", "model_b"]


def test_resolve_aliases_single():
    aliases = preflight._resolve_aliases("only_one")
    assert aliases == ["only_one"]


def test_redact_no_change_for_safe_text():
    safe = "just regular text with no secrets"
    assert preflight._redact(safe) == safe


def test_build_turn_request_has_expected_keys():
    req = preflight._build_turn_request()
    assert req["session_id"] == "preflight_check_001"
    assert "message" in req
    assert req["assistant_instance_code"] == "team360_sales_diagnosis"
    assert req["package_code"] == "pkg_sales_diagnosis"
    assert req["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
    assert req["metadata"]["source"] == "preflight_check"
