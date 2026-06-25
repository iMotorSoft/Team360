import json
from pathlib import Path

import pytest

from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
from modules.automation_diagnosis.assistant_instances import get_assistant_instance_config
from modules.automation_diagnosis.answer_collector import normalize_answer
from modules.automation_diagnosis.chunker import chunk_document
from modules.automation_diagnosis.document_loader import default_knowledge_scope
from modules.automation_diagnosis.knowledge_connector import build_default_knowledge_repository
from modules.automation_diagnosis.schemas import KnowledgeDocument
from modules.automation_diagnosis.service import AutomationDiagnosisService


FIXTURES = Path(__file__).resolve().parents[1] / "modules" / "automation_diagnosis" / "fixtures" / "sessions"


def build_service():
    return AutomationDiagnosisService(ai_interpreter=MockAIInterpreter())


def run_fixture(name):
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    service = build_service()
    started = service.start_session(payload)
    session_id = started["id"]
    for answer in payload["answers"]:
        service.save_answer(session_id, answer)
    return service.classify(session_id)


def direct_sales_payload(fixture_name="standard_package"):
    payload = json.loads((FIXTURES / f"{fixture_name}.json").read_text())
    for key in ("workspace_id", "assistant_instance_id", "automation_package_id", "knowledge_scope_id"):
        payload.pop(key, None)
    payload["source_url"] = "https://team360.live"
    payload["locale"] = "es"
    payload["visitor"] = {"source": "public_site"}
    return payload


def test_default_session_uses_team360_direct_package_installation():
    service = build_service()
    started = service.start_session({"source_url": "https://team360.live", "locale": "es"})

    assert started["organization_id"] == "org_team360"
    assert started["workspace_id"] == "team360_public_site"
    assert started["assistant_instance_id"] == "team360_sales_diagnosis"
    assert started["assistant_display_name"] == "Vera"
    assert started["automation_package_id"] == "pkg_sales_diagnosis"
    assert started["knowledge_scope_id"] == "ks_team360_sales_diagnosis"
    assert started["site_channel"] == "team360.live"
    assert started["lead_owner"] == "Team360"
    assert started["locale"] == "es"
    assert "pw_team360_lead_qualification" in started["package_worker_ids"]
    assert started["cost_attribution"]["cost_center"] == "team360_direct_sales"

    event = started["events"][0]
    assert event["organization_id"] == "org_team360"
    assert event["site_channel"] == "team360.live"
    assert event["payload"]["package_worker_ids"] == started["package_worker_ids"]


def test_team360_direct_classification_preserves_customer_attribution():
    payload = direct_sales_payload()
    service = build_service()
    started = service.start_session(payload)
    session_id = started["id"]
    for answer in payload["answers"]:
        service.save_answer(session_id, answer)

    result = service.classify(session_id)
    card = result["internal_card"]

    assert result["retrieved_context"]["knowledge_scope_id"] == "ks_team360_sales_diagnosis"
    assert card["organization_id"] == "org_team360"
    assert card["workspace_id"] == "team360_public_site"
    assert card["assistant_instance_id"] == "team360_sales_diagnosis"
    assert card["automation_package_id"] == "pkg_sales_diagnosis"
    assert card["knowledge_scope_id"] == "ks_team360_sales_diagnosis"
    assert card["site_channel"] == "team360.live"
    assert card["lead_owner"] == "Team360"
    assert card["locale"] == "es"
    assert card["cost_attribution"]["cost_center"] == "team360_direct_sales"
    assert "pw_team360_package_recommendation" in card["package_worker_ids"]


def test_start_session_rejects_scope_override_that_does_not_match_assistant_instance():
    service = build_service()
    with pytest.raises(ValueError, match="knowledge_scope_id"):
        service.start_session(
            {
                "assistant_instance_id": "team360_sales_diagnosis",
                "knowledge_scope_id": "ks_team360_automation_diagnosis",
            }
        )


def test_team360_direct_config_documents_arangodb_and_milvus_scope_rules():
    config = get_assistant_instance_config("team360_sales_diagnosis")

    assert config.arangodb_scope["physical_collection_per_customer"] is False
    assert "diagnosis_vertices" in config.arangodb_scope["collections"]
    assert "knowledge_scope_id" in config.arangodb_scope["scope_filter_fields"]
    assert config.milvus_scope["collection"] == "team360_diagnosis_chunks"
    assert "assistant_instance_id" in config.milvus_scope["required_filter_fields"]


def test_normalize_answer_rejects_unknown_step():
    with pytest.raises(ValueError):
        normalize_answer("missing", {"free_text": "x"})


def test_chunk_document_splits_markdown_sections():
    scope = default_knowledge_scope()
    document = KnowledgeDocument(
        id="doc_1",
        knowledge_scope_id=scope.id,
        title="Test",
        source_path="memory",
        content="# Uno\n\nTexto A\n\n## Dos\n\nTexto B",
    )
    chunks = chunk_document(document, max_chars=50)
    assert len(chunks) == 2
    assert chunks[0].title == "Uno"
    assert chunks[1].title == "Dos"


def test_default_knowledge_repository_retrieves_mfa_context():
    repository = build_default_knowledge_repository()
    result = repository.search(
        "ks_team360_automation_diagnosis",
        "MFA FaceID hardware no bypass seguridad",
        "rag",
        top_k=3,
    )
    assert result.chunks
    assert any("seguridad" in chunk["content"].lower() or "mfa" in chunk["content"].lower() for chunk in result.chunks)


def test_standard_package_fixture_classification():
    result = run_fixture("standard_package")
    assert result["classification"] == "standard_package"
    assert result["recommended_package_type"] == "team360_standard_automation"
    assert result["required_package_worker_config"]["future_external_worker_ready"] is True


def test_operational_automation_fixture_classification():
    result = run_fixture("operational_automation")
    assert result["classification"] == "operational_automation"
    assert result["automation_mode"] == "assisted"
    assert "erp_connector_or_rpa_worker" in result["suggested_worker_definitions"]
    assert result["required_knowledge_scope"]["retrieval_mode"] == "rag"


def test_consulting_required_fixture_classification():
    result = run_fixture("consulting_required")
    assert result["classification"] == "consulting_required"
    assert result["requires_human_approval"] is True
    assert "high_human_dependency" in result["risk_flags"]


def test_not_recommended_fixture_classification():
    result = run_fixture("not_recommended")
    assert result["classification"] == "not_recommended"
    assert result["automation_mode"] == "blocked"
    assert "bypass_mfa" in result["blocked_actions"]
    assert "hard_security_stop" in result["risk_flags"]


class TestAssistantDisplayName:
    """assistant_display_name from AssistantInstanceConfig reaches start_session."""

    def test_team360_returns_vera(self):
        service = AutomationDiagnosisService(ai_interpreter=MockAIInterpreter())
        started = service.start_session({"source_url": "https://team360.live"})
        assert started["assistant_display_name"] == "Vera"
        assert started["assistant_instance_id"] == "team360_sales_diagnosis"

    def test_assistant_instance_id_stable_under_different_names(self):
        """Different configs must have different assistant_instance_id but
        the same session structure."""
        service = AutomationDiagnosisService(ai_interpreter=MockAIInterpreter())
        team360 = service.start_session({"assistant_instance_id": "team360_sales_diagnosis"})
        legacy = service.start_session({"assistant_instance_id": "automation_diagnosis_default"})
        assert team360["assistant_instance_id"] == "team360_sales_diagnosis"
        assert legacy["assistant_instance_id"] == "automation_diagnosis_default"
        assert team360["assistant_display_name"] == "Vera"
        assert legacy["assistant_display_name"] == ""  # no commercial name set
        assert team360["assistant_instance_id"] != legacy["assistant_instance_id"]

    def test_unknown_instance_fallback_name(self):
        """Unknown assistant_instance_id raises ValueError before display_name."""
        service = AutomationDiagnosisService(ai_interpreter=MockAIInterpreter())
        with pytest.raises(ValueError, match="Unknown assistant_instance_id"):
            service.start_session({"assistant_instance_id": "cliente_inexistente"})
