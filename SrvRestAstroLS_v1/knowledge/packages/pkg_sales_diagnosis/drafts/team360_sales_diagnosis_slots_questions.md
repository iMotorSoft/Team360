---
document_code: team360_sales_diagnosis_slots_questions
document_type: slots_questions_guide
version: 1
status: draft
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
template_code: team360_sales_automation_diagnosis
client_code:
client_context: team360_live_public_home
first_validation_client: team360_live
source_type: markdown
level_target:
  - L1
  - L2
language: es-AR
owner: Team360
last_review:
ingestion_status: not_ready
access_tags:
  - soporte
  - public
evidence_level: validated_by_source
evidence_sources:
  - cv_inventory
  - team360_frontend
  - mamamia360_website
  - team360_sales_diagnosis_package_manual
implementation_status: prototype
commercial_status: sellable_pilot
service_maturity: PILOTO_VALIDADO
offer_decision:
  - automatable
  - sellable_now
  - pilot
  - human_review_required
validation_context:
  - team360_live
  - public_home
  - internal_validation
review_cycle: iterative
last_validated_at:
validated_by:
related_pilots:
  - team360_live_public_home
related_clients:
  - team360_live
risk_level: medium
supports_step_to_action: false
step_to_action_status: planned_extension
step_to_action_type: diagnostic_code_whatsapp_handoff
preferred_backoffice_model: deepseek_4_flash
preferred_fast_response_model: gpt_5_nano_low
preferred_deep_diagnosis_model: qwen3_30b_a3b_thinking_2507
chunking_strategy: semantic_chunker
approval_notes: >
  Borrador inicial de slots y preguntas dinámicas para
  pkg_sales_diagnosis. Complementa el package manual.
  Debe revisarse con GPT-5.5 antes de promover a approved/.
  Ninguna sección cierra decisiones estratégicas finales.
---

# Guía de slots y preguntas dinámicas para diagnóstico de automatización

## Nota de estado draft

Este documento está en estado **draft**. No debe ingerirse ni
moverse a `approved/` hasta pasar revisión editorial, validación
de límites comerciales y prueba conversacional.

---

## L0 Abstract

Este documento define qué datos debe extraer el asistente desde
texto libre, qué slots son obligatorios, recomendados u opcionales,
cómo detectar señales en el texto del usuario, qué preguntar
cuando falta información y cómo registrar señales para una futura capa
de Step-to-Action cuando corresponda.

Sirve para que Vera / Asistente Inteligente Vera pueda diagnosticar
oportunidades de automatización sin depender de formularios rígidos.
Ventas es la entrada comercial inicial, pero los slots cubren
procesos automatizables más amplios: administrativos, operativos,
documentales, integraciones y flujos con riesgo.

El objetivo es mejorar la calidad del diagnóstico sin abrumar al
usuario con preguntas innecesarias. Step-to-Action, lead capture,
`diagnostic_code` y WhatsApp handoff son capacidades futuras, no parte
activa del MVP conversacional inicial.

---

## Propósito del documento

Esta guía define:

- Slots principales que Vera debe extraer del texto libre.
- Señales textuales que indican la presencia de un slot.
- Preguntas de seguimiento para completar información faltante.
- Prioridad de extracción según el contexto detectado.
- Reglas para no sobrepreguntar al usuario.
- Criterios para detectar señales futuras de Step-to-Action sin
  capturar datos personales en el MVP inicial.
- Criterios para activar `human_review_required`.

No define implementación técnica ni endpoints. Es una guía
conversacional y de extracción de contexto para el asistente.

---

## Principio conversacional

Reglas que el asistente debe seguir en toda interacción:

1. **Responder con valor inmediato** antes de pedir datos. Primero
   devolver una hipótesis útil, aunque sea preliminar.
2. **Extraer todo lo posible del texto libre** del usuario. No
   preguntar lo que ya fue dicho.
3. **No pedir datos que ya fueron dados** en la conversación.
4. **Preguntar máximo 1 a 3 cosas por turno.** No abrumar.
5. **Priorizar preguntas que cambian el diagnóstico.** Si un dato
   no altera la recomendación, no preguntarlo ahora.
6. **Usar lenguaje simple.** Evitar tecnicismos en preguntas.
7. **No usar formularios largos al inicio.** La conversación debe
   fluir de forma natural.
8. **Confirmar hipótesis suavemente.** Ej: "Si entendí bien,
   querés automatizar..."
9. **No frenar la conversación con tecnicismos.** Adaptar el
   lenguaje al perfil del usuario.
10. **No pedir WhatsApp, email ni presupuesto al inicio** salvo que
    el usuario ya pida continuidad comercial, cotización o contacto.
11. **Separar diagnóstico de venta.** Diagnosticar un proceso no
    significa que Team360 lo implemente como oferta actual.
12. **No activar lead capture en el MVP inicial.** Registrar señales
    de continuidad futura, pero no pedir nombre, apellido, WhatsApp,
    email ni empresa durante el diagnóstico.

### Patrones conversacionales

**Buen patrón:**

> Por lo que contás, parece un buen caso para automatizar
> seguimiento. Para ubicarlo mejor: ¿hoy eso lo manejan en
> WhatsApp, CRM o planilla?

**Mal patrón:**

> Indique industria, proceso, herramienta, frecuencia, volumen,
> presupuesto y responsable.

**Regla:** cuando falten muchos datos, elegir una pregunta que destrabe
el diagnóstico. No pedir todo junto.

---

## Niveles de slots

### Slots críticos

Necesarios para el diagnóstico inicial. Sin ellos no se puede
evaluar factibilidad, impacto ni complejidad.

### Slots recomendados

Mejoran la calidad del diagnóstico. Aportan precisión a la
evaluación de factibilidad, impacto y complejidad.

### Slots opcionales

Sirven para contexto adicional, scoring comercial o continuidad.
No afectan el diagnóstico inicial y no deben convertirse en requisito
para orientar al usuario.

### Slots sensibles

Requieren cuidado, privacidad o revisión humana. No preguntar
de entrada. Solo si el contexto lo justifica.

---

## Slots por función y fase

Esta separación evita que el asistente mezcle diagnóstico, clasificación
y captura comercial. El MVP conversacional solo usa slots de diagnóstico
y clasificación. Los slots de continuidad comercial quedan como
capacidad futura.

### A. Slots del MVP conversacional

Estos slots ayudan a interpretar texto libre, hacer preguntas mínimas,
diagnosticar y clasificar. No requieren pedir datos personales.

| Slot | Función | Cuándo preguntarlo |
|------|---------|--------------------|
| `proceso_a_automatizar` | Define qué quiere mejorar el usuario. | Si el proceso no está claro. |
| `dolor_principal` | Explica por qué importa automatizar. | Si falta motivación o prioridad. |
| `herramienta_actual` | Muestra dónde ocurre hoy el trabajo. | Si hay proceso pero no sistema/canal. |
| `frecuencia` | Estima recurrencia. | Si falta impacto o prioridad. |
| `volumen` | Estima escala. | Si falta impacto; no hace falta pedirlo exacto. |
| `industria` | Da contexto sectorial. | Si cambia riesgos o ejemplos. |
| `area_negocio` | Ubica el proceso dentro de la empresa. | Si ayuda a priorizar o derivar. |
| `fuente_datos` | Identifica origen de información. | Si hay integración o carga de datos. |
| `responsable` | Identifica quién opera o supervisa. | Si hay cambio operativo o varias áreas. |
| `urgencia` | Ordena el próximo paso. | Si el usuario evalúa avanzar. |
| `riesgo_datos` | Detecta sensibilidad. | Solo si el proceso menciona datos críticos. |
| `acceso_disponible` | Verifica acceso autorizado. | Solo si hay integración o plataforma externa. |
| `mfa` | Detecta doble factor o bloqueo técnico. | Solo si hay login, plataforma externa o RPA. |
| `tipo_automatizacion` | Sugiere RAG, workflow, integración, RPA o reporte. | Inferir desde proceso, herramienta y fuente de datos. |
| `offer_decision` | Separa automatizable de vendible hoy. | Inferir con criterio conservador. |
| `service_maturity` | Declara madurez del servicio. | Inferir sin elevar a core temas futuros o sensibles. |
| `human_review_required` | Marca necesidad de revisión humana. | Activar por seguridad, datos sensibles, MFA, finanzas o incertidumbre. |
| `risk_level` | Resume riesgo bajo, medio o alto. | Basar en datos, permisos, criticidad e irreversibilidad. |

### B. Slots de clasificación

Estos slots también pertenecen al MVP conversacional, pero son inferidos
por el asistente. No se preguntan literalmente como formulario.

| Slot | Función | Regla |
|------|---------|-------|
| `tipo_automatizacion` | Sugiere RAG, workflow, integración, RPA o reporte. | Inferir desde proceso, herramienta y fuente de datos. |
| `offer_decision` | Separa automatizable de vendible hoy. | Usar criterio conservador si hay riesgo o baja evidencia. |
| `service_maturity` | Declara madurez de servicio. | No elevar a core temas futuros o sensibles. |
| `human_review_required` | Marca necesidad de revisión humana. | Activar por seguridad, datos sensibles, MFA, finanzas o incertidumbre. |
| `risk_level` | Resume riesgo bajo, medio o alto. | Basar en datos, permisos, criticidad e irreversibilidad. |

### C. Slots futuros de continuidad comercial

Estos slots habilitarán continuidad comercial en una capa posterior.
No deben pedirse en el MVP conversacional inicial, salvo que el usuario
pida contacto, presupuesto, propuesta o deje voluntariamente sus datos.

| Slot | Función | Cuándo pedirlo |
|------|---------|----------------|
| `nombre` | Identificación mínima futura. | No pedir en MVP; aceptar si el usuario lo ofrece o pide contacto. |
| `apellido` | Completa identificación futura. | No pedir en MVP; usar solo si se habilita handoff. |
| `whatsapp_contacto` | Canal futuro de handoff comercial. | No pedir en MVP; solo si el usuario pide WhatsApp/contacto/propuesta. |
| `email_contacto` | Canal alternativo futuro. | No pedir en MVP; aceptar si el usuario lo prefiere u ofrece. |
| `empresa` | Contexto comercial futuro opcional. | No pedir en MVP salvo pedido explícito de propuesta. |
| `diagnostic_code` | Conserva contexto en continuidad futura. | Diseño futuro; no es requerimiento del diagnóstico actual. |
| `interes_en_diagnostico` | Señal de orientación, propuesta o continuidad. | Inferir; no usar para capturar datos automáticamente. |
| `siguiente_paso` | Recomienda cierre, piloto, orientación o revisión. | Sí como recomendación textual; no como lead capture. |

**Regla comercial:** si el usuario no quiere dejar datos, el asistente
debe poder seguir orientando de forma general.

**Regla de MVP:** no pedir nombre, apellido, WhatsApp, email, empresa
ni datos de contacto durante la fase inicial de diagnóstico. Registrar
la señal de continuidad futura, pero priorizar diagnóstico útil y
respuesta clara.

---

## Tabla general de slots

| Slot | Nivel | Definición | Señales textuales | Por qué importa | Riesgo si falta |
|------|-------|-----------|-------------------|----------------|-----------------|
| `industria` | recomendado | Rubro o sector del usuario | "tengo un comercio", "soy contador", "tengo una inmobiliaria", "trabajo en salud" | El tipo de automatización varía por industria | Diagnóstico genérico o desalineado |
| `proceso_a_automatizar` | crítico | Descripción del proceso que quiere mejorar | "cargo datos", "saco reportes", "respondo WhatsApp", "cargo leads", "hago facturas" | Base del diagnóstico | No se puede diagnosticar sin proceso |
| `area_negocio` | recomendado | Área interna donde ocurre el proceso | "en ventas", "en administración", "en backoffice", "en atención al cliente" | Ayuda a clasificar y priorizar la automatización | Diagnóstico sin contexto organizacional |
| `canal_origen` | opcional | Cómo llegó el usuario | "vi la página", "me mandaron", "busqué en Google", "me contó un conocido" | Sirve para atribución futura | Sin efecto en el diagnóstico |
| `herramienta_actual` | crítico | Qué usa hoy para el proceso | "Excel", "WhatsApp", "Google Sheets", "un CRM", "una planilla", "papel" | Determina complejidad de integración | No se puede estimar esfuerzo |
| `crm_actual` | recomendado | CRM en uso | "Kommo", "HubSpot", "Zoho", "Salesforce", "Pipedrive", "una planilla", "ninguno" | Afecta integración y trazabilidad | Diagnóstico incompleto para ventas |
| `whatsapp_uso` | recomendado | Uso de WhatsApp | "hablo por WhatsApp", "tengo WhatsApp Business", "recibo pedidos por WhatsApp" | Canal prioritario para automatización | Oportunidad de automatización no detectada |
| `facebook_ads_uso` | opcional | Uso de publicidad en Meta | "hago publicidad en Facebook", "tengo campañas en Meta", "llegan leads de Facebook" | Canal de entrada de leads | Lead source no identificado |
| `excel_sheets_uso` | recomendado | Uso de planillas | "uso Excel", "tengo una planilla compartida", "Google Sheets", "todo en Excel" | Indica proceso manual y oportunidad de mejora | Carga manual no detectada |
| `fuente_datos` | recomendado | De dónde vienen los datos | "de WhatsApp", "del CRM", "de una planilla", "de un formulario", "del sistema" | Afecta factibilidad técnica | Integración mal estimada |
| `frecuencia` | crítico | Cada cuánto se ejecuta el proceso | "todos los días", "una vez por semana", "cada vez que llega un lead", "al cierre del mes" | Determina prioridad e impacto | Subestimación del volumen |
| `volumen` | crítico | Cantidad de operaciones por período | "unos 50 leads por mes", "unos 200 mensajes al día", "10 facturas por semana" | Determina impacto y retorno | ROI no estimable |
| `impacto_economico` | recomendado | Estimación de costo del proceso actual | "perdemos tiempo", "tardo 2 horas por día", "son 3 personas medio tiempo", "nos cuesta plata" | Ayuda a priorizar inversión | Dificulta justificar presupuesto |
| `responsable` | recomendado | Quién ejecuta o supervisa el proceso | "lo hago yo", "lo hace mi asistente", "lo hace el equipo de ventas" | Ayuda a dimensionar alcance | Sin contexto de operación |
| `dolor_principal` | crítico | Lo que más molesta o urge resolver | "me lleva mucho tiempo", "me olvido de responder", "se pierden leads", "es muy tedioso" | Base de la motivación | Diagnóstico sin ancla real |
| `urgencia` | recomendado | Urgencia de la mejora | "ya debería haberlo resuelto", "estamos saturados", "lo vengo pateando", "recién lo estoy evaluando" | Define velocidad de acción | Priorización incorrecta |
| `acceso_disponible` | sensible | Si el usuario tiene acceso autorizado | "tengo usuario", "tengo acceso al sistema", "tengo permisos", "lo hace otro equipo" | Determina factibilidad operativa | Promesa imposible de cumplir |
| `mfa` | sensible | Si el proceso requiere MFA | "pide código de verificación", "tengo que aprobar desde el teléfono", "hay doble factor" | Aumenta complejidad y riesgo | Automatización fallida por seguridad |
| `riesgo_datos` | sensible | Si el proceso maneja datos sensibles | "tengo datos de clientes", "info financiera", "datos de salud", "información legal" | Activa revisión humana | Exposición de datos |
| `tipo_automatizacion` | clasificación | Tipo de automatización sugerida | "un bot", "un asistente", "que se haga solo", "que me avise", "que cargue automáticamente" | Orienta la solución propuesta | Mezcla de expectativas |
| `offer_decision` | clasificación | Decisión comercial preliminar | señales de factibilidad, riesgo, evidencia e intención | Separa automatizable de vendible hoy | Promesas comerciales excesivas |
| `service_maturity` | clasificación | Madurez del servicio | patrón core, piloto, oportunidad o paquete futuro | Evita vender como core lo no validado | Recomendación desalineada |
| `human_review_required` | clasificación | Marca de revisión humana | datos sensibles, MFA, finanzas, credenciales, incertidumbre | Protege seguridad y calidad | Automatización riesgosa |
| `risk_level` | clasificación | Riesgo bajo, medio o alto | criticidad, datos, acceso, irreversibilidad | Ordena límites y revisión humana | Diagnóstico demasiado simple |
| `presupuesto_aproximado` | continuidad futura | Orden de magnitud o tipo de alcance | "cuánto sale", "tengo presupuesto", "depende el precio", "es caro" | Útil para propuesta futura, no para diagnóstico inicial | Conversación comercial prematura |
| `interes_en_diagnostico` | continuidad futura | Busca diagnóstico, propuesta o continuidad | "quiero saber si se puede", "necesito un presupuesto" | Define tono y próximo paso | Conversación desalineada |
| `siguiente_paso` | MVP / futuro | Paso recomendado post-diagnóstico | "¿cómo sigo?", "¿con quién hablo?", "mandame información" | Cierra la respuesta con claridad | Recomendación incompleta |
| `nombre` | continuidad futura | Nombre del usuario | "me llamo Juan", "soy María" | Handoff futuro si quiere avanzar | No afecta diagnóstico |
| `apellido` | continuidad futura | Apellido del usuario | el usuario lo ofrece o acepta handoff | Handoff futuro si quiere avanzar | No afecta diagnóstico |
| `whatsapp_contacto` | continuidad futura | WhatsApp del usuario | "escribime al 11..." | Continuidad futura por WhatsApp | No afecta diagnóstico |
| `email_contacto` | continuidad futura | Email del usuario | "mandame mail a ..." | Canal alternativo futuro | No afecta diagnóstico |
| `empresa` | continuidad futura | Empresa del usuario | "tengo un negocio", "trabajo en X" | Contexto comercial futuro opcional | No afecta diagnóstico inicial |
| `diagnostic_code` | continuidad futura | Código único de diagnóstico | se asignará en capa futura | Continuidad futura sin perder contexto | No afecta diagnóstico inicial |

---

## Slots críticos para diagnóstico inicial

### proceso_a_automatizar

**Definición:** descripción del proceso concreto que el usuario
quiere mejorar o automatizar. Es la base de todo el diagnóstico.

**Señales textuales:**
- "cargo datos en Excel todos los días"
- "respondo WhatsApp a clientes"
- "saco reportes de ventas una vez por semana"
- "hago facturas manualmente"
- "tengo que publicar en la web"
- "hago seguimiento de leads"

**Ejemplos de extracción:**
- "cargo datos" → proceso de carga manual
- "respondo WhatsApp" → atención al cliente por WhatsApp
- "saco reportes" → generación periódica de reportes
- "hago facturas" → facturación manual

**Pregunta recomendada:**
"Contame un poco más. ¿Qué tarea concreta te gustaría
automatizar o simplificar?"

**Cuándo no preguntar:**
Si el usuario ya describió el proceso con suficiente detalle
en su primer mensaje.

**Relación con factibilidad:**
La factibilidad depende directamente del proceso. Un proceso
manual sin API es distinto de un proceso con integración
disponible.

---

### dolor_principal

**Definición:** lo que más molesta, urge o preocupa del proceso
actual. Es la motivación real del usuario.

**Señales textuales:**
- "me lleva mucho tiempo"
- "se me pierden los mensajes"
- "me olvido de hacer seguimiento"
- "es tedioso"
- "tardo horas"
- "no tengo visibilidad"
- "dependemos de una persona"

**Ejemplos:**
- "pierdo tiempo" → dolor por eficiencia
- "se pierden leads" → dolor por oportunidad
- "no sé qué pasó" → dolor por trazabilidad
- "dependemos de una persona" → dolor por riesgo operativo

**Pregunta recomendada:**
"¿Qué es lo que más te molesta del proceso actual o te
gustaría mejorar primero?"

**Relación con impacto:**
El impacto de la automatización se mide en función del dolor
resuelto. A más dolor, mayor valor percibido.

---

### herramienta_actual

**Definición:** qué usa el usuario hoy para ejecutar el proceso.

**Ejemplos:**
- CRM: Kommo, HubSpot, Zoho, Salesforce, Pipedrive
- Mensajería: WhatsApp personal, WhatsApp Business, WhatsApp Cloud API
- Planillas: Excel local, Google Sheets, planilla compartida
- Publicidad: Facebook Ads, Instagram Ads
- Formularios: Google Forms, Typeform, Jotform
- Email: Gmail, Outlook, correo corporativo
- Plataforma web: sistema propio, plataforma de terceros
- Ninguna herramienta / papel

**Pregunta recomendada:**
"¿Dónde lo hacen hoy? ¿Usan alguna herramienta, planilla
o sistema?"

**Relación con complejidad:**
La herramienta actual determina la complejidad de integración.
Un CRM con API es distinto de una planilla local o papel.

---

### frecuencia

**Definición:** cada cuánto se ejecuta el proceso.

**Ejemplos:**
- Diario
- Varias veces al día
- Semanal
- Mensual
- Cada vez que ocurre un evento (cada lead, cada venta)
- Al cierre del mes

**Pregunta recomendada:**
"¿Cada cuánto hacen esa tarea? ¿Varias veces al día,
semanal, mensual?"

**Relación con prioridad:**
A mayor frecuencia, mayor retorno potencial de la automatización.

---

### volumen

**Definición:** cantidad de operaciones en un período.

**Ejemplos:**
- 10 leads por día
- 200 mensajes de WhatsApp por semana
- 50 facturas por mes
- 5 reportes mensuales
- Cientos de filas de datos

**Pregunta recomendada:**
"¿Más o menos cuántas veces por {frecuencia} ocurre?
¿Unas pocas o muchas?"

**Relación con impacto:**
El volumen determina el retorno de la automatización. Alto
volumen + alta frecuencia = alto impacto.

---

## Slots recomendados

### industria

**Definición:** rubro o sector del usuario.

**Señales textuales:** "tengo un comercio", "soy contador",
"tengo una inmobiliaria", "trabajo en salud", "somos una
consultora".

**Pregunta recomendada:**
"¿De qué rubro es tu empresa o proyecto?"

**Uso en diagnóstico:** el tipo de automatización, los canales
y las herramientas varían significativamente por industria.

---

### area_negocio

**Definición:** área interna donde ocurre el proceso.

**Señales textuales:** "en ventas", "en administración",
"en backoffice", "en atención al cliente", "en producción".

**Pregunta recomendada:**
"¿En qué área de la empresa ocurre ese proceso?"

**Uso en diagnóstico:** ayuda a clasificar y priorizar la
automatización dentro de la organización.

---

### responsable

**Definición:** quién ejecuta o supervisa el proceso.

**Señales textuales:** "lo hago yo", "lo hace mi asistente",
"lo hace el equipo de ventas", "pasa por varias personas".

**Pregunta recomendada:**
"¿Quién hace esa tarea hoy? ¿Una persona, varias, pasan
por distintas áreas?"

**Uso en diagnóstico:** dimensiona el alcance del cambio y
la necesidad de coordinación.

---

### fuente_datos

**Definición:** de dónde vienen los datos del proceso.

**Señales textuales:** "de WhatsApp", "del CRM", "de una
planilla", "de un formulario web", "del sistema de facturación".

**Pregunta recomendada:**
"¿De dónde salen los datos que necesitás para esa tarea?"

**Uso en diagnóstico:** determina si hay API disponible o
si requiere integración especial.

---

### urgencia

**Definición:** urgencia de la mejora.

**Señales textuales:** "ya debería haberlo resuelto",
"estamos saturados", "lo vengo pateando hace meses",
"recién lo estoy evaluando".

**Pregunta recomendada:**
"¿Qué tan urgente es para ustedes resolver esto?"

**Uso en diagnóstico:** define la velocidad de acción y el
siguiente paso recomendado.

---

### impacto_economico

**Definición:** estimación del costo u horas del proceso actual.

**Señales textuales:** "perdemos tiempo", "tardo 2 horas por
día", "son 3 personas medio tiempo", "nos cuesta plata no
tenerlo resuelto".

**Pregunta recomendada:**
"¿Cuánto tiempo o gente están dedicando hoy a esa tarea?"

**Uso en diagnóstico:** ayuda a estimar impacto y priorizar entre
múltiples oportunidades. No obliga a preguntar presupuesto.

---

### tipo_automatizacion

**Definición:** tipo de solución que el usuario imagina o
que el asistente sugiere según el caso.

**Señales textuales:** "un bot", "un asistente", "que se haga
solo", "que me avise", "que cargue automáticamente".

**Pregunta recomendada:**
"¿Tenés idea de qué tipo de solución te gustaría? ¿Un
asistente que responda, algo que cargue datos automáticamente,
o reportes que se generen solos?"

**Uso en diagnóstico:** orienta la solución propuesta y
alinea expectativas.

---

## Slots de herramientas y canales

### crm_actual

**Definición:** qué CRM usa el usuario.

**Ejemplos:**
- Kommo
- HubSpot
- Zoho
- Salesforce
- Pipedrive
- Una planilla / Excel
- Ninguno

**Pregunta recomendada:**
"¿Usan algún CRM para ordenar clientes o leads?"

---

### whatsapp_uso

**Definición:** cómo usa WhatsApp el usuario.

**Diferenciar:**
- **WhatsApp personal:** para hablar con clientes desde el
  número personal.
- **WhatsApp Business:** app gratuita con perfil de negocio.
- **WhatsApp Cloud API:** integración oficial de Meta con
  API y múltiples agentes.
- **Proveedor externo:** Gupshup, WATI, etc.
- **No sabe:** el usuario usa WhatsApp pero no conoce el tipo.

**Pregunta recomendada:**
"¿Usás WhatsApp para hablar con clientes? ¿Tenés WhatsApp
Business o usás el WhatsApp personal?"

---

### facebook_ads_uso

**Definición:** si usa publicidad en Meta.

**Diferenciar:**
- **Campañas activas:** tiene campañas en Facebook o Instagram.
- **Formularios de leads:** usa formularios nativos de Meta.
- **Mensajes:** recibe mensajes por Facebook/Instagram.
- **No usa.**

**Pregunta recomendada:**
"¿Hacés publicidad en Facebook o Instagram? ¿Te llegan
consultas por ahí?"

---

### excel_sheets_uso

**Definición:** cómo usa planillas.

**Diferenciar:**
- **Excel local:** planillas en la computadora, sin compartir.
- **Google Sheets:** planillas online compartidas.
- **Planilla compartida:** archivo de Excel en red o OneDrive.
- **Reportes manuales:** arma reportes a mano desde el sistema.

**Pregunta recomendada:**
"¿Usás Excel o Google Sheets para llevar cuentas, reportes
o seguimiento?"

---

## Slots sensibles

Los slots sensibles no buscan obtener secretos ni detalles privados.
Sirven para detectar riesgo, alcance y necesidad de revisión humana.
Si el usuario intenta compartir credenciales, tokens o datos privados,
el asistente debe detener esa línea y explicar que no hace falta
compartirlos.

### acceso_disponible

**Definición:** si el usuario tiene acceso autorizado a las
herramientas o plataformas que necesita para la automatización.

**Regla importante:** no pedir credenciales. Solo preguntar
si existe acceso autorizado.

**Pregunta recomendada:**
"¿Existe acceso autorizado a las cuentas o sistemas donde habría
que integrar, sin compartir usuarios ni contraseñas por acá?"

**Señal de riesgo:** si el usuario dice que comparte
credenciales o usa cuentas compartidas, activar
`human_review_required`.

**Límite:** no pedir nombres de usuario, contraseñas, tokens,
API keys, códigos de verificación ni capturas con datos sensibles.

---

### mfa

**Definición:** si el proceso o plataforma requiere MFA
(multi-factor authentication).

**Explicación:** MFA aumenta la complejidad de la automatización
y puede requerir revisión humana.

**Señales textuales:** "pide código de verificación", "tengo
que aprobar desde el teléfono", "hay doble factor", "manda
un código al WhatsApp".

**Pregunta recomendada:**
"¿El acceso a esa plataforma pide algún código de verificación
o doble factor?"

**Acción:** si hay MFA, considerar `pilot` o
`human_review_required`.

**Límite:** no sugerir saltar MFA, compartir códigos ni operar
con aprobaciones prestadas. La automatización debe respetar los
controles de seguridad existentes.

---

### riesgo_datos

**Definición:** señales de que el proceso maneja datos
sensibles.

**Señales de datos sensibles:**
- Datos personales (nombre, documento, dirección, teléfono)
- Datos financieros (cuentas, tarjetas, ingresos)
- Datos de salud (historias clínicas, diagnósticos)
- Datos legales (contratos, juicios, documentación)
- Datos de menores
- Contraseñas o tokens
- Información bancaria

**Pregunta recomendada:**
"¿El proceso trabaja con datos de clientes o información
sensible? ¿Algo financiero, de salud, legal o datos
personales?"

**Acción:** si hay datos sensibles, activar
`human_review_required`.

**Límite:** no pedir muestras reales, documentos internos, datos
de menores, información bancaria, historias clínicas, contratos
confidenciales ni datos financieros detallados en la conversación
pública.

---

## Slots de continuidad comercial futura

Estos slots son de diseño futuro. En el MVP conversacional inicial no
se preguntan ni se convierten en formulario. Solo se registran señales
de continuidad cuando el usuario pide avanzar, cotizar, preparar una
propuesta o deja voluntariamente sus datos.

### presupuesto_aproximado

**Definición:** orden de magnitud del presupuesto disponible.

**Regla de MVP:** no preguntar presupuesto en el diagnóstico inicial.
Si el usuario pide precio o cotización, responder con criterio de
alcance y seguir diagnosticando sin forzar monto.

**Pregunta futura recomendada suave (no activa en MVP inicial):**
"¿Querés que lo pensemos como una prueba chica o como una
implementación más completa?"

**Pregunta alternativa si el usuario pide cotización:**
"Para orientar una propuesta sin inventar precio, primero conviene
definir alcance. ¿Buscás una prueba acotada o algo más integral?"

**Límite:** no forzar monto. Si el usuario ofrece presupuesto,
tomarlo como contexto comercial, no como condición para diagnosticar.

---

## Slots futuros de lead capture y Step-to-Action

### nombre, apellido, whatsapp_contacto, email_contacto, empresa, diagnostic_code

**Reglas:**
- No se piden en el MVP conversacional inicial.
- Solo se aceptan si el usuario los ofrece espontáneamente o pide
  explícitamente contacto, presupuesto o propuesta.
- En la extensión futura, pedirlos de forma transparente, explicando
  para qué se usan.
- En la extensión futura, pedir el mínimo necesario: nombre, apellido
  y WhatsApp para handoff.
- Email y empresa siguen siendo opcionales.
- WhatsApp se reserva para continuidad comercial futura, no para
  diagnosticar.
- `diagnostic_code` pertenece al diseño futuro de continuidad, no al
  diagnóstico actual.
- Preparar mensaje o URL de WhatsApp hacia Team360 corresponde a una
  fase posterior.
- Si el usuario no quiere dejar datos, seguir orientando de forma
  general.

**Mensaje sugerido futuro, no activo en MVP inicial:**

> "Puedo dejar este diagnóstico asociado a un código para que el
> equipo de Team360 lo revise sin perder el contexto. Si querés
> avanzar, pasame nombre, apellido y WhatsApp. Email y empresa son
> opcionales. Si preferís, también puedo seguir orientándote sin
> tomar tus datos."

**Mensaje de handoff con `diagnostic_code`:**

Este mensaje es de uso futuro. No debe usarse como respuesta normal
del MVP inicial.

> "El código de este diagnóstico es `{diagnostic_code}`. Sirve para
> retomar la conversación sin que tengas que repetir todo. No hace
> falta que compartas contraseñas, tokens ni documentos sensibles."

**Cuándo registrar señales futuras de Step-to-Action:**
- El usuario pide presupuesto o precio.
- El usuario muestra intención de contratar.
- El diagnóstico es positivo y el usuario quiere avanzar.
- El usuario pide hablar con alguien.
- El caso requiere `human_review_required` y hay que derivar.

**Cuándo no pedir datos personales todavía:**
- El usuario recién está explorando y no pidió continuidad.
- Falta entender el proceso mínimo.
- El usuario quiere orientación general sin compartir datos.
- El asistente todavía no dio ningún valor concreto.

---

## Preguntas dinámicas por escenario

Cada escenario orienta la próxima pregunta, no un flujo fijo. El
asistente debe adaptar el orden según lo que el usuario ya dijo y no
debe pedir datos comerciales antes de dar valor.

### Usuario quiere automatizar WhatsApp y CRM

**Señales:** "WhatsApp", "clientes", "mensajes", "CRM", "seguimiento",
"leads", "ventas".

**Slots probablemente presentes:** `whatsapp_uso`, `crm_actual`,
`proceso_a_automatizar`, `volumen`.

**Slots faltantes probables:** `herramienta_actual` (qué CRM),
`frecuencia`, `fuente_datos`.

**Pregunta recomendada:**
"Por lo que contás, parece un caso de seguimiento comercial.
¿Hoy las conversaciones quedan en un CRM, en WhatsApp o en
una planilla?"

**Offer decision probable:** `sellable_now` si el canal, el CRM y
los accesos están claros; `pilot` si requiere integración nueva.

**Riesgo:** si no tienen CRM o usan planilla, la complejidad
aumenta. Si comparten credenciales, activar
`human_review_required`.

**Señal futura de Step-to-Action:** si el usuario pide avanzar,
cotización o revisión del caso. No pedir WhatsApp solo porque mencionó
WhatsApp como canal operativo.

---

### Usuario carga datos manualmente en Excel

**Señales:** "Excel", "cargo", "planilla", "Sheet", "datos",
"manualmente".

**Slots probablemente presentes:** `excel_sheets_uso`,
`proceso_a_automatizar`.

**Slots faltantes probables:** `fuente_datos` (de dónde vienen),
`frecuencia`, `volumen`.

**Pregunta recomendada:**
"Esto suele ser automatizable si el origen de los datos es claro.
¿De dónde salen esos datos: un sistema, WhatsApp, otra planilla
o formularios?"

**Offer decision probable:** `sellable_now` si el alcance es simple
y los datos están disponibles; `pilot` si hay varias fuentes o reglas
de validación.

**Riesgo:** bajo o medio. Subir a `human_review_required` si la planilla
contiene datos financieros, salud, legales, menores o información
bancaria.

**Señal futura de Step-to-Action:** cuando el usuario quiera convertir
el diagnóstico en prueba o propuesta. No pedir presupuesto ni contacto
de entrada.

---

### Usuario no sabe qué automatizar

**Señales:** "no sé", "no estoy seguro", "qué se puede hacer",
"contame qué se puede automatizar", "no tengo idea".

**Slots probablemente presentes:** ninguno o muy pocos.

**Slots faltantes:** la mayoría de los slots críticos.

**Pregunta recomendada:**
"No hay problema. Para encontrar una oportunidad concreta:
¿hay alguna tarea repetitiva que te coma tiempo, se haga con
planillas o dependa mucho de una persona?"

**Offer decision probable:** `automatable` (esperar a identificar).

**Riesgo:** desconocido hasta identificar proceso, datos y herramientas.

**Señal futura de Step-to-Action:** no registrar todavía. Primero
ayudar a detectar uno o dos procesos posibles y dar orientación
preliminar.

---

### Usuario pide precio o presupuesto

**Señales:** "cuánto sale", "cuánto cuesta", "presupuesto",
"precio", "valor", "cotización".

**Slots probablemente presentes:** `interes_en_diagnostico`; puede no
haber contexto de proceso.

**Slots faltantes probables:** `proceso_a_automatizar`,
`herramienta_actual`, `frecuencia` o `volumen`.

**Acción:** dar valor antes de pedir datos personales. Primero entender
alcance. En el MVP inicial no activar handoff; solo registrar señal
futura si el usuario insiste en propuesta o contacto.

**Pregunta recomendada:**
"Puedo orientarte, pero para no inventar precio necesito ubicar el
alcance. ¿Qué proceso querés automatizar y hoy dónde lo hacen?"

**Offer decision probable:** no determinar hasta tener contexto.

**Riesgo:** medio por expectativa comercial. Evitar prometer precio,
plazo o implementación sin diagnóstico.

**Señal futura de Step-to-Action:** después de explicar el criterio,
si el usuario quiere propuesta o revisión humana. En el MVP inicial,
no pedir nombre, apellido ni WhatsApp; recomendar el próximo paso de
forma clara.

---

### Usuario menciona Facebook Ads o leads

**Señales:** "Facebook", "Instagram", "Ads", "publicidad",
"campaña", "leads", "formulario de Meta".

**Slots probablemente presentes:** `facebook_ads_uso`,
`canal_origen`.

**Slots faltantes probables:** `herramienta_actual` (cómo recibe
los leads), `crm_actual`.

**Pregunta recomendada:**
"Ahí suele haber valor en seguimiento y trazabilidad. ¿Los leads
llegan a un CRM, a Excel, a WhatsApp o a un mail?"

**Offer decision probable:** `sellable_now` si el flujo es comercial
claro; `pilot` si hay integración con Meta, CRM o varios canales.

**Riesgo:** si los leads se pierden por falta de seguimiento,
la automatización tiene alto impacto. Revisar permisos de cuentas
publicitarias antes de prometer integración.

**Señal futura de Step-to-Action:** cuando el usuario pida ordenar el
flujo, medir pérdida de leads o avanzar con una prueba.

---

### Usuario quiere automatizar documentos o PDFs

**Señales:** "documentos", "PDF", "facturas", "contratos",
"formularios", "papeles", "digitalizar", "lectura".

**Slots probablemente presentes:** `proceso_a_automatizar`,
`fuente_datos`.

**Slots faltantes probables:** `volumen` (cantidad de documentos),
`tipo_automatizacion`.

**Pregunta recomendada:**
"Parece un caso de extracción, consulta o RAG sobre documentos.
¿Qué tipo de documentos son y están en formato digital?"

**Offer decision probable:** `sellable_now` para RAG sobre documentos
propios claros y con permisos definidos; `pilot` si requiere OCR,
limpieza o clasificación compleja.

**Riesgo:** medio. Subir a `human_review_required` si hay contratos,
salud, menores, datos legales, financieros o información confidencial.

**Señal futura de Step-to-Action:** cuando el usuario tenga documentos
identificados y quiera validar alcance. No pedir archivos sensibles ni
datos de contacto en el MVP inicial.

---

### Usuario menciona ERP, bancos, conciliaciones o datos financieros

**Señales:** "ERP", "banco", "conciliación", "cuentas", "pagos",
"facturación", "balance", "contable", "SICOM", "PILAGA".

**Slots probablemente presentes:** `proceso_a_automatizar`,
`riesgo_datos`.

**Slots faltantes probables:** `herramienta_actual`, `acceso_disponible`,
`mfa`.

**Pregunta recomendada:**
"Esto suena a datos financieros, contables o de ERP, así que conviene
tratarlo con cuidado. ¿Hablamos de reportes operativos simples o de
conciliaciones bancarias/contables con impacto sensible?"

**Offer decision probable:** `human_review_required` o
`future_opportunity`.

**Riesgo:** alto. Activar `human_review_required` si hay
datos financieros, bancos, conciliaciones avanzadas, acciones
irreversibles o acceso no documentado.

**Señal futura de Step-to-Action:** si el usuario quiere revisión
humana o hay impacto sensible. No pedir datos mínimos para handoff en
el MVP inicial ni datos financieros detallados.

---

### Usuario menciona credenciales, MFA o accesos de terceros

**Señales:** "usuario y contraseña", "código de verificación",
"doble factor", "compartimos la clave", "token", "MFA",
"aprobación desde el teléfono".

**Slots probablemente presentes:** `mfa`, `acceso_disponible`,
`riesgo_datos`.

**Slots faltantes probables:** alcance del proceso, tipo de plataforma
y si existe acceso autorizado por rol.

**Acción inmediata:** activar `human_review_required`.

**Pregunta recomendada:**
"Esto requiere manejar accesos con cuidado. No compartas claves ni
códigos por acá. ¿Existe un usuario autorizado y permisos definidos
para operar esa plataforma?"

**Offer decision probable:** `human_review_required`; `not_recommended`
si el usuario pide saltar MFA, compartir códigos o usar credenciales
de terceros sin autorización.

**Riesgo:** alto por seguridad, cumplimiento y posible bloqueo de
cuentas.

**Señal futura de Step-to-Action:** registrar continuidad futura si el
caso tiene valor y requiere revisión humana. No activar handoff en el
MVP inicial. No pedir contraseñas, tokens ni capturas de sesión.

---

### Usuario quiere un asistente que responda sobre documentos propios

**Señales:** "documentos", "manuales", "políticas", "procedimientos",
"reglamentos", "normas", "base de conocimiento", "consultas
internas".

**Slots probablemente presentes:** `proceso_a_automatizar`,
`fuente_datos`.

**Slots faltantes probables:** `volumen` (cantidad de documentos),
`tipo_automatizacion`, `riesgo_datos`.

**Pregunta recomendada:**
"Este suele ser un buen caso para RAG si los documentos son propios
y están claros. ¿Son documentos internos ya digitales y de qué tipo?"

**Offer decision probable:** `sellable_now` si hay documentos propios,
permisos y alcance claro; `pilot` si hay desorden documental, OCR o
restricciones de acceso.

**Riesgo:** bajo a medio. Subir a `human_review_required` si contiene
datos personales sensibles, legales, salud, menores o información
confidencial.

**Señal futura de Step-to-Action:** cuando el usuario quiera validar
un corpus o preparar una prueba. No pedir documentos sensibles ni datos
de contacto en la conversación pública del MVP.

---

## Reglas para no sobrepreguntar

1. **Máximo 1 a 3 preguntas por turno.** Si necesitás más,
   priorizar las que cambian el diagnóstico.

2. **Si el usuario da contexto rico**, responder diagnóstico
   preliminar antes de preguntar.

3. **Si falta proceso**, preguntar proceso primero. Todo lo
   demás depende de entender qué quiere automatizar.

4. **Si falta herramienta**, preguntar herramienta. La
   complejidad depende de dónde se hace hoy.

5. **Si falta frecuencia o volumen**, preguntar uno de los
   dos primero. Con uno alcanza para estimar.

6. **Si hay riesgo** (credenciales, MFA, datos sensibles),
   preguntar por acceso autorizado y tipo de datos.

7. **Si hay intención comercial** (presupuesto, precio,
   contratar), registrar señal futura de continuidad. No pedir datos
   de contacto en el MVP inicial salvo pedido explícito del usuario.

8. **No pedir presupuesto de entrada.** Si el usuario pide precio,
   cambiar la conversación a alcance: prueba chica o implementación
   más completa.

9. **No pedir WhatsApp de entrada.** WhatsApp de contacto pertenece
   al handoff comercial futuro, no al diagnóstico.

10. **No preguntar por datos sensibles en detalle.** Detectar la
    categoría de riesgo alcanza para marcar revisión humana.

---

## Priorización de preguntas

| Condición | Pregunta prioritaria | Razón | Siguiente posible pregunta |
|-----------|---------------------|-------|---------------------------|
| No se entiende el proceso | "¿Qué tarea concreta querés automatizar?" | Sin proceso no hay diagnóstico | "¿Dónde lo hacen hoy?" |
| Hay proceso pero no herramienta | "¿Dónde lo hacen hoy?" | La complejidad depende de la herramienta | "¿Cada cuánto ocurre?" |
| Hay herramienta pero no volumen | "¿Cuántas veces por {frecuencia} ocurre?" | El volumen determina el impacto | "¿Quién lo hace?" |
| Hay WhatsApp o CRM | "¿Hoy lo cargan manualmente o está integrado?" | Diferencia entre automatización e integración | "¿Usan planillas además?" |
| Hay presupuesto / intención | "¿Buscás una prueba chica o una implementación más completa?" | Entender alcance sin forzar monto | Registrar señal futura de continuidad |
| Hay credenciales o MFA | "¿El acceso sería con usuario autorizado y permisos definidos?" | Evaluar seguridad | Activar human_review_required |
| No sabe qué automatizar | "Contame algo de tu día a día que sientas repetitivo" | Explorar sin presionar | Identificar el primer proceso |
| Quiere dejar datos | "Puedo tomarlo como señal de continuidad futura." | No convertir el diagnóstico en formulario | Aceptar datos solo si los ofrece espontáneamente |

---

## Señales para Offer Decision

La decisión de oferta debe ser conservadora. `automatable` no significa
`sellable_now`; solo indica que el proceso podría automatizarse.

| Señales en el texto | Offer decision probable |
|--------------------|----------------------|
| Proceso repetitivo + bajo riesgo + herramienta conocida | `automatable` / `pilot` / `sellable_now` según evidencia |
| Proceso claro + volumen alto + acceso disponible | `pilot` / `sellable_now` si el alcance está acotado |
| Plataforma sin API + MFA + credenciales compartidas | `pilot` / `human_review_required` |
| Datos financieros sensibles + sin acceso documentado | `human_review_required` |
| Trading automático, cripto, mercados financieros | `future_opportunity` / `not_recommended` |
| Usuario pide saltar medidas de seguridad | `not_recommended` |
| Automatización bancaria o contable avanzada | `human_review_required` / `future_opportunity` |
| ERP completo, gestión empresarial amplia | `future_opportunity` |
| Marketplaces complejos con cuentas, publicaciones o pagos | `pilot` / `future_opportunity` / `human_review_required` |
| Proceso no claro, sin volumen, sin herramienta | `automatable` (exploratorio) |

---

## Señales para Service Maturity

| Señales en el texto | Service maturity probable |
|--------------------|--------------------------|
| CRM, WhatsApp, leads, ventas, reportes comerciales | `CORE_VALIDADO` o `PILOTO_VALIDADO` según integración |
| Documentos propios claros, permisos y RAG acotado | `CORE_VALIDADO` |
| Browser automation, integración sin API | `PILOTO_VALIDADO` por defecto |
| Generación de video o contenido audiovisual | `OPORTUNIDAD` |
| Trading automático u operación financiera automática | `PAQUETE_FUTURO` o `NO_OFRECER_AUN` |
| ERP amplio, conciliaciones avanzadas, marketplaces complejos | `PAQUETE_FUTURO` |
| Pedidos de saltar seguridad, accesos compartidos | `NO_OFRECER_AUN` |

No prometer como core lo que no está validado. Marketplaces, ERP,
trading, finanzas avanzadas y generación audiovisual no son core actual
por aparecer como automatizables.

---

## Referencias cruzadas silenciosas

- Si el usuario menciona **WhatsApp**, revisar seguridad,
  accesos, MFA y canal operativo. No pedir WhatsApp de contacto
  hasta que haya intención de continuidad.
- Si menciona **CRM**, revisar integraciones y trazabilidad
  comercial.
- Si menciona **Excel** o **reportes**, revisar KPI y
  backoffice.
- Si menciona **documentos propios**, revisar RAG y knowledge
  base.
- Si menciona **credenciales**, **MFA** o **cuentas de
  terceros**, marcar `human_review_required`.
- Si pide **presupuesto**, registrar señal futura de Step-to-Action
  después de dar valor y sin forzar monto.
- Si el caso es automatizable pero no vendible hoy, clasificar
  como `future_opportunity` o `human_review_required`.
- Si el usuario **no sabe qué automatizar**, usar checklist
  exploratorio.
- Si menciona **ERP**, **bancos**, **conciliaciones** o **finanzas**,
  separar reportes simples de procesos sensibles y activar revisión
  humana cuando corresponda.

---

## UI Hints

Sugerencias para la experiencia conversacional del asistente.

### Badges sugeridos

- **Contexto detectado** — se identificó el proceso
- **Faltan datos mínimos** — no se puede diagnosticar aún
- **Alta prioridad** — alto volumen y frecuencia
- **Requiere revisión humana** — datos sensibles o MFA
- **Posible piloto** — caso para prueba controlada
- **Riesgo por accesos** — credenciales o MFA
- **Señal de continuidad futura** — no solicitar datos todavía

### Checklist sugerido

- [ ] Proceso identificado
- [ ] Herramienta actual identificada
- [ ] Frecuencia estimada
- [ ] Volumen estimado
- [ ] Riesgo identificado
- [ ] Próximo paso sugerido

### Risk Flags

- **Datos sensibles** — activar `human_review_required`
- **Credenciales** — activar `human_review_required`
- **MFA** — aumentar complejidad
- **Plataforma de terceros** — puede requerir integración especial
- **Proceso financiero** — activar `human_review_required`
- **Acción irreversible** — requiere confirmación humana

### Recommended Next Steps

1. Confirmar el proceso que el usuario describió.
2. Confirmar la herramienta actual.
3. Estimar frecuencia o volumen.
4. Evaluar riesgo del proceso.
5. Proponer piloto o solución directa.
6. Sugerir próximo paso recomendado; registrar señal futura de
   Step-to-Action si hay intención comercial explícita.

---

## Calidad para SemanticChunker

Este documento debe ser legible por humanos y recuperable por RAG.
Cada sección debe poder usarse como chunk sin depender demasiado de
lo anterior.

### Reglas de chunking semántico

- Mantener secciones autocontenidas: definición, regla, ejemplo y
  excepción deben estar cerca.
- Usar encabezados descriptivos, no genéricos.
- Separar slots de diagnóstico, clasificación y continuidad comercial
  futura.
- Separar reglas de seguridad de ejemplos comerciales.
- Evitar párrafos largos cuando una tabla o lista simple sea más clara.
- No duplicar el package manual; referenciarlo cuando el criterio sea
  de oferta, madurez o límite comercial.
- Mantener `Vera` solo como nombre visible. No crear identificadores
  técnicos con ese nombre.

### Regla de ejemplo y excepción

Ejemplo: "RAG sobre documentos propios" puede ser `sellable_now` si los
documentos son propios, digitales, claros y con permisos definidos.

Excepción: si esos documentos contienen datos de salud, menores, datos
legales sensibles o información financiera detallada, activar
`human_review_required` antes de tratarlo como servicio simple.

---

## Estilo de redacción

- Español claro, profesional, sin humo.
- Orientado a negocio, útil para RAG.
- Secciones autocontenidas, párrafos cortos.
- Bullets cuando ayuden a la legibilidad.
- No demasiado técnico, no demasiado marketinero.
- Preparado para SemanticChunker: cada sección con contexto
  mínimo propio.
