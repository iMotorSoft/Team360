"""Automation diagnosis module.

Phase 1 keeps workers internal, but models package/worker/knowledge contracts so
the module can later move to queues, browser workers, desktop workers or
external services without exposing workers directly to customers.
"""

from .service import AutomationDiagnosisService, build_default_service

__all__ = ["AutomationDiagnosisService", "build_default_service"]
