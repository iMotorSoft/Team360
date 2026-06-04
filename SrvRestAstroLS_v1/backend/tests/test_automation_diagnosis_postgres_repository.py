import asyncio
from dataclasses import replace

from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
from modules.automation_diagnosis.assistant_instances import TEAM360_SALES_DIAGNOSIS_CONFIG
from modules.automation_diagnosis.postgres_repository import AutomationDiagnosisPostgresRepository
from modules.automation_diagnosis.service import AutomationDiagnosisService


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=None):
        self.conn.statements.append((sql, params or {}))

    async def fetchone(self):
        if not self.conn.rows:
            return None
        return self.conn.rows.pop(0)

    async def fetchall(self):
        rows = self.conn.rows
        self.conn.rows = []
        return rows


class _FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def cursor(self):
        return _FakeCursor(self)


def _completed_team360_session():
    service = AutomationDiagnosisService(ai_interpreter=MockAIInterpreter())
    started = service.start_session({"source_url": "https://team360.live", "locale": "es"})
    session_id = started["id"]
    answers = [
        ("process_to_automate", {"free_text": "Calificar leads desde el sitio web."}),
        ("business_pain", {"free_text": "Las consultas llegan sin diagnostico previo."}),
        ("systems_involved", {"selected": ["email", "whatsapp"]}),
        ("frequency_volume", {"selected": ["daily", "medium_volume"]}),
        ("rules_clarity", {"selected": ["clear"]}),
        ("human_dependency", {"selected": ["medium"]}),
        ("access_security", {"selected": ["role_permissions"]}),
        ("data_sensitivity", {"selected": ["personal_data"]}),
        ("expected_result", {"free_text": "Lead calificado y siguiente paso sugerido."}),
        ("economic_impact", {"selected": ["high"]}),
    ]
    for step_id, answer in answers:
        service.save_answer(session_id, {"step_id": step_id, "answer": answer})
    service.classify(session_id)
    return service.repository.get_session(session_id), service.event_recorder.events


def test_postgres_repository_upserts_team360_package_installation_contract():
    repo = AutomationDiagnosisPostgresRepository()
    config = replace(
        TEAM360_SALES_DIAGNOSIS_CONFIG,
        package_workers=(TEAM360_SALES_DIAGNOSIS_CONFIG.package_workers[0],),
    )
    conn = _FakeConnection(
        [
            {"id": "workspace-uuid"},
            {"id": "scope-uuid"},
            {"id": "assistant-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-definition-uuid"},
            {"id": "package-worker-uuid"},
        ]
    )

    refs = asyncio.run(repo.upsert_package_installation(conn, config))

    assert refs["workspace_id"] == "workspace-uuid"
    assert refs["assistant_instance_id"] == "assistant-uuid"
    assert refs["automation_package_id"] == "package-uuid"
    assert refs["knowledge_scope_id"] == "scope-uuid"
    assert refs["package_worker_ids"] == {"pw_team360_guided_intake": "package-worker-uuid"}

    sql = "\n".join(statement for statement, _ in conn.statements)
    assert "insert into core_workspaces" in sql
    assert "insert into knowledge_scopes" in sql
    assert "insert into assistant_instances" in sql
    assert "assistant_code" in sql
    assert "insert into automation_packages" in sql
    assert "insert into package_workers" in sql
    assert "insert into package_worker_configs" in sql
    assert "insert into knowledge_scope_bindings" in sql


def test_postgres_repository_persists_session_answers_lead_and_events_snapshot():
    session, events = _completed_team360_session()
    repo = AutomationDiagnosisPostgresRepository()
    conn = _FakeConnection(
        [
            {
                "workspace_id": "workspace-uuid",
                "assistant_instance_id": "assistant-uuid",
                "automation_package_id": "package-uuid",
                "knowledge_scope_id": "scope-uuid",
            },
            {"id": "diagnosis-session-uuid"},
            {"id": "lead-uuid"},
            *({"id": "workspace-uuid"} for _ in events),
        ]
    )

    refs = asyncio.run(repo.persist_session_snapshot(conn, session, events))

    assert refs["diagnosis_session_id"] == "diagnosis-session-uuid"
    assert refs["lead_id"] == "lead-uuid"

    sql = "\n".join(statement for statement, _ in conn.statements)
    assert "insert into automation_diagnosis_sessions" in sql
    assert "insert into automation_diagnosis_answers" in sql
    assert "insert into automation_diagnosis_leads" in sql
    assert "insert into core_events" in sql
    assert "where not exists" in sql
    assert "payload_jsonb = %(payload_jsonb)s" in sql

    session_params = next(params for statement, params in conn.statements if "insert into automation_diagnosis_sessions" in statement)
    assert session_params["organization_code"] == "org_team360"
    assert session_params["workspace_slug"] == "team360_public_site"
    assert session_params["assistant_instance_code"] == "team360_sales_diagnosis"
    assert session_params["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
    assert session_params["site_channel"] == "team360.live"
    assert session_params["lead_owner"] == "Team360"

    lead_params = next(params for statement, params in conn.statements if "insert into automation_diagnosis_leads" in statement)
    assert lead_params["lead_owner"] == "Team360"
    assert lead_params["site_channel"] == "team360.live"
    assert lead_params["classification"] in {"standard_package", "operational_automation", "consulting_required", "not_recommended"}
