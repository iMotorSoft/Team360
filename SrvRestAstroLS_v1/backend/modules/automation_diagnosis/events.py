"""Event recording for automation diagnosis."""

from __future__ import annotations

from .schemas import DiagnosisEvent, DiagnosisSession, to_dict


class InMemoryEventRecorder:
    def __init__(self) -> None:
        self.events: list[DiagnosisEvent] = []

    def emit(self, session: DiagnosisSession, event_name: str, payload: dict | None = None) -> DiagnosisEvent:
        event = DiagnosisEvent(
            event_name=event_name,
            organization_id=session.organization_id,
            workspace_id=session.workspace_id,
            assistant_instance_id=session.assistant_instance_id,
            automation_package_id=session.automation_package_id,
            knowledge_scope_id=session.knowledge_scope_id,
            session_id=session.id,
            correlation_id=session.correlation_id,
            payload=payload or {},
            site_channel=session.site_channel,
            lead_owner=session.lead_owner,
            locale=session.locale,
        )
        self.events.append(event)
        return event

    def list_for_session(self, session_id: str) -> list[dict]:
        return [to_dict(event) for event in self.events if event.session_id == session_id]
