"""Application service for automation diagnosis Phase 1."""

from __future__ import annotations

from typing import Any

from .ai_interpreter import AIInterpreterPort, build_ai_interpreter
from .assistant_instances import resolve_assistant_instance_config
from .answer_collector import answers_as_text, normalize_answer
from .classifier import classify_session
from .events import InMemoryEventRecorder
from .guided_flow import get_guided_flow, required_step_ids
from .knowledge_connector import InMemoryKnowledgeRepository, build_default_knowledge_repository
from .knowledge_retrieval_provider import (
    build_dev_retrieval_provider,
    is_dev_retrieval_enabled,
)
from .lead_output import build_internal_card
from .repository import InMemoryDiagnosisRepository
from .result_generator import generate_user_result
from .schemas import (
    DEFAULT_ASSISTANT_INSTANCE_ID,
    DEFAULT_KNOWLEDGE_SCOPE_ID,
    DiagnosisSession,
    new_id,
    to_dict,
    utc_now_iso,
)
from .scoring import score_session


class AutomationDiagnosisService:
    # @lat: [[team360-platform#Team360 Platform#Control Plane]]
    # @lat: [[multi-package-workers#Multi-package Workers#Interaction Boundary]]
    def __init__(
        self,
        repository: InMemoryDiagnosisRepository | None = None,
        knowledge_repository: InMemoryKnowledgeRepository | None = None,
        event_recorder: InMemoryEventRecorder | None = None,
        ai_interpreter: AIInterpreterPort | None = None,
    ) -> None:
        self.repository = repository or InMemoryDiagnosisRepository()
        if knowledge_repository is not None:
            self.knowledge_repository = knowledge_repository
        elif is_dev_retrieval_enabled():
            dev_provider = build_dev_retrieval_provider()
            if dev_provider is not None:
                self.knowledge_repository = dev_provider
            else:
                self.knowledge_repository = build_default_knowledge_repository()
        else:
            self.knowledge_repository = build_default_knowledge_repository()
        self.event_recorder = event_recorder or InMemoryEventRecorder()
        self.ai_interpreter = ai_interpreter or build_ai_interpreter()

    def start_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        # @lat: [[customer-packaged-assistant-instance#Required Runtime Context]]
        config = resolve_assistant_instance_config(payload, DEFAULT_ASSISTANT_INSTANCE_ID)
        locale = config.resolve_locale(payload.get("locale"))
        session = DiagnosisSession(
            id=new_id("diag"),
            organization_id=config.organization_id,
            workspace_id=config.workspace_id,
            assistant_instance_id=config.assistant_instance_id,
            automation_package_id=config.automation_package_id,
            knowledge_scope_id=config.knowledge_scope_id,
            source_url=payload.get("source_url") or "",
            site_channel=config.site_channel,
            lead_owner=config.lead_owner,
            locale=locale,
            market=config.market,
            visitor=payload.get("visitor") or {},
            package_worker_ids=config.package_worker_ids(),
            cost_attribution={
                "cost_center": config.cost_center,
                "lead_owner": config.lead_owner,
                "market": config.market,
                "site_channel": config.site_channel,
            },
            metadata={
                "assistant_instance": config.to_session_metadata(),
                "organization_name": config.organization_name,
                "workspace_name": config.workspace_name,
                "automation_package_name": config.automation_package_name,
            },
        )
        self.repository.save_session(session)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.session_started",
            {
                "site_channel": session.site_channel,
                "lead_owner": session.lead_owner,
                "locale": session.locale,
                "package_worker_ids": session.package_worker_ids,
            },
        )
        return self.get_session(session.id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        data = to_dict(session)
        data["answers"] = {key: to_dict(value) for key, value in session.answers.items()}
        data["events"] = self.event_recorder.list_for_session(session_id)
        return data

    def save_answer(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        step_id = payload["step_id"]
        answer = normalize_answer(step_id, payload.get("answer") or {})
        session.answers[step_id] = answer
        session.updated_at_utc = utc_now_iso()
        self.repository.save_session(session)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.answer_saved",
            {"step_id": step_id, "selected": answer.selected, "has_free_text": bool(answer.free_text)},
        )
        return {"session_id": session_id, "answer": to_dict(answer)}

    def classify(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        missing = [step_id for step_id in required_step_ids() if step_id not in session.answers]
        if missing:
            raise ValueError(f"Missing required answers: {', '.join(missing)}")

        query = answers_as_text(session.answers)
        # @lat: [[knowledge-rag-graphrag#Knowledge RAG GraphRAG#Retrieval Criteria]]
        context = self.knowledge_repository.search(session.knowledge_scope_id, query, "rag", top_k=5)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.knowledge_retrieved",
            {"chunk_count": len(context.chunks), "retrieval_mode": context.retrieval_mode},
        )

        self.event_recorder.emit(session, "automation_diagnosis.ai_interpretation_started")
        interpretation = self.ai_interpreter.interpret(session, context)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.ai_interpretation_completed",
            {
                "provider": interpretation.provider,
                "model": interpretation.model,
                "usage": interpretation.usage,
                "latency_ms": interpretation.latency_ms,
            },
        )

        score = score_session(session, interpretation)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.scoring_completed",
            {"score_total": score.score_total, "risk_flags": score.risk_flags},
        )
        classification = classify_session(session, score, interpretation)
        user_result = generate_user_result(classification, score, interpretation)
        internal_card = build_internal_card(session, interpretation, score, classification)
        result = {
            "classification": classification.classification,
            "score_total": score.score_total,
            "automation_mode": classification.automation_mode,
            "recommended_package_type": classification.recommended_package_type,
            "suggested_worker_definitions": classification.suggested_worker_definitions,
            "required_package_worker_config": classification.required_package_worker_config,
            "required_credential_refs": classification.required_credential_refs,
            "required_knowledge_scope": classification.required_knowledge_scope,
            "risk_flags": classification.risk_flags,
            "blocked_actions": classification.blocked_actions,
            "requires_human_approval": classification.requires_human_approval,
            "user_response": user_result,
            "internal_card": internal_card,
            "ai_interpretation": to_dict(interpretation),
            "retrieved_context": to_dict(context),
            "score_breakdown": score.score_breakdown,
            "rule_hits": score.rule_hits,
        }
        session.result = result
        session.updated_at_utc = utc_now_iso()
        self.repository.save_session(session)
        self.event_recorder.emit(
            session,
            "automation_diagnosis.classified",
            {
                "classification": classification.classification,
                "score_total": score.score_total,
                "automation_mode": classification.automation_mode,
            },
        )
        return result

    def capture_contact(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        session.contact = {
            "name": payload.get("name"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "company": payload.get("company"),
            "consent": bool(payload.get("consent")),
        }
        session.updated_at_utc = utc_now_iso()
        self.repository.save_session(session)
        self.event_recorder.emit(session, "automation_diagnosis.contact_captured", {"has_email": bool(payload.get("email"))})
        return {"session_id": session_id, "contact": session.contact}

    def finalize(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        session.status = "finalized"
        session.updated_at_utc = utc_now_iso()
        self.repository.save_session(session)
        self.event_recorder.emit(session, "automation_diagnosis.finalized")
        return self.get_session(session_id)

    def debug(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        return {
            "session": self.get_session(session_id),
            "flow": get_guided_flow(),
            "knowledge": self.knowledge_repository.scope_debug(session.knowledge_scope_id),
        }

    def search_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope_id = payload.get("knowledge_scope_id") or DEFAULT_KNOWLEDGE_SCOPE_ID
        context = self.knowledge_repository.search(
            scope_id,
            payload.get("query") or "",
            payload.get("retrieval_mode") or "rag",
            int(payload.get("top_k") or 5),
        )
        return to_dict(context)


def build_default_service(ai_provider: str | None = None) -> AutomationDiagnosisService:
    return AutomationDiagnosisService(ai_interpreter=build_ai_interpreter(ai_provider))
