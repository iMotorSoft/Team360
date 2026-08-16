"""Reproducible model evaluation for Team360 Flow intelligent analysis.

This package is the exclusive WRITE scope of the MODEL EVAL agent:
  backend/modules/flow/model_eval/**
It reuses the real Flow contracts (intake and operational interpreters) and
never duplicates production prompts, schemas or routing logic.
"""

from .contracts import (
    FAILURE_TYPES,
    MODEL_ALIASES,
    PRIMARY_COMPARISON,
)
from .dataset import load_cases, validate_cases

__all__ = [
    "FAILURE_TYPES",
    "MODEL_ALIASES",
    "PRIMARY_COMPARISON",
    "load_cases",
    "validate_cases",
]
