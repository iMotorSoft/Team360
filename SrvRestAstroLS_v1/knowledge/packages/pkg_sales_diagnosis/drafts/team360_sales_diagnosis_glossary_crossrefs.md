---
document_code: team360_sales_diagnosis_glossary_crossrefs
status: draft
ingestion_status: not_ready
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360
workspace_code: team360_live
package_code: pkg_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: glosario
topic_key: glossary_crossrefs
document_type: reference
visibility: internal
access_tags:
  - internal
  - package:sales_diagnosis
  - topic:glossary
  - topic:crossrefs
locale: es
version: "0.1"
title: "Glosario y referencias cruzadas del paquete de diagnóstico"
source_type: markdown
node_path: "/glosario/glossary-crossrefs"
risk_level: low
step_to_action_status: planned_extension
approval_notes: >
  Borrador inicial del glosario y referencias cruzadas para
  pkg_sales_diagnosis. Define vocabulario estandar, categorias
  normalizadas, slots, capacidades futuras y precedencia documental.
  No esta aprobado para ingesta. Debe revisarse con GPT-5.5 antes
  de promover a approved/.
---

# Glosario y referencias cruzadas del paquete de diagnóstico

> Este documento está en estado draft. No debe ingerirse ni moverse
> a `approved/` hasta pasar revisión editorial, validación de límites
> y prueba conversacional.

---

## L0 Abstract

Este documento define los términos, categorías, slots, referencias
cruzadas y reglas de precedencia que unifican el vocabulario de los
8 documentos draft del paquete `pkg_sales_diagnosis`.

El objetivo es evitar ambigüedad en ingesta, retrieval, clasificación
y generación de respuestas, asegurando que el asistente use términos
consistentes sin importar qué documento consultó para formar su
respuesta.

---

## Propósito

- **Unificar vocabulario**: todos los documentos del paquete usan
  las mismas definiciones para los mismos términos.
- **Evitar que el modelo confunda factibilidad con disponibilidad**:
  términos como `technical_feasibility` y `availability_status` tienen
  definiciones separadas y no intercambiables.
- **Estabilizar valores de slots**: los valores canónicos de
  `diagnosis_category`, `offer_decision`, `service_maturity` y otros
  son consistentes entre documentos.
- **Sostener respuestas consistentes**: el asistente recibe el mismo
  significado para cada concepto sin importar la fuente.
- **Ayudar a futura ingesta**: facilita el mapeo de campos,
  chunking semántico y retrieval de fragmentos.
- **Facilitar QA documental**: cualquier revisor puede verificar que
  los 8 documentos usan la misma terminología.
- **Evitar que capacidades futuras aparezcan como activas**:
  `planned_extension` queda definido de forma explícita.

---

## Regla de uso

1. Si hay conflicto con seguridad, credenciales, MFA, QR, Face ID,
   datos sensibles, bloqueo o revisión humana, prevalece
   [[team360_sales_diagnosis_security_hitl_policy]].
2. Si hay conflicto con factibilidad, disponibilidad,
   service_maturity, offer_decision o diagnosis_category, prevalece
   [[team360_sales_diagnosis_feasibility_availability_matrix]].
3. Si hay conflicto de estilo conversacional, prevalece
   [[team360_sales_diagnosis_response_playbook]].
4. Si hay conflicto comercial sobre precio, garantías, contacto u
   objeciones, prevalece
   [[team360_sales_diagnosis_commercial_objections]].
5. Este glosario estabiliza vocabulario cuando no contradice
   documentos más específicos.
6. Este glosario no mueve documentos a approved ni habilita ingesta.

---

## Glosario conceptual

### diagnóstico de automatización

Evaluación de un proceso empresarial para determinar si puede
automatizarse, con qué tecnología, qué riesgos implica, qué
datos se necesitan y qué nivel de intervención humana requiere.
No implica que Team360 ofrezca el servicio. Es la función
principal de Vera.

### factibilidad técnica

Evaluación de si un proceso puede automatizarse con la tecnología
disponible. Considera existencia de APIs, estabilidad de plataformas,
reglas definidas, volumen manejable y barreras técnicas.
No incluye disponibilidad comercial ni autorización del usuario.

### factibilidad operativa

Evaluación de si el usuario y su organización pueden adoptar y
sostener la automatización. Considera accesos, permisos, responsables,
frecuencia, volumen, dependencia humana y cambios organizacionales
requeridos.

### disponibilidad inmediata

Indica si Team360 ofrece hoy el servicio como paquete estándar
con alcance y condiciones definidas. No depende de la factibilidad
técnica: un proceso puede ser factible y no estar disponible como
paquete.

### paquete disponible

Servicio que Team360 comercializa hoy con alcance, condiciones,
evidencia y capacidad de delivery. Se clasifica como CORE_VALIDADO
o PILOTO_VALIDADO en service_maturity.

### solución no empaquetada

Caso factible técnica y operativamente pero que Team360 no ofrece
como paquete cerrado. Puede requerir diseño a medida, integración
nueva o desarrollo específico.

### validación necesaria

Estado donde faltan datos técnicos u operativos para confirmar la
factibilidad del caso. No implica que el caso sea inviable, sino
que el diagnóstico no puede completarse con la información actual.

### revisión humana

Evaluación del equipo de Team360 antes de ofrecer una respuesta
comercial, presupuesto o compromiso de implementación. Se activa
ante riesgo, datos sensibles, complejidad particular o falta de
evidencia.

### oportunidad futura

Caso con valor potencial para el roadmap de Team360 pero que no
debe ofrecerse como servicio actual. No prometer fechas, plazos
ni disponibilidad.

### caso no recomendable

Caso que no debe automatizarse por riesgo, costo, impacto,
seguridad, cumplimiento o inviabilidad técnica/operativa.
No ofrecer como servicio.

### producción por etapas

Enfoque de desarrollo incremental del asistente. Primero,
conversación natural, slots mínimos, diagnóstico útil y respuesta
clara. Después, capacidades avanzadas como Step-to-Action.
No usar el término MVP.

### producción incremental

Sinónimo de producción por etapas. Describe la estrategia de
maduración del asistente sumando capacidades progresivamente.

### catálogo diagnosticable

Conjunto de casos típicos que Vera puede diagnosticar, incluyendo
aquellos que Team360 no ofrece como paquete. No es una lista cerrada
de servicios.

### catálogo no cerrado

Principio de que Vera puede diagnosticar casos fuera de la lista
de automatizaciones documentadas. La ausencia en el catálogo no
significa imposibilidad.

### respuesta consultiva

Estilo de respuesta que prioriza diagnóstico útil sobre venta
inmediata. El asistente orienta, diferencia factibilidad de
disponibilidad y recomienda próximos pasos sin presión comercial.

### valor diagnóstico inicial

Orientación útil que Vera debe entregar en el primer mensaje,
incluso si falta información. Sin este valor, no debe pedir datos
personales ni ofrecer contacto.

### seguridad nativa bajo control del usuario

Principio de que Team360 no sustituye los mecanismos de seguridad
de las aplicaciones que automatiza. Códigos, QR, Face ID, MFA,
tokens y aprobaciones manuales deben ser completados por el usuario
o responsable autorizado.

### intervención humana

Punto del flujo donde una persona debe completar una acción que la
automatización no puede o no debe ejecutar. Puede ser una validación
de seguridad, una decisión crítica o una acción irreversible.

### dato sensible

Información que por su naturaleza requiere protección especial:
datos personales (salud, menores, biometría), financieros (cuentas,
tarjetas, transacciones), legales (contratos, cumplimiento) o
información gubernamental. Activa human_review_required.

### dato operativo

Información necesaria para el diagnóstico que no es sensible:
herramienta actual, frecuencia, volumen, proceso, área, canal.
Puede solicitarse sin restricción durante el diagnóstico.

### permiso autorizado

Acceso legítimo y documentado a una plataforma, sistema o dato,
otorgado por el responsable correspondiente. No incluye credenciales
compartidas, accesos delegados sin aprobación ni cuentas genéricas.

### API oficial

Interfaz de programación documentada y soportada por el proveedor
de la plataforma. Preferible a scraping o browser automation.

### browser automation

Automatización de acciones en un navegador web cuando la plataforma
no ofrece API. Técnicamente posible pero con riesgos: MFA, bloqueo,
cambios de interfaz, términos de servicio. Por defecto requiere
revisión humana.

### scraping

Extracción automatizada de datos desde páginas web sin API oficial.
Puede violar términos de servicio o leyes de protección de datos.
Requiere revisión humana por defecto.

### RAG sobre documentos propios

Asistente que responde preguntas usando documentos internos del
usuario (manuales, políticas, procedimientos) como fuente de
conocimiento. Factible si los documentos son digitales y hay
permisos definidos.

### CRM + leads

Automatización del proceso comercial: captura, clasificación,
asignación y seguimiento de clientes potenciales. Caso típico con
factibilidad alta si hay API disponible.

### WhatsApp comercial asistido

Automatización parcial de atención y ventas por WhatsApp: respuestas
frecuentes, clasificación, recordatorios, derivación a humano.
Requiere validación de consentimiento y alcance.

### reporte KPI

Generación automática de reportes periódicos a partir de fuentes
de datos estructuradas. Caso core de Team360 si las fuentes están
claras.

### Step-to-Action

Capacidad futura para que el usuario avance desde el diagnóstico
hacia una acción comercial concreta (contacto, propuesta, piloto).
Estado actual: `planned_extension`. No activo en producción por
etapas.

### lead capture

Captura de datos de contacto del usuario (nombre, WhatsApp, email)
para continuidad comercial. Estado actual: `planned_extension`.
No activo en producción por etapas.

### diagnostic_code

Identificador único de diagnóstico que conserva contexto para
futura continuidad comercial. Estado actual: `planned_extension`.
No activo en producción por etapas.

### WhatsApp handoff

Derivación de la conversación a un canal de WhatsApp hacia el
equipo de Team360, incluyendo contexto del diagnóstico. Estado
actual: `planned_extension`. No activo en producción por etapas.

### planned_extension

Estado de una capacidad que está diseñada conceptualmente pero
no implementada ni activa en la producción conversacional por
etapas. No debe presentarse como disponible, ofrecerse al usuario
ni activarse en respuestas.

---

## Categorías normalizadas

### A. diagnosis_category

Categoría final del diagnóstico que integra factibilidad técnica,
operativa y disponibilidad comercial.

| Valor | Definición | Cuándo usar | Qué no significa | Documento fuente |
|-------|-----------|-------------|------------------|------------------|
| `available_now` | El caso entra en un paquete o servicio disponible hoy por Team360. | Factibilidad técnica y operativa alta, disponibilidad confirmada, riesgo bajo. | Que no requiera validación de accesos o datos. | [[team360_sales_diagnosis_package_manual]] |
| `feasible_not_packaged` | El caso es factible técnica y operativamente, pero no está en disponibilidad inmediata como paquete cerrado. | Factibilidad alta/media, disponibilidad no empaquetada, riesgo bajo/medio. | Que Team360 lo implemente sin desarrollo a medida. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `feasible_needs_more_info` | En principio es factible, pero faltan datos técnicos u operativos para validar completamente. | Incertidumbre sobre factibilidad por falta de información. | Que el caso no tenga solución posible. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `special_case_human_review` | Caso particular que requiere charla con el equipo de Team360 para entender contexto, restricciones y objetivos. | Riesgo medio/alto, datos sensibles, complejidad, MFA, finanzas, browser automation. | Que sea automáticamente no recomendable. | [[team360_sales_diagnosis_security_hitl_policy]] |
| `future_opportunity` | Caso interesante y relevante para el roadmap, pero no debe prometerse como oferta actual. | Sin disponibilidad inmediata, sin evidencia suficiente, riesgo no resuelto. | Que el usuario pueda contratarlo hoy. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `not_recommended` | Caso no recomendable por riesgo, costo, cumplimiento o impacto. | Riesgo blocked, inviabilidad técnica/operativa, violación de seguridad. | Que no existan alternativas de mejora. | [[team360_sales_diagnosis_security_hitl_policy]] |

### B. availability_status

Disponibilidad del servicio como paquete de Team360.

| Valor | Definición |
|-------|-----------|
| `available_now` | Team360 ofrece hoy el servicio con alcance y condiciones definidas. |
| `available_with_validation` | El servicio existe pero requiere validación de accesos, datos o alcance. |
| `feasible_not_packaged` | El caso es factible pero no está empaquetado como servicio estándar. |
| `future_opportunity` | Es relevante para el roadmap pero no debe ofrecerse como servicio actual. |
| `not_available` | El servicio no está disponible hoy. |
| `not_recommended` | No se recomienda automatizar por riesgo, costo o impacto. |

### C. service_maturity

Madurez del servicio según evidencia y capacidad de delivery.

| Valor | Definición |
|-------|-----------|
| `CORE_VALIDADO` | Servicio con evidencia suficiente, alineado al foco inicial. Capacidad defendible para oferta principal. |
| `PILOTO_VALIDADO` | Servicio probado o factible para piloto con límites claros. No maduro como core repetible. |
| `OPORTUNIDAD` | Interés comercial o dirección posible sin evidencia suficiente para delivery estándar. |
| `PAQUETE_FUTURO` | Línea relevante que merece diseño propio o roadmap antes de activarse como oferta. |
| `NO_OFRECER_AUN` | Tema fuera de alcance actual, riesgoso o no validado para comercializar ahora. |

### D. offer_decision

Decisión comercial responsable para el caso diagnosticado.

| Valor | Definición |
|-------|-----------|
| `sellable_now` | Team360 puede ofrecerlo hoy con alcance y límites claros. |
| `pilot` | Puede ofrecerse como piloto controlado con alcance acotado. |
| `needs_more_info` | Se necesita más información técnica u operativa antes de decidir. |
| `human_review_required` | Requiere evaluación humana antes de responder, presupuestar o ejecutar. |
| `future_opportunity` | Interesante para roadmap, no vendible como oferta actual. |
| `do_not_offer` | No ofrecer activamente. Usar para descarte informado. |

### E. technical_feasibility

Factibilidad técnica del proceso.

| Valor | Definición |
|-------|-----------|
| `high` | Claramente automatizable. APIs, datos accesibles, reglas definidas. |
| `medium` | Probablemente automatizable, pero con factores técnicos a validar. |
| `low` | Difícil técnicamente. Puede requerir desarrollo a medida o integración compleja. |
| `unknown` | No hay suficiente información técnica para evaluar. |
| `not_feasible` | Técnicamente no es viable automatizar con los medios disponibles. |

### F. operational_feasibility

Factibilidad operativa del proceso.

| Valor | Definición |
|-------|-----------|
| `high` | Proceso claro, responsable definido, accesos disponibles, mínima dependencia humana. |
| `medium` | Requiere coordinación, cambios organizacionales o aprobaciones. |
| `low` | Alta dependencia humana, procesos no documentados o cambios profundos. |
| `unknown` | No hay información operativa suficiente. |
| `blocked` | Barrera operativa concreta: falta de acceso, presupuesto o restricción interna. |

### G. risk_level

Nivel de riesgo del caso.

| Valor | Definición | Ejemplos |
|-------|-----------|----------|
| `low` | Riesgo mínimo. Proceso interno, datos propios, sin exposición externa. | Reportes internos simples, clasificación de leads sin datos sensibles. |
| `medium` | Riesgo moderado. Herramientas comerciales, datos de clientes no sensibles. | CRM, WhatsApp comercial, formularios. |
| `high` | Riesgo alto. Datos sensibles, finanzas, scraping, plataformas con controles nativos. | Browser automation con login, MFA, datos financieros. |
| `blocked` | Riesgo máximo. Violación de seguridad, términos o legal. | Pedir contraseñas, evadir MFA, scraping prohibido. |

### H. human_review_required

Indica si el caso requiere revisión humana antes de oferta comercial.

| Valor | Definición |
|-------|-----------|
| `true` | Requiere revisión humana. Una o más condiciones de riesgo activadas. |
| `false` | No requiere revisión humana por defecto. |
| `conditional` | Requiere revisión humana si se detectan condiciones específicas (datos sensibles, MFA, cumplimiento). |

`conditional` es un valor editorial útil para defaults de catálogo o
slots preliminares. La respuesta final debe resolver
`human_review_required` como `true` o `false` antes de recomendar un
próximo paso.

---

## Slots normalizados

### Slots de diagnóstico inicial

Se completan durante la conversación de diagnóstico. Son la base
para evaluar factibilidad técnica y operativa.

| Slot | Definición | Tipo esperado | Valores posibles | Cuándo se completa | Documento relacionado |
|------|-----------|---------------|------------------|-------------------|----------------------|
| `proceso_a_automatizar` | Descripción del proceso que el usuario quiere automatizar. | string | Texto libre | Primer mensaje o primera pregunta. | [[team360_sales_diagnosis_slots_questions]] |
| `dolor_principal` | Lo que más molesta o urge resolver del proceso actual. | string | Texto libre | Cuando el usuario describe su motivación. | [[team360_sales_diagnosis_slots_questions]] |
| `herramienta_actual` | Qué usa hoy el usuario para ejecutar el proceso. | string | CRM, WhatsApp, Excel, Sheets, sistema, papel, ninguno | Cuando se describe el proceso. | [[team360_sales_diagnosis_slots_questions]] |
| `industria` | Rubro o sector del usuario. | string | Texto libre | Cuando se menciona o se infiere. | [[team360_sales_diagnosis_slots_questions]] |
| `area_negocio` | Área interna donde ocurre el proceso. | string | ventas, admin, backoffice, atención, producción | Cuando se describe el contexto. | [[team360_sales_diagnosis_slots_questions]] |
| `frecuencia` | Cada cuánto se ejecuta el proceso. | string | diario, varias veces al día, semanal, mensual, por evento | Cuando se habla de recurrencia. | [[team360_sales_diagnosis_slots_questions]] |
| `volumen` | Cantidad de operaciones por período. | string | Número aproximado + unidad | Cuando se evalúa impacto. | [[team360_sales_diagnosis_slots_questions]] |
| `fuente_datos` | De dónde vienen los datos del proceso. | string | WhatsApp, CRM, planilla, formulario, sistema | Cuando se habla de integración. | [[team360_sales_diagnosis_slots_questions]] |
| `responsable` | Quién ejecuta o supervisa el proceso. | string | el usuario, un equipo, varias áreas | Cuando se evalúa factibilidad operativa. | [[team360_sales_diagnosis_slots_questions]] |
| `urgencia` | Urgencia de la mejora. | string | alta, media, baja | Cuando se prioriza el próximo paso. | [[team360_sales_diagnosis_slots_questions]] |
| `crm_actual` | CRM en uso. | string | Kommo, HubSpot, Zoho, Salesforce, Pipedrive, planilla, ninguno | Cuando el proceso involucra CRM. | [[team360_sales_diagnosis_slots_questions]] |
| `whatsapp_uso` | Cómo usa WhatsApp. | string | personal, Business, Cloud API, proveedor externo, no sabe | Cuando el proceso involucra WhatsApp. | [[team360_sales_diagnosis_slots_questions]] |
| `facebook_ads_uso` | Si usa publicidad en Meta. | string | campañas activas, formularios leads, mensajes, no usa | Cuando menciona Facebook/Instagram. | [[team360_sales_diagnosis_slots_questions]] |
| `excel_sheets_uso` | Cómo usa planillas. | string | Excel local, Google Sheets, planilla compartida, reportes manuales | Cuando menciona planillas. | [[team360_sales_diagnosis_slots_questions]] |
| `impacto_economico` | Estimación del costo u horas del proceso actual. | string | tiempo, personas, costo estimado | Cuando se evalúa retorno. | [[team360_sales_diagnosis_slots_questions]] |
| `tipo_automatizacion` | Tipo de solución sugerida. | string | RAG, workflow, integración, RPA, reporte, asistente | Inferir durante el diagnóstico. | [[team360_sales_diagnosis_slots_questions]] |
| `acceso_disponible` | Si el usuario tiene acceso autorizado a las herramientas. | boolean | true, false, no sabe | Cuando se evalúa factibilidad operativa. | [[team360_sales_diagnosis_slots_questions]] |
| `mfa` | Si el proceso o plataforma requiere MFA. | boolean | true, false, no sabe | Cuando hay login o plataforma externa. | [[team360_sales_diagnosis_slots_questions]] |
| `riesgo_datos` | Si el proceso maneja datos sensibles. | boolean | true, false | Cuando se detectan datos personales, financieros, salud. | [[team360_sales_diagnosis_slots_questions]] |

### Slots de clasificación

Se infieren durante el diagnóstico. No se preguntan literalmente
como formulario.

| Slot | Definición | Tipo esperado | Valores posibles | Cuándo se completa | Documento relacionado |
|------|-----------|---------------|------------------|-------------------|----------------------|
| `technical_feasibility` | Factibilidad técnica del proceso. | enum | high, medium, low, unknown, not_feasible | Inferir después de analizar proceso, herramientas, API, MFA. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `operational_feasibility` | Factibilidad operativa del proceso. | enum | high, medium, low, unknown, blocked | Inferir después de analizar accesos, permisos, datos, responsables. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `availability_status` | Disponibilidad como paquete/servicio hoy. | enum | available_now, available_with_validation, feasible_not_packaged, future_opportunity, not_available, not_recommended | Inferir desde service_maturity y oferta actual. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `diagnosis_category` | Categoría del diagnóstico amplio. | enum | available_now, feasible_not_packaged, feasible_needs_more_info, special_case_human_review, future_opportunity, not_recommended | Clasificar después del análisis de factibilidad. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `package_fit` | Correspondencia entre el caso y un paquete existente. | string | alto, medio, bajo, ninguno | Inferir desde proceso, alcance y madurez del servicio. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `requires_more_info` | Si faltan datos técnicos u operativos para validar. | boolean | true, false | Activar ante incertidumbre técnica u operativa. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `human_review_required` | Si el caso requiere revisión humana. | enum | true, false, conditional | `conditional` solo como valor editorial preliminar; resolver en true/false antes de responder. | [[team360_sales_diagnosis_security_hitl_policy]] |
| `future_opportunity_reason` | Razón por la que el caso es oportunidad futura. | string | Texto libre | Solo si diagnosis_category es future_opportunity. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `not_recommended_reason` | Razón por la que el caso no es recomendable. | string | Texto libre | Solo si diagnosis_category es not_recommended. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `immediate_availability` | Si Team360 ofrece el servicio hoy como paquete estándar. | boolean | true, false | Inferir desde service_maturity. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `validation_needed_reason` | Describe qué información falta para validar factibilidad. | string | Texto libre | Solo si diagnosis_category es feasible_needs_more_info. | [[team360_sales_diagnosis_feasibility_availability_matrix]] |
| `risk_level` | Nivel de riesgo del caso. | enum | low, medium, high, blocked | Basar en datos, permisos, criticidad e irreversibilidad. | [[team360_sales_diagnosis_security_hitl_policy]] |
| `next_step` | Paso recomendado post-diagnóstico. | string | Texto libre | Al final del diagnóstico. | [[team360_sales_diagnosis_response_playbook]] |

### Slots comerciales posteriores

Se completan solo después de dar valor diagnóstico y si el usuario
pide contacto, presupuesto o propuesta. No se piden al inicio.

| Slot | Definición | Tipo esperado | Cuándo se completa |
|------|-----------|---------------|-------------------|
| `nombre` | Nombre del usuario. | string | Solo si el usuario pide contacto o lo ofrece espontáneamente. |
| `apellido` | Apellido del usuario. | string | Solo si se habilita handoff o el usuario lo ofrece. |
| `whatsapp_contacto` | WhatsApp del usuario para continuidad. | string | Solo si el usuario pide contacto o propuesta. |
| `email_contacto` | Email del usuario. | string | Solo si el usuario lo prefiere o lo ofrece. |
| `empresa` | Empresa del usuario. | string | Solo si aplica y después de diagnóstico. |
| `diagnostic_code` | Código único de diagnóstico para continuidad. | string | Capa futura. No se genera en producción por etapas. |

---

## Capacidades futuras y planned_extension

### Step-to-Action

| Campo | Valor |
|-------|-------|
| Definición | Capacidad para que el usuario avance desde el diagnóstico hacia una acción comercial concreta (contacto, propuesta, piloto). |
| Estado | `planned_extension` |
| Qué no debe hacer Vera ahora | No activar flujo de continuidad. No pedir datos de contacto como parte del diagnóstico normal. No ofrecer "dejá tu WhatsApp" sin valor previo. |
| Cuándo podría usarse en futuro | Cuando el usuario muestre intención de contratar, pida presupuesto, complete un diagnóstico con scoring positivo, o el caso requiera continuidad humana. |
| Relación con contacto humano | El contacto con el equipo se ofrece después del valor diagnóstico. Step-to-Action agrega un mecanismo estructurado para esa continuidad. |

### Lead capture

| Campo | Valor |
|-------|-------|
| Definición | Captura estructurada de datos de contacto del usuario para continuidad comercial. |
| Estado | `planned_extension` |
| Qué no debe hacer Vera ahora | No preguntar nombre, WhatsApp, email o empresa durante el diagnóstico inicial. No activar formularios de captura. |
| Cuándo podría usarse en futuro | Cuando el usuario acepte contacto después de recibir valor diagnóstico. Pedir solo el mínimo necesario (nombre y WhatsApp). |
| Relación con contacto humano | El lead capture futuro debe explicar para qué se usan los datos y permitir que el usuario continúe sin compartirlos. |

### Diagnostic code

| Campo | Valor |
|-------|-------|
| Definición | Identificador único que conserva el contexto del diagnóstico para que el equipo de Team360 pueda retomarlo sin pedir al usuario que repita todo. |
| Estado | `planned_extension` |
| Qué no debe hacer Vera ahora | No generar diagnostic_code. No usarlo como identificador de sesión. |
| Cuándo podría usarse en futuro | Cuando se habilite Step-to-Action o lead capture. El código se asigna al momento de la continuidad comercial. |
| Relación con contacto humano | El diagnostic_code se entrega al usuario y al equipo para retomar el caso sin perder contexto. |

### WhatsApp handoff

| Campo | Valor |
|-------|-------|
| Definición | Derivación de la conversación a un canal de WhatsApp hacia Team360, incluyendo el diagnostic_code y un resumen del caso. |
| Estado | `planned_extension` |
| Qué no debe hacer Vera ahora | No generar URL o mensaje de WhatsApp. No pedir WhatsApp de contacto. |
| Cuándo podría usarse en futuro | Cuando el usuario acepte contacto y haya un diagnostic_code asociado. |
| Relación con contacto humano | El handoff futuro prepara un mensaje prearmado para que el usuario envíe a Team360 con el contexto del diagnóstico. |

---

## Referencias cruzadas entre documentos

| Documento | Rol principal | Cuándo consultarlo | Términos que define | Dependencia principal |
|-----------|-------------|-------------------|-------------------|----------------------|
| `team360_sales_diagnosis_package_manual.md` | Manual maestro del paquete. | Propósito general, alcance, límites, flujo conceptual, offer_decision, service_maturity. | diagnosis_category, offer_decision, service_maturity, flujo conceptual, reglas de conversación. | Ninguno (documento raíz). |
| `team360_sales_diagnosis_slots_questions.md` | Guía de slots y preguntas dinámicas. | Extracción de contexto, slots, preguntas, señales, reglas de no sobrepreguntar. | Todos los slots, niveles de slot, reglas conversacionales, señales textuales. | package_manual para alcance y límites. |
| `team360_sales_diagnosis_feasibility_availability_matrix.md` | Matriz de factibilidad y disponibilidad. | Clasificación técnica y operativa de casos. | technical_feasibility, operational_feasibility, availability_status, human_review_required, patrones de respuesta por categoría. | package_manual para definiciones; slots_questions para slots. |
| `team360_sales_diagnosis_response_playbook.md` | Playbook de respuestas conversacionales. | Estilo, estructura y patrones de respuesta. | Estructura base de respuesta, patrones por diagnosis_category, frases prohibidas. | feasibility_availability_matrix para categorías de diagnóstico. |
| `team360_sales_diagnosis_security_hitl_policy.md` | Política de seguridad y HITL. | Límites de seguridad, riesgo, MFA, scraping, finanzas, revisión humana. | risk_level, human_review_required, seguridad nativa, criterios de bloqueo. | package_manual para alcance; feasibility_availability_matrix para clasificación de riesgo. |
| `team360_sales_diagnosis_automation_catalog.md` | Catálogo de automatizaciones. | Ejemplos concretos de casos por familia, datos mínimos, clasificación rápida. | automation_case, minimum_information_needed, valores por defecto por familia. | feasibility_availability_matrix para clasificación; security_hitl_policy para riesgos. |
| `team360_sales_diagnosis_commercial_objections.md` | Objeciones comerciales. | Respuestas ante objeciones de precio, urgencia, disponibilidad, seguridad, contacto. | Patrones de objeción, preguntas permitidas por etapa, frases recomendadas. | Todos los documentos anteriores según la objeción. |
| `team360_sales_diagnosis_glossary_crossrefs.md` | Glosario y referencias cruzadas. | Definiciones estables, precedencia documental, QA, vocabulario unificado. | Todos los términos normalizados, categorías, slots, planned_extension, precedencia. | Todos los documentos del paquete. |

---

## Matriz de precedencia documental

En caso de conflicto entre documentos del paquete, se aplica el
siguiente orden de precedencia:

1. **security_hitl_policy** para riesgos, credenciales, MFA, QR,
   Face ID, datos sensibles, seguridad nativa, bloqueo o revisión
   humana.
2. **feasibility_availability_matrix** para clasificación de
   factibilidad técnica, operativa, disponibilidad, service_maturity,
   offer_decision y diagnosis_category.
3. **response_playbook** para estilo conversacional, estructura de
   respuesta y patrones por categoría.
4. **commercial_objections** para objeciones, precio, garantías,
   contacto y dudas comerciales.
5. **automation_catalog** para ejemplos concretos y familias de
   casos.
6. **slots_questions** para información a capturar, preguntas y
   señales textuales.
7. **package_manual** para propósito general del paquete y alcance
   funcional.
8. **glossary_crossrefs** para vocabulario estable cuando no
   contradice documentos más específicos.

---

## Términos prohibidos o restringidos

| Término | Problema | Alternativa |
|---------|----------|-------------|
| MVP | Promete versión mínima, sugiere producto incompleto. | "producción por etapas", "producción incremental", "producción avanzando por pasos". |
| `vera_*` en identificadores técnicos | Mezcla marca comercial con código. | Usar `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis`. |
| Step-to-Action como activo | Capacidad futura presentada como disponible. | "planned_extension", "capacidad futura". |
| lead capture como activo | Captura prematura de datos personales. | "planned_extension", "capacidad futura". |
| diagnostic_code como activo | Código de diagnóstico no implementado. | "planned_extension", "capacidad futura". |
| WhatsApp handoff como activo | Derivación automática no implementada. | "planned_extension", "capacidad futura". |
| "automatizamos cualquier cosa" | Promesa comercial excesiva. | "diagnosticamos casos y evaluamos factibilidad". |
| "garantizamos resultados" | Los resultados dependen de múltiples factores. | "la automatización hace el trabajo repetitivo de forma consistente". |
| "pasame tu clave/código/token" | Violación de seguridad. | "no compartas credenciales, revisemos APIs oficiales". |
| "saltamos MFA" | Evasión de seguridad nativa. | "respetamos los controles de seguridad existentes". |
| "solo hay que conectar la API" | Minimiza complejidad sin validación. | "requiere validar que la API esté disponible y documentada". |

---

## Frases canónicas recomendadas

Estas frases son consistentes con todos los documentos del paquete
y pueden usarse como base para respuestas del asistente.

| Frase | Contexto |
|-------|----------|
| "Factible técnicamente no significa disponible hoy como paquete." | Separar factibilidad de disponibilidad. |
| "Disponible como línea de trabajo no elimina la necesidad de validación." | Todo paquete requiere validación de accesos y datos. |
| "No disponible como paquete no significa imposible." | Casos fuera de catálogo pueden ser diagnósticables. |
| "Primero damos valor diagnóstico; el contacto viene después si el usuario quiere avanzar." | Regla de contacto posterior al valor. |
| "Team360 ayuda a automatizar, pero no sustituye la seguridad nativa de las aplicaciones." | Límite de seguridad. |
| "Si una aplicación pide código, QR, Face ID o MFA, esa validación la realiza el usuario autorizado." | Seguridad nativa bajo control del usuario. |
| "Un caso puede ser técnicamente factible y aun así requerir revisión humana." | Precedencia de seguridad sobre factibilidad. |
| "El catálogo orienta, no limita el diagnóstico." | Catálogo no cerrado. |

---

## QA documental antes de approved

Checklist para revisar cualquier documento del paquete antes de
promoverlo de `drafts/` a `approved/`:

- [ ] ¿Tiene frontmatter completo con todos los campos requeridos?
- [ ] ¿El campo `status` sigue siendo coherente con el estado real?
- [ ] ¿El campo `ingestion_status` es correcto?
- [ ] ¿No usa el término MVP en ninguna variante?
- [ ] ¿No usa identificadores `vera_*`?
- [ ] ¿No presenta capacidades futuras (Step-to-Action, lead capture, diagnostic_code, WhatsApp handoff) como activas?
- [ ] ¿Distingue explícitamente entre factibilidad y disponibilidad?
- [ ] ¿Respeta el principio de seguridad nativa bajo control del usuario?
- [ ] ¿No pide datos personales al inicio del diagnóstico?
- [ ] ¿Tiene referencias cruzadas correctas a otros documentos del paquete?
- [ ] ¿No contradice la política de seguridad/HITL?
- [ ] ¿No contradice la matriz de factibilidad/disponibilidad?
- [ ] ¿Usa las categorías normalizadas de este glosario?
- [ ] ¿Los valores de diagnosis_category, risk_level y service_maturity son válidos?
- [ ] ¿Respeta el orden de precedencia documental?

---

## Límites

- Este glosario no define precios.
- No reemplaza la política de seguridad/HITL.
- No reemplaza la matriz de factibilidad/disponibilidad.
- No habilita Step-to-Action.
- No habilita lead capture.
- No habilita diagnostic_code.
- No habilita WhatsApp handoff.
- No convierte drafts en approved.
- No ejecuta ingesta.
- No define runtime ni modelos.

---

## Historial de cambios

| Fecha | Cambio | Autor |
|------|--------|-------|
| 2026-06-14 | Creación draft inicial para producción por etapas. | Team360 |
