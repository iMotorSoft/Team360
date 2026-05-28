# Automation Diagnosis

`automation_diagnosis` is the guided automation diagnosis assistant for Team360.

It is not an open chatbot. It collects structured information, retrieves Team360 knowledge, asks LiteLLM to interpret and summarize, then classifies with deterministic scoring and rules.

## Required Outputs

The assistant must produce:

1. visible user response;
2. internal Team360 lead card;
3. measurable events.

## Intake Fields

The guided flow should collect:

- process to automate;
- business pain;
- systems involved;
- frequency;
- volume;
- rule clarity;
- human dependency;
- access and permissions;
- MFA / 2FA;
- security risks;
- data sensitivity;
- expected result;
- economic or operational impact;
- possible RAG/GraphRAG need;
- possible worker need;
- approval level.

## Classification

Allowed final classifications:

```text
standard_package
operational_automation
consulting_required
not_recommended
```

The LLM can enrich signals but cannot decide final classification.

## Internal Result

The internal card should include:

- `recommended_package_type`;
- `suggested_worker_definitions`;
- `required_package_worker_config`;
- `required_credential_refs`;
- `required_knowledge_scope`;
- `automation_mode`;
- `risk_flags`;
- `blocked_actions`;
- `requires_human_approval`.

## Knowledge Scope

Initial scope:

```text
ks_team360_automation_diagnosis
```

It should contain criteria about:

- automation viability;
- security limits;
- MFA / 2FA;
- SAP B1;
- browser automation;
- desktop automation;
- HITL;
- commercial packages;
- risk matrix;
- classification examples;
- ERP / SAP B1 vertical;
- no-bypass security rules.

## Phase 1 Validation

Expected command:

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_automation_diagnosis.py
```
