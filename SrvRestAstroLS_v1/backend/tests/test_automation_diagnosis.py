import json
from pathlib import Path

import pytest

from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
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
