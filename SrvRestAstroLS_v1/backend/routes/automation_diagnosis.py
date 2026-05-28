"""Automation diagnosis route functions.

The current Team360 backend entrypoint is still a placeholder. These functions
keep the public API contract ready for Litestar route decorators without
exposing workers directly to customers.
"""

from __future__ import annotations

from modules.automation_diagnosis import build_default_service


_SERVICE = build_default_service()


def start_session(payload: dict) -> dict:
    return _SERVICE.start_session(payload)


def get_session(session_id: str) -> dict:
    return _SERVICE.get_session(session_id)


def save_answer(session_id: str, payload: dict) -> dict:
    return _SERVICE.save_answer(session_id, payload)


def classify(session_id: str) -> dict:
    return _SERVICE.classify(session_id)


def capture_contact(session_id: str, payload: dict) -> dict:
    return _SERVICE.capture_contact(session_id, payload)


def finalize(session_id: str) -> dict:
    return _SERVICE.finalize(session_id)


def debug(session_id: str) -> dict:
    return _SERVICE.debug(session_id)


def search_knowledge(payload: dict) -> dict:
    return _SERVICE.search_knowledge(payload)
