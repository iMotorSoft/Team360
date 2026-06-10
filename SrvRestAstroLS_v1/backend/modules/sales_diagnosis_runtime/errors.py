class SalesDiagnosisRuntimeError(Exception):
    """Base exception for sales diagnosis runtime errors."""


class RetrievalUnavailableError(SalesDiagnosisRuntimeError):
    """Raised when no retrieval provider is configured or available."""


class LLMUnavailableError(SalesDiagnosisRuntimeError):
    """Raised when no LLM provider is configured or available."""


class GuardrailViolationError(SalesDiagnosisRuntimeError):
    """Raised when the response violates guardrail policy critically."""


class UnsafeResponseError(SalesDiagnosisRuntimeError):
    """Raised when the response is unsafe and cannot be delivered."""


class InvalidAssistantRuntimeInputError(SalesDiagnosisRuntimeError):
    """Raised when the input fails validation."""
