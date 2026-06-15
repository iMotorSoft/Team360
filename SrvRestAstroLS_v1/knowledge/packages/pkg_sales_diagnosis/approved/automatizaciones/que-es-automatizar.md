---
document_code: que_es_automatizar
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
area_key: automatizaciones
topic_key: conceptos_basicos
node_path: "/automatizaciones/que-es-automatizar"
title: "¿Qué es automatizar? Explicación simple para entender el diagnóstico"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-15
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
evidence_level: team360_definition
implementation_status: validated_on_knowledge
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
review_cycle: per_release
risk_level: low
approval_notes: >
  Documento de referencia para explicar qué significa automatizar a
  usuarios no técnicos, en lenguaje simple y con ejemplos cotidianos.
---

# ¿Qué es automatizar?

## Explicación simple

Automatizar significa **usar software para que una tarea repetitiva se haga sola**, sin que una persona tenga que hacerla manualmente cada vez.

No significa tener robots físicos ni máquinas. Significa que un programa (como los que construye Team360) se encarga de tareas que normalmente harías a mano: enviar un mensaje, registrar un dato, generar un reporte, actualizar una lista o recordar algo importante.

## Ejemplos cotidianos

| Sin automatizar | Con automatización |
|---|---|
| Cada vez que alguien escribe por WhatsApp, copias su consulta a mano a una planilla. | Cuando llega un mensaje, el sistema lo registra solo y te avisa si necesita atención. |
| Tenés que acordarte de enviar un reporte todos los lunes. | El reporte se genera y se envía automáticamente cada lunes. |
| Revisás uno por uno los mensajes para saber cuántos leads recibiste. | Un tablero te muestra en tiempo real cuántos leads llegaron, de dónde y su estado. |
| Llamás o escribís para recordar a alguien que tiene un pago pendiente. | El sistema envía el recordatorio automático según las reglas que definiste. |

## ¿Qué NO es automatizar en Team360?

- **No es un robot físico.** Team360 no tiene brazos robóticos ni hace tareas del mundo físico (cocinar, limpiar, reparar, transportar objetos).
- **No es magia.** Para automatizar necesitamos entender el proceso, los datos disponibles y cómo se accede a los sistemas involucrados.
- **No todo se puede automatizar de entrada.** El diagnóstico nos ayuda a identificar qué partes de un proceso se pueden digitalizar y automatizar, y cuáles requieren intervención humana.
- **No es inmediato.** Algunas automatizaciones son rápidas (ej: registro automático de consultas), otras requieren configuración, integraciones y pruebas.

## ¿Qué se puede automatizar típicamente?

1. **Registro y orden de datos** — capturar información que llega por WhatsApp, email o formulario y guardarla ordenada automáticamente.
2. **Avisos y recordatorios** — enviar notificaciones cuando algo cambia, cuando vence un plazo o cuando alguien necesita actuar.
3. **Respuestas rápidas** — responder preguntas frecuentes o dar información básica sin intervención humana.
4. **Reportes y KPI** — generar tableros con métricas actualizadas sin tener que armarlos a mano.
5. **Seguimiento de tareas** — asignar, escalar y cerrar tareas según reglas predefinidas.
6. **Coordinación entre personas y sistemas** — conectar pasos que hoy requieren que alguien copie información de un lado a otro.

## ¿Qué necesita Team360 para diagnosticar?

Para saber si un proceso se puede automatizar, necesitamos entender:

- **¿Qué tarea querés mejorar?** (ej: atender consultas de WhatsApp, organizar pedidos, enviar reportes)
- **¿Qué herramientas usás hoy?** (ej: WhatsApp, Excel, un ERP, papel)
- **¿Con qué frecuencia se hace?** (ej: todos los días, una vez por semana)
- **¿Hay reglas claras o cada caso es distinto?**
- **¿Qué tan sensible es la información?** (ej: datos públicos, datos de clientes, información financiera)

Con esa información, el diagnóstico puede orientar qué es automatizable, qué requiere revisión humana y qué capacidades de Team360 aplican.

## Referencias

- `[[team360_sales_diagnosis_package_manual]]`: Clasificación de automatización
- `[[reglas-anti-overpromise]]`: Qué no prometer
- `[[alcance-productivo-inicial]]`: Alcance del diagnóstico
