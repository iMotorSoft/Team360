---
document_code: procesos_fisicos_vs_digitales
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
area_key: industrias
topic_key: procesos_fisicos_vs_digitales
node_path: "/industrias/procesos-fisicos-vs-digitales"
title: "Procesos físicos vs. digitales: qué puede automatizar Team360"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-15
access_tags:
  - public
  - ejecutivo_comercial
evidence_level: team360_definition
implementation_status: validated_on_knowledge
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
review_cycle: per_release
risk_level: low
approval_notes: >
  Documento para reconducir casos donde el usuario describe una tarea
  física (cocinar, reparar, construir, transportar, limpiar) hacia
  los procesos digitales que la rodean.
---

# Procesos físicos vs. digitales

## El límite de la automatización digital

Team360 automatiza **procesos digitales, administrativos y de coordinación**. No realiza acciones físicas.

Si la tarea que querés mejorar implica mover objetos, reparar cosas, construir, cocinar, transportar físicamente, limpiar o cambiar partes de un vehículo o máquina, **Team360 no ejecuta esa acción física**.

## Lo que SÍ se puede automatizar alrededor de una tarea física

Aunque la tarea central sea física, casi siempre hay procesos digitales alrededor que se pueden automatizar:

### Ejemplo: cambiar una rueda de auto

| Acción física (no automatizable por Team360) | Proceso digital alrededor (sí automatizable) |
|---|---|
| Cambiar físicamente la rueda | Registrar el incidente: quién reportó, qué vehículo, qué ocurrió |
| | Enviar una solicitud de asistencia al responsable |
| | Notificar al cliente o equipo que ya se asignó la tarea |
| | Llevar un checklist de los pasos realizados |
| | Recordatorio de mantenimiento preventivo programado |
| | Seguimiento del estado: pendiente, en curso, resuelto |
| | Reporte mensual de incidentes, tiempos de respuesta y costos |

### Ejemplo: hacer tortas para vender

| Acción física | Proceso digital automatizable |
|---|---|
| Hornear la torta | Registrar pedidos entrantes |
| Decorar | Gestionar calendario de entregas |
| Entregar | Enviar confirmaciones y recordatorios al cliente |
| | Llevar control de stock de ingredientes |
| | Generar reportes de ventas por período |

### Ejemplo: reparar equipos electrónicos

| Acción física | Proceso digital automatizable |
|---|---|
| Abrir y reparar el equipo | Registrar orden de servicio |
| Probar funcionamiento | Asignar técnico según disponibilidad |
| | Notificar al cliente avances |
| | Control de garantías y repuestos |
| | Encuesta de satisfacción automática |

## Cómo preguntar para reconducir

Cuando un usuario describe una tarea física, el diagnóstico debe:

1. **Reconocer** que la tarea principal es física y no automatizable directamente.
2. **Separar** los procesos digitales alrededor: registro, coordinación, avisos, reportes, seguimiento.
3. **Preguntar** sobre la parte administrativa: ¿cómo registran los pedidos? ¿cómo se enteran de que algo pasó? ¿cómo llevan el control?
4. **Ofrecer** empezar por la parte digital más simple.

## Regla general

> Si la tarea implica mover, transformar o reparar objetos físicos, Team360 puede automatizar la **gestión, coordinación y registro** alrededor de esa tarea, pero no la tarea física misma.

## Referencias

- `[[que-es-automatizar]]`: Explicación básica de automatización
- `[[reglas-anti-overpromise]]`: No prometer lo que no se puede hacer
