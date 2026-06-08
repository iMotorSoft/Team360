# Metadata Frontmatter

Contrato comun de metadata para documentos fuente knowledge.

El worker actual de `knowledge_ingestion` valida un subconjunto minimo. Este
contrato editorial agrega campos de curaduria y madurez para preparar ingestion
semantica y retrieval gobernado.

## Campos minimos comunes

```yaml
---
document_code: <stable_kebab_or_snake_code>
status: <draft|approved|active|deprecated|archived>
ingestion_status: <not_ready|ready|approved_for_ingestion|deprecated>
knowledge_scope_code: <knowledge_scope_code>
scope_type: <global|package|partner|organization|workspace|service|assistant_instance|session>
organization_code: <organization_code>
workspace_code: <workspace_code>
package_code: <package_code_or_empty>
assistant_instance_code: <assistant_instance_code_or_empty>
service_code: <service_code_or_empty>
area_key: <area>
topic_key: <topic>
document_type: <policy|guide|procedure|template|faq|reference|report|other>
visibility: <public|internal|restricted|confidential>
access_tags:
  - <tag>
locale: <es|en|he>
version: "1.0"
title: "<Titulo>"
source_type: markdown
node_path: "/<area>/<topic>"
---
```

## Campos de curaduria recomendados

```yaml
evidence_level: <hypothesis|validated_by_source|validated_by_pilot|validated_by_production|deprecated>
evidence_sources:
  - <source_code>
implementation_status: <not_implemented|prototype|pilot_done|production_client|paused|deprecated>
commercial_status: <exploratory|sellable_pilot|sellable_service|core_offer|future_package|not_offered>
service_maturity: <CORE_VALIDADO|PILOTO_VALIDADO|OPORTUNIDAD|PAQUETE_FUTURO|NO_OFRECER_AUN>
offer_decision: <automatable|sellable_now|pilot|future_opportunity|human_review_required>
validation_context: <team360_live_internal|public_home|client_pilot|production_client|research>
review_cycle: <monthly|quarterly|per_pilot|per_release|ad_hoc>
last_validated_at: <YYYY-MM-DD>
validated_by: <persona|role|team>
related_pilots: []
related_clients: []
risk_level: <low|medium|high>
approval_notes: "<criterio, limite o razon de permanencia en draft>"
```

## Reglas por status

| `status` | `ingestion_status` esperado | Regla |
|---|---|---|
| `draft` | `not_ready` | Puede tener metadata incompleta; no se ingiere. |
| `approved` | `ready` o `approved_for_ingestion` | Requiere metadata completa y revision. |
| `active` | `approved_for_ingestion` | Apto para ingestion activa. |
| `deprecated` | `deprecated` | No alimentar respuestas nuevas salvo politica explicita. |
| `archived` | `deprecated` | Referencia historica; no se ingiere. |

## Reglas de rutas

- `node_path` debe empezar con `/`.
- `node_path` no debe terminar en `/`, salvo raiz `/`.
- `area_key` y `topic_key` no deben contener `/`.
- En `approved/{area_key}/`, el `area_key` debe coincidir con la carpeta.

## Global vs paquete

Para knowledge global:

- `scope_type: global`;
- `package_code: ""`;
- `assistant_instance_code: ""` salvo que exista una razon documentada;
- `node_path` debe describir un concepto transversal.

Para knowledge de paquete:

- `scope_type: package` por defecto;
- `package_code` obligatorio;
- `knowledge_scope_code` debe coincidir con `_metadata/knowledge-scope-mapping.yaml`.

## Vera

`Vera / Asistente Inteligente Vera` puede aparecer como `commercial_name`,
`display_name` o texto visible. No debe aparecer como identificador tecnico
core ni generar codigos `vera_*`.
