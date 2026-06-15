---
document_code: cotizacion_precios_limites
document_type: policy
version: "1.0"
status: approved
ingestion_status: ready
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360_live
workspace_code: team360_public_site
area_key: ventas
topic_key: cotizacion_precios
node_path: "/ventas/cotizacion-precios-limites-comerciales"
title: "Cotización, precios y límites comerciales — reglas del diagnóstico"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-14
access_tags:
  - ceo
  - director_comercial
  - gerente_ventas
  - ejecutivo_comercial
evidence_level: validated_by_source
implementation_status: prototype
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
review_cycle: per_release
last_validated_at: 2026-06-14
validated_by: Team360
risk_level: high
approval_notes: >
  Política que define cómo el diagnóstico debe manejar consultas sobre
  precios, cotización automática, SLA y disponibilidad comercial.
  Team360 puede orientar pero no cotizar sin configuración comercial aprobada.
---

# Cotización, precios y límites comerciales

## Propósito

Establecer qué puede y qué no puede responder el diagnóstico de Team360
cuando un cliente pregunta por precios, cotización automática, plazos, SLA
o disponibilidad comercial.

## Regla central

El diagnóstico puede detectar necesidad, riesgo, alcance y datos faltantes,
pero no debe inventar precios, plazos, SLA ni disponibilidad comercial.
La cotización automática (auto-quote) no está activa salvo que exista
configuración comercial aprobada explícitamente.

No confundir factibilidad técnica con vendible hoy. Una capacidad puede ser
técnicamente posible pero no estar disponible comercialmente.

## Qué puede orientar el diagnóstico

- Detectar si una consulta del cliente tiene intención de compra o cotización.
- Indicar qué información faltaría para generar una propuesta.
- Diferenciar entre una capacidad automatizable, una vendible hoy y una
  planned_extension.
- Señalar si una solicitud comercial requiere revisión humana.
- Explicar las opciones comerciales conocidas (paquetes, servicios, pilotos).
- Recomendar que el cliente hable con el equipo comercial para precios
  y disponibilidad exactos.

## Qué no debe prometer

- Precios concretos, salvo que exista una oferta pública documentada
  en el knowledge base y esté marcada como vigente.
- Plazos de implementación sin verificación de capacidad del equipo.
- SLA sin acuerdo formal firmado.
- Cotización automática como funcionalidad activa. Sigue siendo
  planned_extension hasta nueva configuración.
- Disponibilidad comercial de capacidades que están en estado pilot,
  prototype o future_package.
- Que una capacidad técnicamente factible está disponible para contratación
  inmediata si no hay oferta comercial aprobada.

## Diferencia entre factible, vendible hoy y planned_extension

| Concepto | Significado |
|---|---|
| Factibilidad técnica | La capacidad se puede implementar con la tecnología actual |
| Vendible hoy | Existe oferta comercial aprobada, precio y disponibilidad |
| Planned extension | Está diseñado pero no activo comercialmente |

El diagnóstico debe indicar claramente en qué categoría está cada capacidad
mencionada.

## Cuándo requiere revisión comercial

El diagnóstico debe marcar `human_review_required` o derivar al equipo
comercial cuando:

- El cliente pregunta por precio, presupuesto o cotización.
- Solicita SLA, plazos o compromisos de disponibilidad.
- Pregunta por capacidades marcadas como planned_extension.
- Pregunta por capacidades en estado prototype o future_package.
- La consulta mezcla factibilidad técnica con decisión de compra.
- No existe oferta comercial documentada para lo solicitado.

## Términos de búsqueda / aliases

- precio, precios, costo, costos
- cotización, cotizar, cotización automática, auto-quote
- propuesta, propuesta automática, presupuesto
- SLA, acuerdo de nivel de servicio, plazo, disponibilidad
- vendible hoy, sellable now, comercialmente disponible
- factibilidad técnica, técnicamente posible
- planned_extension, extensión planificada
- revisión comercial, revisión humana, human review
- oferta, paquete, servicio, piloto comercial
- promesa comercial, overpromise
