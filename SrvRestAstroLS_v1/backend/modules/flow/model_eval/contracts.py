"""Shared constants for the Flow model evaluation.

Only aliases reachable through LiteLLM are evaluated. Flow never talks to a
provider directly; the benchmark mirrors that by using the existing LiteLLM
client and the real Flow interpreter adapters.
"""

from __future__ import annotations

MODEL_ALIASES: tuple[str, ...] = (
    "openai_gpt-5.4-nano",
    "openai_gpt-5.6-luna-medium",
    "deepseek_deepseek_4_flash",
    "deepseek_deepseek_4_pro",
)

# The main comparison mandated by the task. DeepSeek results stay separate.
PRIMARY_COMPARISON: tuple[str, ...] = (
    "openai_gpt-5.4-nano",
    "openai_gpt-5.6-luna-medium",
)

# Failure taxonomy (Team360 model eval policy).
FAILURE_TYPES: tuple[str, ...] = (
    "MODEL_OUTPUT_FAILURE",
    "LITELLM_FAILURE",
    "MODEL_EVAL_CODE_FAILURE",
    "FLOW_CONTRACT_FAILURE",
    "ENVIRONMENT_FAILURE",
    "TEST_EXPECTATION_FAILURE",
)

# Production parameters of the real Flow interpreters. The benchmark does not
# change them between models (determinism requirement).
INTAKE_CONTRACT = {
    "interpreter": "modules.flow.intake.ai.LiteLLMFlowIntakeInterpreter",
    "temperature": 0.2,
    "max_tokens": 1800,
    "schema": "modules.flow.intake.ai._INITIAL_SCHEMA",
}
OPERATIONAL_CONTRACT = {
    "interpreter": "modules.flow.operational_ai.LiteLLMOperationalInterpreter",
    "temperature": 0.0,
    "max_tokens": 300,
    "schema": "modules.flow.operational_ai._SCHEMA",
}
