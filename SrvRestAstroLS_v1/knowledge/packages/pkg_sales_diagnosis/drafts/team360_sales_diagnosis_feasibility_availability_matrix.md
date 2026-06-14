---
document_code: team360_sales_diagnosis_feasibility_availability_matrix
status: draft
ingestion_status: not_ready
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360
workspace_code: team360_live
package_code: pkg_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: scoring
topic_key: feasibility_availability_matrix
document_type: reference
visibility: internal
access_tags:
  - internal
  - package:sales_diagnosis
  - topic:feasibility
  - topic:availability
locale: es
version: "0.1"
title: "Matriz de factibilidad técnica y disponibilidad comercial"
source_type: markdown
node_path: "/scoring/feasibility-availability-matrix"
risk_level: medium
step_to_action_status: planned_extension
approval_notes: >
  Borrador inicial de la matriz operativa de factibilidad y
  disponibilidad para pkg_sales_diagnosis. Complementa el package
  manual y la guía de slots. No está aprobado para ingesta.
  Sirve como guía para que el asistente clasifique casos con
  consistencia entre factibilidad técnica, operativa y disponibilidad
  comercial. Debe revisarse con GPT-5.5 antes de promover a approved/.
---

# Matriz de factibilidad técnica y disponibilidad comercial

> Estado draft: este documento está en estado draft. No debe ingerirse
> ni moverse a `approved/` hasta pasar revisión editorial, validación
> de límites comerciales y prueba conversacional.

---

## L0 Abstract

Esta matriz define cómo Vera / el asistente de diagnóstico de Team360
evalúa y clasifica casos reales de automatización, IA, integración y
mejora operativa separando de forma explícita:

- **Factibilidad técnica**: si el proceso puede automatizarse con la
  tecnología disponible.
- **Factibilidad operativa**: si el usuario tiene los accesos, permisos,
  datos y condiciones organizacionales para implementarlo.
- **Disponibilidad comercial**: si Team360 ofrece hoy el servicio como
  paquete o si requiere validación, revisión humana, desarrollo futuro
  o no se recomienda.

La matriz convierte el principio de diagnóstico amplio en reglas
prácticas para que retrieval, modelos y clasificación operen con
consistencia. No reemplaza la revisión humana ni activa capacidades
comerciales automáticas.

---

## Propósito

Team360 busca ser el mejor diagnosticador posible de casos de
automatización. Para eso, Vera no debe limitarse a decir si existe
o no un paquete disponible. Primero debe diagnosticar la factibilidad
técnica y operativa del caso que plantea el usuario, incluso cuando
Team360 no tenga un paquete cerrado para ese caso.

Este documento provee la matriz operativa que permite:

- Evaluar dimensiones de factibilidad de forma separada y consistente.
- Clasificar cada caso en una categoría de diagnóstico.
- Determinar si requiere más información, revisión humana o no es
  recomendable.
- Generar respuestas que orienten al usuario sin prometer lo que no
  está disponible.
- Mantener separación entre lo factible, lo vendible hoy, lo que
  necesita validación y lo que requiere contacto humano.

---

## Precedencia documental

- Esta matriz prevalece para `technical_feasibility`,
  `operational_feasibility`, `availability_status`,
  `service_maturity`, `offer_decision` y `diagnosis_category`.
- Si hay riesgo de seguridad, credenciales, MFA, QR, Face ID, datos
  sensibles, bloqueo o revisión humana, prevalece
  [[team360_sales_diagnosis_security_hitl_policy]].
- Para estilo conversacional, prevalece
  [[team360_sales_diagnosis_response_playbook]].
- Para precio, garantías, contacto y objeciones comerciales, prevalece
  [[team360_sales_diagnosis_commercial_objections]].

---

## Principio rector

Tres reglas fundamentales:

1. **Factible técnicamente no significa disponible hoy como paquete.**
   Vera puede diagnosticar que un proceso es automatizable sin que
   Team360 ofrezca hoy un servicio estándar para implementarlo.

2. **Disponible hoy no significa que no requiera validación.**
   Incluso los paquetes existentes pueden necesitar verificación de
   accesos, datos o condiciones operativas antes de comprometer
   una implementación.

3. **No disponible como paquete no significa que no pueda tener
   solución.** Team360 puede orientar, diseñar una solución a medida
   o explorar el caso como oportunidad futura sin generar expectativas
   comerciales incorrectas.

---

## Dimensiones de evaluación

### A. technical_feasibility

Evalúa si el proceso es técnicamente automatizable con las
capacidades actuales de Team360.

| Valor | Significado |
|-------|-------------|
| `high` | El proceso es claramente automatizable. Existen APIs, datos accesibles y reglas definidas. |
| `medium` | Es probablemente automatizable, pero hay factores técnicos que requieren validación. |
| `low` | La automatización es difícil técnicamente. Puede requerir desarrollo a medida, integración compleja o soluciones no estándar. |
| `unknown` | No hay suficiente información técnica para evaluar. Faltan datos sobre herramientas, plataformas o APIs. |
| `not_feasible` | Técnicamente no es viable automatizar con los medios disponibles. |

**Criterios:**

- Existencia y accesibilidad de datos fuente.
- Disponibilidad de APIs documentadas y estables.
- Reglas de negocio claras y estables.
- Volumen manejable dentro de límites operativos.
- Posibilidad de integración sin violar términos de servicio.
- Ausencia o presencia de barreras técnicas (MFA, captcha, rate limiting).
- Estabilidad de la plataforma origen.

### B. operational_feasibility

Evalúa si el usuario y su organización pueden adoptar y sostener
la automatización.

| Valor | Significado |
|-------|-------------|
| `high` | Proceso claro, responsable definido, accesos disponibles y mínima dependencia humana. |
| `medium` | El proceso es operable pero requiere coordinación, cambios organizacionales o aprobaciones. |
| `low` | Alta dependencia humana, procesos no documentados o cambios organizacionales profundos. |
| `unknown` | No hay información operativa suficiente. Se desconoce quién ejecuta, cada cuánto o con qué recursos. |
| `blocked` | Existe una barrera operativa concreta que impide la automatización: falta de acceso, falta de presupuesto, restricción de política interna. |

**Criterios:**

- Proceso documentado y repetible.
- Responsable identificado con capacidad de decisión.
- Frecuencia y volumen conocidos.
- Dependencia humana crítica.
- Cambios organizacionales requeridos.
- Riesgo operativo de interrupción.
- Necesidad de aprobación interna de terceros.
- Disponibilidad de permisos y accesos.

### C. availability_status

Indica si Team360 ofrece hoy el servicio como paquete estándar.

| Valor | Significado |
|-------|-------------|
| `available_now` | Team360 ofrece hoy el servicio con alcance y condiciones definidas. Hay paquete o servicio disponible. |
| `available_with_validation` | El servicio existe pero requiere validación de accesos, datos o alcance antes de ofrecerlo. |
| `feasible_not_packaged` | El caso es factible pero no está empaquetado como servicio estándar. Puede requerir solución a medida. |
| `future_opportunity` | Es relevante para el roadmap pero no debe ofrecerse como servicio actual. |
| `not_available` | El servicio no está disponible hoy. No hay capacidad de delivery inmediata. |
| `not_recommended` | No se recomienda automatizar por riesgo, costo o impacto. |

`available_with_validation` no significa `feasible_not_packaged`.
Indica que existe una línea de trabajo o servicio, pero requiere
validación antes de confirmar alcance. Usar `feasible_not_packaged`
solo cuando el caso no pertenece a disponibilidad inmediata ni a un
servicio validable actual.

### D. service_maturity

Madurez del servicio según evidencia y capacidad de delivery.

| Valor | Significado |
|-------|-------------|
| `CORE_VALIDADO` | Servicio con evidencia suficiente, alineado al foco inicial. Capacidad defendible para oferta principal. |
| `PILOTO_VALIDADO` | Servicio probado o factible para piloto con límites claros. No maduro como core repetible. |
| `OPORTUNIDAD` | Interés comercial o dirección posible sin evidencia suficiente para delivery estándar. |
| `PAQUETE_FUTURO` | Línea relevante que merece diseño propio o roadmap antes de activarse como oferta. |
| `NO_OFRECER_AUN` | Tema fuera de alcance actual, riesgoso o no validado para comercializar ahora. |

### E. offer_decision

Decisión comercial responsable para el caso diagnosticado.

| Valor | Significado |
|-------|-------------|
| `sellable_now` | Team360 puede ofrecerlo hoy con alcance y límites claros. |
| `pilot` | Puede ofrecerse como piloto controlado con alcance acotado. |
| `needs_more_info` | Se necesita más información técnica u operativa antes de decidir. |
| `human_review_required` | Requiere evaluación humana antes de responder, presupuestar o ejecutar. |
| `future_opportunity` | Interesante para roadmap, no vendible como oferta actual. |
| `do_not_offer` | No ofrecer activamente. Usar para descarte informado. |

### F. diagnosis_category

Categoría final del diagnóstico que integra las dimensiones anteriores.

| Categoría | Significado |
|-----------|-------------|
| `available_now` | El caso entra en paquete o servicio disponible hoy. |
| `feasible_not_packaged` | Factible pero no disponible como paquete cerrado. |
| `feasible_needs_more_info` | En principio factible, faltan datos para validar. |
| `special_case_human_review` | Caso particular que requiere charla con el equipo. |
| `future_opportunity` | Interesante pero no debe prometerse como oferta actual. |
| `not_recommended` | No recomendable por riesgo, costo o impacto. |

---

## Matriz principal

La siguiente tabla relaciona las dimensiones de evaluación y orienta
la respuesta recomendada para cada combinación típica.

| # | technical_feasibility | operational_feasibility | availability_status | service_maturity | offer_decision | diagnosis_category | human_review_required | Respuesta recomendada |
|---|----------------------|------------------------|--------------------|-----------------|----------------|-------------------|---------------------|----------------------|
| 1 | high | high | available_now | CORE_VALIDADO | sellable_now | available_now | false | "Por lo que describís, este caso encaja con una línea de trabajo disponible de Team360. La factibilidad inicial parece alta, y el siguiente paso sería validar datos y accesos." |
| 2 | high | medium | available_with_validation | PILOTO_VALIDADO | pilot | available_now | false | "El caso parece factible y existe una línea de trabajo aplicable, pero antes de confirmar alcance conviene validar aspectos operativos como accesos y frecuencia." |
| 3 | medium | high | feasible_not_packaged | OPORTUNIDAD | needs_more_info | feasible_not_packaged | false | "Este caso no está dentro de nuestra disponibilidad inmediata como paquete cerrado, pero sí parece posible diseñar una solución. Antes de prometer implementación, conviene revisar datos y proceso." |
| 4 | unknown | high | not_available | OPORTUNIDAD | needs_more_info | feasible_needs_more_info | false | "En principio parece factible, pero faltan datos técnicos para validarlo bien. Para avanzar habría que conocer herramientas, datos y frecuencia del proceso." |
| 5 | high | low/blocked | feasible_not_packaged | PILOTO_VALIDADO | human_review_required | special_case_human_review | true | "El proceso es técnicamente viable, pero la operación presenta desafíos. Este caso es más particular y conviene conversarlo para entender restricciones y objetivos." |
| 6 | low | low | not_recommended | NO_OFRECER_AUN | do_not_offer | not_recommended | true | "Con la información actual, no sería responsable recomendar automatizar este proceso sin revisar riesgos, controles y consecuencias. Puede requerir rediseño del proceso o intervención humana." |
| 7 | medium | unknown | future_opportunity | PAQUETE_FUTURO | future_opportunity | future_opportunity | false | "Es una oportunidad interesante, pero hoy no debería tratarse como disponibilidad inmediata. Puede quedar registrada como caso futuro o evaluarse en una revisión más específica." |
| 8 | not_feasible | blocked | not_recommended | NO_OFRECER_AUN | do_not_offer | not_recommended | true | "Este proceso no reúne las condiciones técnicas ni operativas para automatizarse con los medios actuales. No recomendamos avanzar sin cambios significativos en el proceso o la infraestructura." |

### Reglas para usar la matriz

- La matriz orienta la clasificación, no es un árbol de decisión rígido.
- Si hay señales de riesgo (MFA, datos sensibles, cumplimiento),
  priorizar `human_review_required` por encima de otras dimensiones.
- Si la factibilidad técnica y operativa son altas pero el servicio
  no está disponible, clasificar como `feasible_not_packaged`.
- Si falta información técnica, clasificar como `feasible_needs_more_info`.
- Los casos con `human_review_required: true` deben priorizar revisión
  humana antes de cualquier oferta comercial.

---

## Patrones de respuesta

Todas las respuestas deben:

1. **Dar valor diagnóstico primero.** Antes de pedir contacto, ofrecer
   una orientación útil sobre el caso del usuario.
2. **No pedir datos personales al inicio.** WhatsApp, email, nombre
   y empresa solo si el usuario pide contacto o ya recibió valor.
3. **Usar tono profesional sin venta agresiva.** Diagnosticar no es
   vender. La venta llega después si el caso lo justifica.
4. **No activar Step-to-Action.** Step-to-Action, lead capture,
   diagnostic_code y WhatsApp handoff son capacidades futuras.

### A. available_now

> Por lo que describís, este caso encaja con una línea de trabajo
> disponible de Team360. La factibilidad inicial parece
> [alta/media], y el siguiente paso sería validar
> [datos/accesos/proceso] para confirmar alcance.

### B. feasible_not_packaged

> Este caso no está dentro de nuestra disponibilidad inmediata como
> paquete cerrado, pero sí parece posible diseñar una solución.
> Antes de prometer implementación, conviene revisar
> [datos/proceso/integraciones] para entender mejor el alcance.

### C. feasible_needs_more_info

> En principio parece factible, pero faltan datos técnicos y
> operativos para validarlo bien. Para avanzar habría que conocer
> [herramientas/datos/frecuencia/reglas/accesos] del proceso actual.

### D. special_case_human_review

> Este caso es más particular y conviene conversarlo para entender
> restricciones, riesgos y objetivos. Podemos coordinar una charla
> virtual con alguien del equipo si querés avanzar.

### E. future_opportunity

> Es una oportunidad interesante, pero hoy no debería tratarse como
> disponibilidad inmediata. Puede quedar registrada como caso futuro
> o evaluarse en una revisión más específica del roadmap.

### F. not_recommended

> Con la información actual, no sería responsable recomendar automatizar
> este proceso sin revisar riesgos, controles y consecuencias. Puede
> requerir rediseño del proceso o intervención humana para ser viable.

---

## Human review required

`human_review_required` debe activarse cuando el caso presente
cualquiera de las siguientes condiciones:

### Condiciones de activación

- **Credenciales compartidas**: el usuario menciona que varias personas
  usan la misma cuenta o contraseña.
- **MFA / doble factor**: el acceso a la plataforma requiere
  autenticación multifactor.
- **Datos personales sensibles**: el proceso maneja datos de salud,
  datos biométricos, información de menores o datos especialmente
  protegidos por regulación.
- **Datos financieros**: cuentas bancarias, transacciones, conciliaciones
  financieras, facturación crítica.
- **Decisiones legales**: automatización que afecta contratos,
  cumplimiento normativo, obligaciones legales o derechos de terceros.
- **Acciones irreversibles**: pagos, envíos, cancelaciones, baja de
  servicios, eliminación de datos.
- **Scraping riesgoso**: extracción automatizada de datos de plataformas
  sin API, con riesgo de bloqueo o violación de términos de servicio.
- **Plataformas críticas**: ERP, sistemas contables, plataformas
  bancarias, sistemas de salud, gobierno.
- **Impacto económico alto**: automatización que puede generar pérdidas
  significativas si falla.
- **Cumplimiento / regulación**: sectores regulados (financiero, salud,
  legal, seguros) o procesos sujetos a auditoría.
- **Clientes finales**: automatización que afecta directamente la
  experiencia o los datos de clientes.
- **Falta de claridad sobre permisos**: no está claro quién autoriza
  el acceso o si existe aprobación interna.

### Regla de activación

Si **una o más** condiciones están presentes, el asistente debe
marcar `human_review_required: true` independientemente de las otras
dimensiones de factibilidad. La revisión humana debe ocurrir antes
de cualquier oferta comercial, presupuesto o compromiso de
implementación.

---

## Ejemplos por tipo de caso

### CRM + WhatsApp

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | high |
| availability_status | available_now |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: asume CRM con API, WhatsApp Business Cloud API disponible y
accesos definidos. Si hay credenciales compartidas o MFA, subir a
human_review_required.

### Facebook Ads + leads

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | medium |
| availability_status | available_with_validation |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: requiere validar acceso a la cuenta publicitaria, conexión CRM
y flujo de leads. Si la cuenta es compartida, marcar
human_review_required.

### Excel / Google Sheets

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | high |
| availability_status | available_now |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: si la planilla contiene datos financieros, salud o legales,
evaluar human_review_required.

### Reportes KPI

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | high |
| availability_status | available_now |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: reportes operativos simples con datos accesibles. Si los datos
son financieros o regulatorios, evaluar human_review_required.

### RAG sobre documentos propios

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | medium |
| availability_status | available_with_validation |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: RAG es factible si los documentos son digitales, claros y hay
permisos definidos. Si contienen datos sensibles (salud, legal,
menores), marcar human_review_required.

### Atención al cliente

| Campo | Valor |
|-------|-------|
| technical_feasibility | high |
| operational_feasibility | high |
| availability_status | available_now |
| diagnosis_category | available_now |
| human_review_required | false |

Nota: depende del canal, volumen y tipo de consultas. Si involucra
datos sensibles o decisiones automáticas con impacto al cliente,
marcar human_review_required.

### Browser automation

| Campo | Valor |
|-------|-------|
| technical_feasibility | medium |
| operational_feasibility | low |
| availability_status | feasible_not_packaged |
| diagnosis_category | special_case_human_review |
| human_review_required | true |

Nota: browser automation tiene riesgo de bloqueo, MFA, cambios de
interfaz y términos de servicio. Requiere revisión humana por defecto.

### Integraciones con ERP

| Campo | Valor |
|-------|-------|
| technical_feasibility | medium |
| operational_feasibility | low |
| availability_status | feasible_not_packaged |
| diagnosis_category | special_case_human_review |
| human_review_required | true |

Nota: las integraciones con ERP requieren acceso, permisos, estabilidad
de API y conocimiento del negocio. Marcar human_review_required.

### Finanzas / bancos

| Campo | Valor |
|-------|-------|
| technical_feasibility | medium |
| operational_feasibility | low |
| availability_status | future_opportunity |
| diagnosis_category | future_opportunity |
| human_review_required | true |

Nota: reportes financieros simples pueden ser core. Conciliaciones
bancarias, contabilidad avanzada o automatización financiera sensible
requieren human_review_required y deben tratarse como future_opportunity
salvo validación específica. Pagos, aprobaciones, rechazos,
inversiones o decisiones financieras automáticas deben clasificarse
como `not_recommended` o `blocked` si no existe supervisión humana,
autorización explícita y marco de cumplimiento.

### Trading bot

| Campo | Valor |
|-------|-------|
| technical_feasibility | medium |
| operational_feasibility | low |
| availability_status | not_recommended |
| diagnosis_category | not_recommended |
| human_review_required | true |

Nota: salvo validación muy específica con revisión humana y legal,
no ofrecer. Riesgo financiero, regulatorio y operativo alto.

### Marketplaces complejos

| Campo | Valor |
|-------|-------|
| technical_feasibility | medium |
| operational_feasibility | low |
| availability_status | future_opportunity |
| diagnosis_category | future_opportunity |
| human_review_required | true |

Nota: depende de la plataforma, estabilidad, MFA, políticas de
automatización y riesgo de cuenta. Marcar human_review_required por
defecto.

### Casos legales o sensibles

| Campo | Valor |
|-------|-------|
| technical_feasibility | unknown |
| operational_feasibility | low |
| availability_status | not_recommended |
| diagnosis_category | not_recommended |
| human_review_required | true |

Nota: cualquier caso que involucre decisiones legales, cumplimiento,
datos de menores, salud o información gubernamental debe activar
human_review_required. No ofrecer sin revisión humana explícita.

---

## Relación con slots

Cada dimensión de la matriz se corresponde con slots definidos en
[[team360_sales_diagnosis_slots_questions]]:

| Slot | Dimensión de la matriz | Propósito |
|------|----------------------|-----------|
| `technical_feasibility` | A. technical_feasibility | Determinar si el proceso es técnicamente automatizable. |
| `operational_feasibility` | B. operational_feasibility | Determinar si el usuario puede adoptar la automatización. |
| `availability_status` | C. availability_status | Indicar disponibilidad como paquete/servicio. |
| `diagnosis_category` | F. diagnosis_category | Clasificación integrada del caso. |
| `package_fit` | - | Correspondencia entre el caso y un paquete existente. |
| `requires_more_info` | - | Marcar si faltan datos para validar. |
| `human_review_required` | Human review required | Activar si hay condiciones de riesgo. |
| `future_opportunity_reason` | - | Registrar por qué es oportunidad futura. |
| `not_recommended_reason` | - | Registrar por qué no se recomienda. |
| `immediate_availability` | C. availability_status | Indicar si hay disponibilidad hoy. |
| `validation_needed_reason` | - | Describir qué falta para validar. |

Los slots se extraen del texto libre o se infieren durante el
diagnóstico. La matriz proporciona los criterios para inferirlos
de forma consistente.

---

## Límites

- **La matriz orienta la conversación, no reemplaza revisión humana.**
  Los casos marcados con `human_review_required` deben pasar por
  evaluación del equipo antes de cualquier oferta.

- **No convierte una oportunidad futura en oferta activa.**
  Clasificar un caso como `future_opportunity` no autoriza a venderlo
  como servicio disponible. Debe quedar claro que no es oferta actual.

- **No autoriza pedir datos personales al inicio.**
  La matriz ayuda a diagnosticar, no a capturar leads. WhatsApp, email,
  nombre y empresa no se piden durante el diagnóstico inicial.

- **No activa Step-to-Action.**
  Step-to-Action, lead capture, diagnostic_code y WhatsApp handoff
  son capacidades futuras. La matriz no las activa ni las presupone.

- **No reemplaza política de seguridad / HITL.**
  Las reglas de seguridad, MFA, credenciales y supervisión humana
  definidas en el package manual y la política de seguridad tienen
  prioridad sobre cualquier recomendación de la matriz.

- **No debe usarse para prometer tiempos, precios o implementación
  garantizada.** La matriz clasifica factibilidad y disponibilidad;
  no es una herramienta de cotización ni de planificación de delivery.

---

## Historial de cambios

| Fecha | Cambio | Autor |
|------|--------|-------|
| 2026-06-14 | Creación draft inicial para producción por etapas. | Team360 |
