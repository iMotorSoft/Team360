---
document_code: capacidades_futuras_e_integraciones
document_type: reference
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
area_key: integraciones
topic_key: capacidades_futuras
node_path: "/integraciones/capacidades-futuras"
title: "Capacidades futuras e integraciones — estado y respuesta comercial"
visibility: internal
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
  - breaking_points_lab_results
implementation_status: prototype
commercial_status: future_package
service_maturity: PAQUETE_FUTURO
offer_decision:
  - future_opportunity
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
  Lista de capacidades futuras con estado actual, por qué no vender como
  listo y cómo responder comercialmente. Cada capacidad está marcada como
  PAQUETE_FUTURO o planned_extension. Ninguna está disponible como
  servicio productivo general.
---

# Capacidades futuras e integraciones

## Propósito

Este documento lista las capacidades que están en hoja de ruta, planeadas como extensión futura (planned_extension) o en etapa de laboratorio. Ninguna debe venderse como disponible productivamente.

Para cada capacidad se indica:
- Estado actual
- Por qué no vender como listo
- Condición para considerarla futura
- Cómo responder ante preguntas comerciales

---

## Step-to-Action

**Estado actual:** planned_extension. No implementado en producción.

**Por qué no vender como listo:** Step-to-Action requiere ejecución automática de acciones sobre sistemas externos. Esa capacidad no está desarrollada. El MVP actual termina en orientación concreta (concrete_orientation), no en ejecución.

**Condición para considerarla futura:** Cuando exista un worker productivo que ejecute acciones reales sobre APIs o sistemas externos con autorización explícita.

**Cómo responder:**
- "Step-to-Action es una extensión planificada. Hoy ofrecemos diagnóstico y orientación concreta, pero la ejecución automática de pasos no está disponible."
- Si el cliente pregunta "¿puede ejecutar acciones?": "No. El diagnóstico actual sugiere pasos que el vendedor ejecuta manualmente."

---

## Lead capture productivo general

**Estado actual:** planned_extension. La captura de leads no está implementada como servicio productivo general.

**Por qué no vender como listo:** Lead capture requiere integración con CRM, almacenamiento de datos de contacto y flujo de continuidad comercial. Ninguno de esos componentes está operativo como servicio general.

**Condición para considerarla futura:** Cuando exista un flujo aprobado de captura de datos, storage y handoff a CRM con consentimiento explícito del usuario.

**Cómo responder:**
- "Lead capture está planificada como extensión futura. Hoy no guardamos leads de forma automática."
- Si el cliente insiste: "Podemos evaluar tu caso específico, pero como capacidad general no está disponible."

---

## WhatsApp handoff automático

**Estado actual:** planned_extension. El handoff automático desde el diagnosis package hacia WhatsApp no está implementado.

**Por qué no vender como listo:** WhatsApp handoff requiere: (1) generación de diagnostic_code, (2) URL o mensaje automático con contexto, (3) worker de continuidad comercial. Ninguno existe productivamente.

**Importante — NO confundir con WhatsApp service offer:** Team360 puede ofrecer paquetes de WhatsApp inteligente como servicio comercial independiente (ver `[[paquetes-whatsapp-inteligente]]`). Eso NO es lo mismo que el handoff automático dentro del diagnosis package. Son líneas separadas.

**Cómo responder:**
- "El WhatsApp handoff automático dentro del diagnóstico es una capacidad futura. Pero podemos ofrecerte un paquete de WhatsApp inteligente como servicio aparte."
- Ver `[[whatsapp-limites-e-integraciones]]` para la diferenciación completa.

---

## Diagnostic code

**Estado actual:** planned_extension. El código único de diagnóstico por conversación no está implementado.

**Por qué no vender como listo:** Diagnostic_code requiere un generador de IDs, asociación a conversación y trazabilidad post-diagnóstico. No existe como servicio.

**Cómo responder:**
- "El código de diagnóstico único es una extensión planificada. Hoy el resultado del diagnóstico es la clasificación de oportunidad, no un código de seguimiento."

---

## CRM handoff

**Estado actual:** planned_extension. La integración automática con CRM para crear/actualizar contactos no está disponible como servicio general.

**Por qué no vender como listo:** CRM handoff requiere conectores específicos por CRM, autenticación, mapeo de campos y flujo aprobado. No existe como servicio general.

**Cómo responder:**
- "La integración automática con CRM no está disponible como servicio general. Existen integraciones específicas para casos evaluados comercialmente."

---

## Workflow execution

**Estado actual:** planned_extension. La ejecución automática de workflows no está implementada.

**Por qué no vender como listo:** La ejecución automática sobre sistemas externos requiere workers, APIs, autorización y monitoreo. Ninguno existe productivamente.

**Cómo responder:**
- "La ejecución automática de workflows es una capacidad futura. Hoy el diagnóstico termina en recomendación, no en ejecución."

---

## Campaign automation

**Estado actual:** planned_extension. Las campañas automáticas por WhatsApp no están disponibles como servicio general.

**Por qué no vender como listo:** Campaign automation requiere: (1) proveedor de mensajería configurado, (2) plantillas aprobadas, (3) cumplimiento de políticas, (4) segmentación. Ninguno está operativo como servicio general.

**Cómo responder:**
- "Las campañas automáticas por WhatsApp no están disponibles. Requieren proveedor, plantillas aprobadas y configuración específica."

---

## Agenda automation

**Estado actual:** planned_extension. La agenda/turnos automática no está disponible como servicio general.

**Por qué no vender como listo:** Agenda automation requiere integración con calendario, confirmación bidireccional, recordatorios y manejo de reprogramación. No existe como servicio general.

**Cómo responder:**
- "La agenda automática no está disponible como servicio general. Existen soluciones específicas evaluables caso por caso."

---

## Resumen: capacidades HOY vs FUTURAS

| Capacidad | HOY | FUTURA | Notas |
|-----------|-----|--------|-------|
| Diagnóstico conversacional | ✅ Sí | — | Core del producto actual |
| Orientación concreta | ✅ Sí | — | Post-diagnóstico |
| FAQ inteligente | ✅ Sí | — | Si el contenido está cargado |
| Captura de consulta | ✅ Sí | — | Si está en el flujo definido |
| Derivación humana con resumen | ⚠️ Parcial | — | Depende del paquete/proyecto |
| Step-to-Action | ❌ No | ✅ planned | Ejecución automática futura |
| Lead capture general | ❌ No | ✅ planned | Captura productiva futura |
| WhatsApp handoff automático | ❌ No | ✅ planned | Handoff automático futuro |
| Diagnostic code | ❌ No | ✅ planned | Código de seguimiento futuro |
| CRM handoff automático | ❌ No | ✅ planned | Integración CRM futura |
| Workflow execution | ❌ No | ✅ planned | Ejecución sobre APIs futura |
| Campaign automation | ❌ No | ✅ planned | Campañas automáticas futuras |
| Agenda automation | ❌ No | ✅ planned | Agenda/turnos automática futura |
| WhatsApp service packages | ✅ Sí* | — | Como servicio comercial con alcance |

*WhatsApp service packages están disponibles como servicio comercial con alcance definido (ver `[[paquetes-whatsapp-inteligente]]`). No confundir con WhatsApp handoff automático.

---

## Referencias

- `[[reglas-anti-overpromise]]`: Reglas vinculantes para no prometer de más
- `[[paquetes-whatsapp-inteligente]]`: WhatsApp como servicio comercial
- `[[whatsapp-limites-e-integraciones]]`: Límites y diferenciación WhatsApp
- `[[team360_sales_diagnosis_package_manual]]`: Offer Decision, Service Maturity
