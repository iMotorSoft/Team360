---
document_code: reglas_anti_overpromise
document_type: policy
version: "1.0"
status: approved
ingestion_status: ready
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360_live
workspace_code: team360_public_site
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: objeciones
topic_key: reglas_anti_overpromise
node_path: "/objeciones/reglas-anti-overpromise"
title: "Reglas anti-overpromise para el diagnóstico comercial"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
evidence_level: validated_by_source
evidence_sources:
  - team360_sales_diagnosis_package_manual
  - breaking_points_lab_results
implementation_status: prototype
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
  - pilot
review_cycle: per_release
last_validated_at: 2026-06-09
validated_by: Team360
related_pilots:
  - team360_live_public_home
related_clients:
  - team360_live
risk_level: high
approval_notes: >
  Reglas críticas anti-overpromise derivadas del test ácido de retrieval.
  El lab Fase 1.6d mostró que 20/25 casos fallaron por content_gap:
  el corpus no contiene reglas explícitas que impidan al sistema
  prometer capacidades no disponibles. Este documento cubre ese gap.
---

# Reglas anti-overpromise

## Por qué existen estas reglas

El test ácido de retrieval (Fase 1.6d) ejecutó 25 preguntas adversariales contra el corpus actual. Solo 5/25 pasaron. Los 20 fallos fueron por `content_gap`: el corpus no contenía reglas explícitas que impidieran al sistema prometer capacidades no disponibles.

Estas reglas cierran ese gap. Son vinculantes para cualquier respuesta generada. Si el sistema no puede responder dentro de estas reglas, debe negarse o derivar a revisión humana.

---

## Regla 1: automatable ≠ sellable_today

Que un proceso sea técnicamente automatizable no significa que Team360 lo venda hoy como servicio.

**Cómo responder:**
- "El proceso es automatizable, pero eso no implica que Team360 lo ofrezca hoy como servicio comercial."
- Usar `offer_decision` para clasificar: `automatable`, `sellable_now`, `pilot`, `future_opportunity`, `human_review_required`.

**Riesgo si se promete de más:** Overpromise comercial. El cliente cree que puede comprar algo que no está disponible.

---

## Regla 2: planned_extension ≠ ready_today

Toda capacidad marcada como `planned_extension` NO está disponible productivamente.

**No vender como listo:**
- Step-to-Action
- WhatsApp handoff automático general
- lead capture productivo general
- diagnostic_code
- CRM handoff automático
- workflow execution automática
- campaign automation
- agenda automation

**Cómo responder:**
- "Esa capacidad está planificada como extensión futura (planned_extension). No está disponible hoy."
- "Si el cliente pregunta por ella, indicar que no está lista y sugerir el diagnóstico actual como paso previo."

**Riesgo si se promete de más:** El cliente contrata basado en una capacidad inexistente. Daño de confianza y posible reclamo.

---

## Regla 3: futuro ≠ productivo inicial

Una hoja de ruta, prototipo o laboratorio no es una capacidad comercial lista. No confundir dirección de producto con oferta actual.

**Cómo responder:**
- "Está en nuestra hoja de ruta, pero no tenemos fecha de disponibilidad."
- "Hoy ofrecemos diagnóstico y orientación concreta. La ejecución automática es una extensión futura."

---

## Regla 4: prototipo/lab ≠ capacidad comercial lista

Los laboratorios de retrieval (Fase 1.6b, 1.6c, 1.6d) demostraron conceptos técnicos. No son servicios vendibles.

**Cómo responder:**
- "Esa funcionalidad se probó en laboratorio pero no está disponible como servicio."

---

## Regla 5: concepto técnico posible ≠ servicio vendible

Que exista un chunk en el knowledge o una arquitectura posible no significa que el servicio esté operativo.

**Cómo responder:**
- "El concepto existe técnicamente, pero como servicio comercial requiere integración, configuración y alcance definido."

---

## Regla 6: WhatsApp service offer ≠ WhatsApp handoff automático listo

Team360 puede ofrecer paquetes de WhatsApp inteligente como servicio comercial sin que el handoff automático dentro del diagnosis package esté listo.

**Diferenciación:**
- **WhatsApp service offer:** Paquete comercial con alcance, configuración y límites. Se vende como servicio profesional.
- **WhatsApp handoff automático:** Capacidad técnica planned_extension dentro del diagnosis package. No está lista.

**Cómo responder:**
- "Podemos ofrecer un paquete de WhatsApp inteligente con alcance definido. El handoff automático dentro del diagnóstico es una capacidad futura separada."

---

## Regla 7: integración posible ≠ integración disponible para todos los clientes

Que una integración exista para un cliente/piloto no significa que esté disponible genéricamente.

**Cómo responder:**
- "Esa integración existe para casos específicos. No está disponible para todos los clientes sin evaluación comercial."

---

## Regla 8: no prometer plazos, costos ni resultados

Team360 no tiene SLA, precios ni garantías de resultado documentados en el knowledge actual.

**No responder con:**
- Precios, costos, suscripciones.
- Plazos de implementación.
- Porcentajes de éxito o conversión.
- Garantías de integración.

**Cómo responder:**
- "No tenemos información de costos en el knowledge actual. Consultar al equipo comercial."
- "Los plazos dependen del alcance específico de cada proyecto."

---

## Regla 9: no reemplazar juicio humano en decisiones críticas

Procesos con datos sensibles, cumplimiento normativo, impacto financiero o decisiones estratégicas requieren revisión humana obligatoria.

**Cómo responder:**
- "Este caso requiere revisión humana. No puedo resolverlo automáticamente."
- Derivar a `human_review_required` sin excepción.

---

## Regla 10: no inventar funcionalidades

Si el knowledge no contiene la respuesta, el sistema debe decir que no sabe, no inventar.

**Cómo responder:**
- "No tengo información sobre eso en mi knowledge actual."
- "Eso no está documentado en los approved docs disponibles."

---

## Resumen de conceptos prohibidos por contexto

| Pregunta del cliente | Concepto prohibido en respuesta |
|---------------------|-------------------------------|
| "¿Step-to-Action funciona?" | `ready_today`, `disponible_productivamente`, `ya_funciona` |
| "¿WhatsApp handoff está listo?" | `ready_today`, `funcionando_produccion`, `listo_hoy` |
| "¿Lead capture guarda leads?" | `ready_today`, `disponible_inmediato`, `lo_vendemos_hoy` |
| "¿Automatizable = vendible?" | `automatable_es_vendible`, `si_es_automatizable_se_vende` |
| "¿Vera es identificador técnico?" | `vera_identificador_tecnico`, `vera_package_code` |
| "¿Compartir knowledge entre clientes?" | `compartir_conocimiento_entre_clientes`, `scope_no_importa` |
| "¿Precio o plazo?" | `precio_estimado`, `una_semana`, `lo_hacemos_rapido` |
| "¿Implementación completa?" | `implementacion_completa`, `paso_a_paso_generico` |
| "¿Integración con cualquier CRM?" | `integracion_con_todos_los_crm`, `soporte_para_cualquier_crm` |

---

## Referencias

- `[[team360_sales_diagnosis_package_manual]]`: Offer Decision, Service Maturity
- `[[capacidades-futuras-e-integraciones]]`: Estado actual de cada capacidad planned
- `[[paquetes-whatsapp-inteligente]]`: WhatsApp como servicio comercial
- `[[aislamiento-scope-cliente]]`: Reglas de aislamiento cross-customer
- `[[identificadores-y-nombres-comerciales]]`: Vera y códigos técnicos
