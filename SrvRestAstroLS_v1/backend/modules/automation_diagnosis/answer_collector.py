"""Answer normalization for guided diagnosis."""

from __future__ import annotations

import re
from typing import Any

from .guided_flow import get_step
from .schemas import DiagnosisAnswer


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def normalize_answer(step_id: str, answer_payload: dict[str, Any]) -> DiagnosisAnswer:
    step = get_step(step_id)
    if not step:
        raise ValueError(f"Unknown diagnosis step: {step_id}")

    raw_selected = answer_payload.get("selected") or []
    if isinstance(raw_selected, str):
        selected = [raw_selected]
    else:
        selected = [str(item).strip() for item in raw_selected if str(item).strip()]

    allowed = set(step.get("options") or [])
    if allowed:
        selected = [item for item in selected if item in allowed]

    free_text = _clean_text(answer_payload.get("free_text", ""))
    normalized_text = _clean_text(" ".join([*selected, free_text]))

    if step.get("required") and not selected and not free_text:
        raise ValueError(f"Step {step_id} requires an answer")

    return DiagnosisAnswer(
        step_id=step_id,
        selected=selected,
        free_text=free_text,
        normalized_text=normalized_text,
        metadata={"step_type": step.get("type")},
    )


def answers_as_text(answers: dict[str, DiagnosisAnswer]) -> str:
    lines = []
    for step_id, answer in answers.items():
        selected = ", ".join(answer.selected) if answer.selected else "-"
        text = answer.free_text or "-"
        lines.append(f"{step_id}: selected=[{selected}] text={text}")
    return "\n".join(lines)
