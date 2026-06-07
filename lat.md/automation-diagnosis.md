# Automation Diagnosis

`automation_diagnosis` is the guided automation diagnosis assistant for Team360.

It is not an open chatbot. It collects structured information, retrieves Team360 knowledge, asks LiteLLM to interpret and summarize, then classifies with deterministic scoring and rules.

## Commercial Entry Points

The first commercial exits for `automation_diagnosis` are:

```text
team360_sales_diagnosis
mamamia360_sales_diagnosis
```

These are assistant instances, not separate engines.

`team360_sales_diagnosis` serves Team360's direct website and routes leads to Team360.

`mamamia360_sales_diagnosis` serves Mamá Mía 360 as a distributor / regional partner in Israel. It must support Spanish, English and Hebrew, adapt visible tone/branding to Mamá Mía 360, and route commercial opportunities through the partner configuration.

Assistant instance codes are stable technical identifiers. Visible commercial names, such as `Vera` for the Team360 direct sales assistant, belong in display/configuration fields and must not replace `team360_sales_diagnosis`, `pkg_sales_diagnosis` or `ks_team360_sales_diagnosis`. See [[customer-packaged-assistant-instance]].

The diagnosis engine must stay channel-aware:

- `organization_id`;
- `workspace_id`;
- `assistant_instance_id`;
- `site_channel`;
- `partner_id` when applicable;
- `market_country`;
- `locale`;
- `lead_owner`;
- `knowledge_scope_id`;
- `allowed_package_ids`.

This preserves the same technical core while allowing Team360 direct sales and partner-distributor sales to scale independently.

The Team360 direct assistant is not an internal demo. It is the first customer package installation of the sales and diagnosis package. See [[customer-packaged-assistant-instance]].

## Required Outputs

The assistant must produce:

1. visible user response;
2. internal Team360 lead card;
3. measurable events.

For partner channels, the internal lead card must preserve attribution to the partner, site channel, locale and market. Team360 remains the platform authority and audit owner; the configured partner owns the commercial follow-up when the channel says so.

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
