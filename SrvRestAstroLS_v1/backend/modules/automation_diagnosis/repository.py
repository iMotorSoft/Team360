"""Repositories for Phase 1 automation diagnosis."""

from __future__ import annotations

from .schemas import DiagnosisSession


class InMemoryDiagnosisRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, DiagnosisSession] = {}

    def save_session(self, session: DiagnosisSession) -> DiagnosisSession:
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> DiagnosisSession:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise ValueError(f"Unknown diagnosis session: {session_id}") from exc
