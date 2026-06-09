---
document_code: paquetes_whatsapp_inteligente
document_type: guide
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
area_key: ventas
topic_key: whatsapp_inteligente
node_path: "/ventas/whatsapp-inteligente"
title: "Paquetes de WhatsApp inteligente — oferta comercial"
visibility: public
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
  - director_comercial
evidence_level: validated_by_source
evidence_sources:
  - team360_sales_diagnosis_package_manual
  - commercial_inventory
implementation_status: prototype
commercial_status: sellable_pilot
service_maturity: PILOTO_VALIDADO
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
risk_level: medium
approval_notes: >
  Paquetes de WhatsApp inteligente como línea comercial de Team360.
  Cada paquete describe alcance, dependencias y límites. Ninguno
  incluye handoff automático con diagnosis package (eso es
  planned_extension separada). Los paquetes son servicios
  configurables, no productos automáticos llave en mano.
---

# Paquetes de WhatsApp inteligente

## ¿Qué es WhatsApp inteligente para Team360?

Team360 puede ofrecer soluciones de WhatsApp como servicio comercial para empresas, comercios, profesionales o instituciones que necesitan atender mejor, ordenar consultas, responder más rápido, capturar datos mínimos, calificar oportunidades, derivar a humanos con contexto y convertir conversaciones en procesos comerciales medibles.

No es un "chatbot genérico". Es una solución configurada con alcance definido para cada cliente.

---

## Diferenciación crítica

**WhatsApp service offer** (este documento) es una línea comercial de Team360. Son paquetes configurables con alcance humano y técnico definido.

**WhatsApp handoff automático** dentro del diagnosis package es una capacidad técnica planned_extension que no está lista. Son cosas distintas.

Un cliente puede contratar un paquete WhatsApp sin que el handoff automático del diagnóstico esté implementado. Y viceversa.

---

## Planes comerciales

### Plan 1 — WhatsApp Profesional

**Descripción:** Canal de WhatsApp configurado con bienvenida, FAQ básica, horarios y derivación humana.

**Para quién:** Comercios, profesionales independientes, pymes que reciben consultas por WhatsApp y necesitan organizar la atención.

**Qué puede incluir:**
- Configuración de canal WhatsApp Business
- Mensaje de bienvenida automatizado
- FAQ básica con respuestas predefinidas
- Horarios de atención visibles
- Derivación a humano cuando el asistente no puede resolver

**Valor comercial:** Atención ordenada 24/7 para consultas frecuentes. Libera tiempo del equipo.

**Depende de integración/configuración:**
- Número de WhatsApp Business del cliente
- Contenido de FAQ (lo provee el cliente o se releva)
- Definición de horarios y reglas de derivación

**No prometer como automático:**
- Respuestas a preguntas complejas no cargadas en FAQ
- Integración con sistemas del cliente sin configuración adicional

---

### Plan 2 — WhatsApp Asistente

**Descripción:** Asistente con información del negocio, servicios, horarios, precios orientativos, ubicación, formas de pago, procesos y derivación a humano.

**Para quién:** Negocios con catálogo de servicios o productos que quieren automatizar la primera consulta.

**Qué puede incluir:**
- Todo lo del Plan 1
- Información del negocio (servicios, horarios, ubicación)
- Precios orientativos (si el cliente los provee)
- Formas de pago
- Procesos comunes (cómo comprar, cómo contratar, cómo reservar)
- Derivación contextual a humano

**Valor comercial:** El asistente responde el 80% de las consultas frecuentes sin intervención humana.

**Depende de integración/configuración:**
- Contenido comercial del negocio
- Precios y formas de pago (los provee el cliente)
- Reglas de cuándo derivar a humano

**No prometer como automático:**
- Respuestas sobre stock o disponibilidad en tiempo real sin integración
- Transacciones sin confirmación humana

---

### Plan 3 — WhatsApp Comercial (Captura + Calificación)

**Descripción:** Captura de datos mínimos del consultante y calificación de leads.

**Para quién:** Empresas que reciben leads por WhatsApp y necesitan clasificarlos antes de derivar a ventas.

**Qué puede incluir:**
- Captura de datos: nombre, necesidad, zona, presupuesto estimado, urgencia, tipo de producto/servicio
- Preguntas inteligentes según rubro del negocio
- Clasificación frío/tibio/caliente
- Resumen comercial para el equipo de ventas

**Valor comercial:** El equipo de ventas recibe leads pre-calificados con contexto, no mensajes sueltos sin data.

**Depende de integración/configuración:**
- Preguntas específicas según el rubro del cliente
- Criterios de calificación (los define el cliente con Team360)
- Destino del resumen (email, CRM, grupo WhatsApp interno)

**No prometer como automático:**
- Integración CRM automática sin implementación específica
- Scoring automático sin definición de criterios
- Asignación automática a vendedor sin configuración

---

### Plan 4 — WhatsApp Diagnóstico AI

**Descripción:** Primera entrevista inteligente con diagnóstico útil y orientación concreta.

**Para quién:** Empresas que necesitan diagnosticar necesidades del cliente antes de ofrecer una solución.

**Qué puede incluir:**
- Conversación guiada con slots mínimos
- Preguntas según contexto detectado
- Diagnóstico útil: situación actual, problemas, oportunidades
- Orientación concreta: próximos pasos recomendados
- Preparación de contexto para atención humana

**Valor comercial:** Cada conversación genera un diagnóstico estructurado. El equipo comercial llega sabiendo qué necesita el cliente.

**Depende de integración/configuración:**
- Slots y preguntas específicas del rubro
- Criterios de diagnóstico (los define el cliente con Team360)
- Destino del diagnóstico (email, CRM, equipo interno)

**No prometer como automático:**
- Ejecución de acciones basadas en el diagnóstico
- Integración con sistemas del cliente sin implementación
- Reemplazo del juicio humano en decisiones comerciales

---

## Relación entre planes

```
Plan 1 — Profesional (FAQ + derivación)
    │
    ▼
Plan 2 — Asistente (información del negocio)
    │
    ▼
Plan 3 — Comercial (captura + calificación)
    │
    ▼
Plan 4 — Diagnóstico AI (entrevista + diagnóstico)
```

Cada plan incluye al anterior. No son excluyentes. Se pueden ofrecer combinados o por separado según necesidad del cliente.

---

## Qué NO incluye ningún plan

Ningún plan de WhatsApp inteligente incluye:

- Handoff automático con el diagnosis package de Team360
- Step-to-Action o ejecución automática de acciones
- Integración CRM automática sin configuración específica
- Campañas masivas sin proveedor/plantillas/cumplimiento
- Agenda automática sin integración real
- Reemplazo del vendedor por IA autónoma
- Garantía de resultados económicos

---

## Cómo responder comercialmente

**Cliente: "¿Pueden automatizar WhatsApp?"**
"Sí, ofrecemos paquetes de WhatsApp inteligente como servicio. Hay 4 planes según tu necesidad: desde FAQ básica con derivación humana hasta diagnóstico conversacional con clasificación de leads."

**Cliente: "¿Se integra con mi CRM?"**
"La integración con CRM puede incluirse como parte del plan, pero requiere evaluación técnica de tu CRM actual. No está disponible automáticamente para todos los clientes."

**Cliente: "¿Puede capturar leads?"**
"El Plan 3 incluye captura y calificación de leads. Los datos se entregan como resumen comercial. La integración CRM automática requiere configuración adicional."

**Cliente: "¿Esto es lo mismo que el handoff del diagnóstico?"**
"No. El WhatsApp inteligente es un servicio comercial independiente. El handoff automático dentro del diagnóstico es una capacidad técnica futura separada."

---

## Referencias

- `[[whatsapp-limites-e-integraciones]]`: Límites y diferenciación WhatsApp service vs handoff
- `[[reglas-anti-overpromise]]`: Reglas vinculantes para no prometer de más
- `[[capacidades-futuras-e-integraciones]]`: Capacidades planned_extension
- `[[team360_sales_diagnosis_package_manual]]`: Offer Decision, Service Maturity
