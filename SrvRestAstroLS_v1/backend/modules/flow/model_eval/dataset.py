"""Dataset loading and validation for the Flow model evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

MODEL_EVAL_DIR = Path(__file__).resolve().parent

_CASE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["id", "contract", "category", "message", "expected"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "contract": {"enum": ["intake", "operational"]},
        "category": {"type": "string", "minLength": 1},
        "subject": {"type": "string"},
        "message": {"type": "string", "minLength": 1},
        "notes": {"type": "string"},
        "weight": {"type": "number", "exclusiveMinimum": 0},
        "consistency_subset": {"type": "boolean"},
        "expected": {
            "oneOf": [
                {"$ref": "#/definitions/intake_expected"},
                {"$ref": "#/definitions/operational_expected"},
            ]
        },
    },
    "definitions": {
        "intake_expected": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "request_count": {
                    "oneOf": [
                        {"type": "integer", "minimum": 0},
                        {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                    ]
                },
                "clarification_required": {"type": ["boolean", "null"]},
                "requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description_contains": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "description_contains_any": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "description_not_contains": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "tentative_category": {"type": ["string", "null"]},
                            "sector": {"type": ["string", "null"]},
                            "location_text": {"type": ["string", "null"]},
                            "location_contains": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "location_or_context_contains": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "missing_data": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "missing_data_no_extra": {"type": "boolean"},
                            "context_notes_contains": {
                                "type": ["array", "null"],
                                "items": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        },
        "operational_expected": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "enum": [
                        "ACK_OR_PROGRESS",
                        "RESOLUTION_PROPOSED",
                        "AMBIGUOUS",
                        "UNRELATED",
                        "UNSUPPORTED_OPERATIONAL_ACTION",
                    ]
                }
            },
        },
    },
}


def _validate_case(case: dict[str, Any]) -> None:
    validate(instance=case, schema=_CASE_SCHEMA)


def load_cases(
    intake_path: Path | str | None = None,
    operational_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Load and validate both case files. Raises ValueError on any problem."""
    intake_path = Path(intake_path) if intake_path else MODEL_EVAL_DIR / "cases_intake.json"
    operational_path = (
        Path(operational_path)
        if operational_path
        else MODEL_EVAL_DIR / "cases_operational.json"
    )
    cases: list[dict[str, Any]] = []
    for path in (intake_path, operational_path):
        if not path.exists():
            raise ValueError(f"Dataset file not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        contract = payload.get("contract")
        if contract not in {"intake", "operational"}:
            raise ValueError(f"{path.name}: invalid contract label {contract!r}")
        for case in payload.get("cases", []):
            case = dict(case)
            case["contract"] = contract
            case["weight"] = float(case.get("weight", 1.0))
            _validate_case(case)
            cases.append(case)
    return validate_cases(cases)


def validate_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce dataset-level invariants and return a normalized copy."""
    seen: set[str] = set()
    for case in cases:
        if case["id"] in seen:
            raise ValueError(f"Duplicate case id: {case['id']}")
        seen.add(case["id"])
        if case["contract"] == "intake":
            expected = case["expected"]
            requests = expected.get("requests") or []
            if not requests and "request_count" not in expected:
                raise ValueError(
                    f"{case['id']}: intake case without verifiable expectations"
                )
        else:
            expected_action = case["expected"].get("action")
            if expected_action not in {
                "ACK_OR_PROGRESS",
                "RESOLUTION_PROPOSED",
                "AMBIGUOUS",
                "UNRELATED",
                "UNSUPPORTED_OPERATIONAL_ACTION",
            }:
                raise ValueError(f"{case['id']}: invalid expected action")
    return cases


def consistency_subset(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [case for case in cases if case.get("consistency_subset")]
