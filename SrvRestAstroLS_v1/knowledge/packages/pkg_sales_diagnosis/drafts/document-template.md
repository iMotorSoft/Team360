---
document_code: <stable_document_code>
status: draft
ingestion_status: not_ready
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360
workspace_code: team360_platform
package_code: pkg_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
area_key: <area>
topic_key: <topic>
document_type: <policy|guide|procedure|template|faq|reference|report|other>
visibility: <public|internal|restricted|confidential>
access_tags:
  - <tag>
locale: <es|en|he>
version: "<x.y>"
title: "<Título descriptivo del documento>"
source_type: markdown
node_path: "/<area>/<topic>"
evidence_level: <hypothesis|validated_by_source|validated_by_pilot|validated_by_production|deprecated>
evidence_sources:
  - <cv_inventory|implementation|pilot|commercial_test|client_feedback|product_frontend|mamamia360|other>
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
approval_notes: "<criterio de aprobación, límites o motivo de permanencia en draft>"
---

# {{ title }}

## Objetivo

<!-- Breve descripción del propósito del documento -->

## Alcance

<!-- A quién aplica, qué cubre y qué no cubre -->

## Estado de evidencia y madurez

<!--
Campos obligatorios antes de promover a approved/:
- evidence_level
- evidence_sources
- implementation_status
- commercial_status
- service_maturity
- offer_decision
- validation_context
- review_cycle
- last_validated_at
- validated_by
- risk_level
- approval_notes

Campos opcionales/contextuales:
- related_pilots
- related_clients

Usar [] en related_pilots o related_clients cuando no apliquen, no existan o no puedan divulgarse.
-->

### Contexto de validación

- <!-- Indicar si el aprendizaje viene de Team360.live, home pública, piloto cliente, producción o investigación -->
- <!-- Separar automatizable de vendible hoy: un proceso puede ser automatizable y aun así requerir piloto, oportunidad futura o revisión humana -->

### Evidencia usada

- <!-- Fuente 1 y por qué valida o limita este documento -->

### Límites de uso

- <!-- Qué NO debe prometer Vera / Asistente Inteligente Vera con base en este documento -->

## Contenido

### Sección 1

Contenido de la sección 1.

### Sección 2

Contenido de la sección 2.

## Referencias

- Enlaces a documentos relacionados dentro de este mismo corpus
- Documentos externos si aplica
- Evidencia fuente, pilotos o implementaciones relacionadas si aplica

## Historial de cambios

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 1.0 | YYYY-MM-DD | Creación inicial |
