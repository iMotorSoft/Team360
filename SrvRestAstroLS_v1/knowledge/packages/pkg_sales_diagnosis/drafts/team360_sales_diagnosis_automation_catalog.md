---
document_code: team360_sales_diagnosis_automation_catalog
status: draft
ingestion_status: not_ready
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360
workspace_code: team360_live
package_code: pkg_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: automatizaciones
topic_key: automation_catalog
document_type: reference
visibility: internal
access_tags:
  - internal
  - package:sales_diagnosis
  - topic:automation_catalog
  - topic:diagnosis
locale: es
version: "0.1"
title: "Catálogo inicial de automatizaciones diagnosticables"
source_type: markdown
node_path: "/automatizaciones/automation-catalog"
risk_level: medium
step_to_action_status: planned_extension
approval_notes: >
  Borrador inicial del catalogo de automatizaciones diagnosticables
  para pkg_sales_diagnosis. Enumera casos tipicos que Vera puede
  diagnosticar sin limitarse a paquetes disponibles hoy. No esta
  aprobado para ingesta. Debe revisarse con GPT-5.5 antes de promover
  a approved/.
---

# Catálogo inicial de automatizaciones diagnosticables

> Este documento está en estado draft. No debe ingerirse ni moverse
> a `approved/` hasta pasar revisión editorial, validación de límites
> comerciales y prueba conversacional.

---

## L0 Abstract

Este documento enumera los casos típicos de automatización, IA,
integración y mejora operativa que Vera puede diagnosticar. El
catálogo no es una lista cerrada de servicios ni un listado de
precios: es una guía para que Vera oriente diagnósticos, mejore
retrieval, identifique riesgos y clasifique casos de forma
consistente.

Vera puede diagnosticar casos que no estén en este catálogo. La
ausencia de un caso en la lista no significa que no sea factible,
sino que requiere evaluación caso a caso.

---

## Propósito

Este catálogo sirve para:

- **Orientar diagnósticos**: dar a Vera referencias concretas de
  casos típicos y sus criterios de evaluación.
- **Mejorar retrieval**: los casos catalogados pueden enlazarse a
  documentos de conocimiento más detallados.
- **Dar ejemplos concretos**: ayudar al usuario a reconocer su
  caso a partir de patrones conocidos.
- **Separar factibilidad de disponibilidad**: cada caso declara
  si está disponible hoy como paquete o no.
- **Identificar riesgos**: cada caso lista los factores de riesgo
  conocidos.
- **Detectar cuándo falta información**: cada caso indica los
  datos mínimos necesarios para diagnosticar.
- **Reconocer cuándo corresponde revisión humana**: cada caso
  declara si requiere human_review_required por defecto.

---

## Precedencia documental

- Para seguridad, credenciales, MFA, QR, Face ID, datos sensibles,
  bloqueo o revisión humana, prevalece
  [[team360_sales_diagnosis_security_hitl_policy]].
- Para clasificación final de factibilidad, disponibilidad,
  service_maturity, offer_decision y diagnosis_category, prevalece
  [[team360_sales_diagnosis_feasibility_availability_matrix]].
- Este catálogo aporta ejemplos y valores por defecto; no convierte un
  caso en oferta disponible.
- Para estilo conversacional, prevalece
  [[team360_sales_diagnosis_response_playbook]].

---

## Principios del catálogo

1. El usuario puede traer casos no listados sin que Vera cierre
   la conversación con "no tenemos ese servicio".
2. Un caso no listado puede ser diagnosticable y hasta factible.
3. Un caso diagnosticable puede no estar disponible como paquete
   inmediato de Team360.
4. Un caso disponible como paquete puede requerir validación de
   accesos, datos o permisos antes de comprometer implementación.
5. Un caso técnicamente factible puede no ser recomendable por
   riesgo, costo o impacto.
6. Si hay riesgo, datos sensibles, credenciales, MFA, QR, Face ID,
   finanzas, decisiones legales o clientes finales, debe evaluarse
   `human_review_required`.
7. Team360 no sustituye controles nativos de seguridad. Si una
   aplicación pide código, MFA, QR o validación biométrica, debe
   completarlo el usuario autorizado.

---

## Columnas estándar para cada automatización

Cada caso del catálogo se describe con estos campos:

| Campo | Descripción |
|-------|-------------|
| `automation_case` | Nombre del caso de automatización. |
| `descripción` | Breve descripción del tipo de proceso. |
| `user_intent_examples` | Ejemplos de cómo el usuario podría plantearlo. |
| `typical_tools` | Herramientas típicas involucradas. |
| `minimum_information_needed` | Datos mínimos para diagnosticar. |
| `technical_feasibility_default` | Valor típico de factibilidad técnica. |
| `operational_feasibility_default` | Valor típico de factibilidad operativa. |
| `availability_status` | Disponibilidad actual como paquete/servicio. |
| `service_maturity` | Madurez del servicio. |
| `diagnosis_category` | Categoría típica de diagnóstico. |
| `human_review_required_default` | Si requiere revisión humana por defecto. |
| `key_risks` | Principales riesgos a considerar. |
| `safe_response_pattern` | Patrón de respuesta recomendado. |
| `notes` | Notas adicionales. |

`human_review_required_default: conditional` es un valor editorial del
catálogo, no una decisión final para responder al usuario. Antes de
ofrecer un diagnóstico o siguiente paso, Vera debe resolverlo como
`true` o `false` usando la política de seguridad/HITL.

---

## Catálogo inicial de casos

### A. CRM + leads

| Campo | Valor |
|-------|-------|
| automation_case | Captura, clasificación y seguimiento de leads |
| descripción | Automatización del proceso comercial: captura de leads desde formularios, WhatsApp o redes, clasificación por etapa, asignación a vendedor y seguimiento. |
| user_intent_examples | "Quiero que los leads de Facebook vayan al CRM solos", "Necesito seguimiento automático de clientes", "Los leads se pierden porque no los cargamos rápido" |
| typical_tools | Kommo, HubSpot, Pipedrive, planillas, formularios (Google Forms, Typeform), WhatsApp |
| minimum_information_needed | herramienta actual, origen de leads, estados del embudo, volumen, responsable, canal de seguimiento |
| technical_feasibility_default | high |
| operational_feasibility_default | high |
| availability_status | available_now |
| service_maturity | CORE_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | false |
| key_risks | Datos de clientes, permisos de CRM, integración con WhatsApp, expectativas de seguimiento inmediato |
| safe_response_pattern | "Esto encaja con servicios disponibles. Para avanzar necesito saber qué CRM usan y de dónde vienen los leads." |
| notes | Si el CRM no tiene API o usan planilla sin estructura, la factibilidad baja. Si comparten credenciales, activar human_review_required. |

### B. WhatsApp comercial asistido

| Campo | Valor |
|-------|-------|
| automation_case | Atención, derivación, clasificación y recordatorios por WhatsApp |
| descripción | Automatización parcial de conversaciones de WhatsApp: respuestas frecuentes, clasificación de consultas, recordatorios, derivación a humano. |
| user_intent_examples | "Quiero responder WhatsApp más rápido", "Necesito un bot que clasifique consultas", "Los clientes preguntan siempre lo mismo" |
| typical_tools | WhatsApp Business, WhatsApp Cloud API, CRM, planillas |
| minimum_information_needed | tipo de mensajes, consentimiento, volumen, frecuencia, objetivo, responsable humano, plataforma usada |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Consentimiento del cliente, reputación, privacidad, volumen masivo sin control, clientes finales, WhatsApp handoff es planned_extension |
| safe_response_pattern | "Podemos ayudarte con WhatsApp comercial. Primero necesito saber si ya tenés WhatsApp Business y qué volumen de mensajes recibís." |
| notes | WhatsApp handoff automático y lead capture siguen como planned_extension. Si implica mensajes masivos sin consentimiento, activar human_review_required. |

### C. Facebook Ads / Meta leads

| Campo | Valor |
|-------|-------|
| automation_case | Captura de leads desde Meta, seguimiento y reporte de campañas |
| descripción | Automatización del flujo desde formularios de Meta hacia CRM, sistema de seguimiento o planilla. |
| user_intent_examples | "Los leads de Facebook no llegan a ningún lado", "Quiero que los formularios de Meta se carguen automáticamente" |
| typical_tools | Facebook Ads, Instagram Ads, CRM, planillas, WhatsApp |
| minimum_information_needed | herramienta actual, CRM, volumen de leads, cuenta publicitaria, permisos |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Permisos de cuenta publicitaria, calidad de datos, atribución, expectativas de integración inmediata |
| safe_response_pattern | "Esto puede automatizarse si tenés acceso a la cuenta publicitaria. ¿Ya conectaste los leads con algún CRM o planilla?" |
| notes | Si la cuenta es compartida o hay MFA, activar human_review_required. No prometer integración sin verificar acceso. |

### D. Excel / Google Sheets

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de carga, limpieza, seguimiento y reportes desde planillas |
| descripción | Automatización de procesos que hoy se hacen manualmente en planillas de cálculo. |
| user_intent_examples | "Cargo datos de WhatsApp a Excel todos los días", "Tengo una planilla que actualizo a mano", "Quiero que los reportes se generen solos" |
| typical_tools | Excel, Google Sheets, formularios, CRM, sistemas |
| minimum_information_needed | origen de datos, frecuencia, volumen, reglas de negocio, responsable, datos sensibles |
| technical_feasibility_default | high |
| operational_feasibility_default | high |
| availability_status | available_now |
| service_maturity | CORE_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | false |
| key_risks | Datos sensibles en planillas, fórmulas críticas, reglas no documentadas, datos financieros o de clientes |
| safe_response_pattern | "Las planillas suelen ser buen candidato si los datos y las reglas están claros. ¿De dónde vienen los datos que cargás?" |
| notes | Si la planilla contiene datos financieros, salud o legales, evaluar human_review_required. |

### E. Reportes KPI y dashboards

| Campo | Valor |
|-------|-------|
| automation_case | Consolidación de datos, métricas y paneles operativos o comerciales |
| descripción | Automatización de reportes periódicos desde múltiples fuentes hacia dashboards, PDFs o correos. |
| user_intent_examples | "Todos los meses pierdo un día armando reportes", "Quiero un dashboard que se actualice solo" |
| typical_tools | Excel, Google Sheets, CRM, sistemas, BI tools (o hacia ellas) |
| minimum_information_needed | fuentes de datos, frecuencia, métricas, formato esperado, responsable, destino del reporte |
| technical_feasibility_default | high |
| operational_feasibility_default | high |
| availability_status | available_now |
| service_maturity | CORE_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | false |
| key_risks | Datos financieros o sensibles en reportes, métricas mal definidas, expectativas de tiempo real |
| safe_response_pattern | "Los reportes periódicos son automatizables si las fuentes de datos están claras. ¿De dónde salen los datos hoy?" |
| notes | Si los reportes contienen datos financieros sensibles o decisiones basadas en ellos, evaluar human_review_required. |

### F. RAG sobre documentos propios

| Campo | Valor |
|-------|-------|
| automation_case | Asistente inteligente sobre documentos internos, manuales, políticas y FAQs |
| descripción | Creación de un asistente que responda preguntas sobre documentos propios del usuario (manuales, políticas, procedimientos). |
| user_intent_examples | "Quiero que los empleados puedan preguntar sobre políticas sin leer todo el manual", "Necesito un asistente que responda sobre nuestros procedimientos" |
| typical_tools | Documentos digitales (PDF, DOCX, TXT), base de conocimiento, sistemas internos |
| minimum_information_needed | tipo de documentos, volumen, confidencialidad, permisos, actualización, preguntas esperadas |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | CORE_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Documentos confidenciales, datos sensibles, permisos de acceso, actualización de la base, alucinaciones del modelo |
| safe_response_pattern | "RAG sobre documentos propios suele ser factible si los documentos son digitales y hay permisos definidos. ¿Qué tipo de documentos son?" |
| notes | Si contiene datos de salud, menores, legales o financieros, activar human_review_required. Separar documentos públicos, internos y confidenciales. |

### G. Atención al cliente / FAQ asistida

| Campo | Valor |
|-------|-------|
| automation_case | Respuestas frecuentes, clasificación de consultas y derivación en atención al cliente |
| descripción | Automatización parcial de atención al cliente: FAQ, clasificación de consultas, derivación a humano cuando corresponde. |
| user_intent_examples | "Siempre preguntan lo mismo, quiero automatizar respuestas", "Necesito clasificar consultas antes de derivar" |
| typical_tools | WhatsApp, CRM, chat web, formularios, base de conocimiento |
| minimum_information_needed | canal, volumen, tipo de consultas, responsable humano, base de respuestas existente |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Clientes finales, respuestas incorrectas, escalado a humano lento, privacidad, datos personales |
| safe_response_pattern | "La atención al cliente puede asistirse con automatización. ¿Qué canal usan y qué tipo de consultas reciben más seguido?" |
| notes | Si las respuestas automáticas afectan clientes finales sin supervisión, activar human_review_required. |

### H. Clasificación de consultas o tickets

| Campo | Valor |
|-------|-------|
| automation_case | Etiquetado, priorización, resumen y derivación de tickets o consultas |
| descripción | Automatización de la clasificación y priorización de tickets de soporte, consultas o solicitudes internas. |
| user_intent_examples | "Recibimos muchos tickets y perdemos tiempo clasificándolos", "Quiero que los casos urgentes se detecten solos" |
| typical_tools | CRM, sistema de tickets, formularios, email, WhatsApp |
| minimum_information_needed | volumen, categorías, criterios de prioridad, responsable, histórico de clasificación |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_now |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | false |
| key_risks | Clasificación incorrecta, sesgo en categorías, dependencia de histórico representativo |
| safe_response_pattern | "Clasificar tickets automáticamente suele ser viable si hay criterios claros. ¿Hoy cómo los ordenan?" |
| notes | Si la clasificación deriva en acciones automáticas sensibles, evaluar human_review_required. |

### I. Carga manual de datos

| Campo | Valor |
|-------|-------|
| automation_case | Repetición de tareas de copia y carga entre sistemas |
| descripción | Automatización de procesos donde un operador copia datos de un sistema, formulario o archivo a otro. |
| user_intent_examples | "Todos los días paso datos del sistema a Excel", "Cargo formularios al sistema manualmente" |
| typical_tools | Sistemas web, planillas, formularios, CRM, ERP |
| minimum_information_needed | origen, destino, volumen, frecuencia, reglas de transformación, accesos |
| technical_feasibility_default | medium |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | false |
| key_risks | APIs no disponibles, formatos inestables, errores de transformación, accesos no disponibles |
| safe_response_pattern | "La carga manual suele automatizarse si el origen y destino están claros. ¿De dónde a dónde necesitás pasar los datos?" |
| notes | Si requiere browser automation, evaluar caso aparte. Si hay datos sensibles, activar human_review_required. |

### J. Integraciones entre sistemas

| Campo | Valor |
|-------|-------|
| automation_case | Sincronización de datos entre CRM, planillas, ecommerce, formularios, ERP y otros sistemas |
| descripción | Automatización de la comunicación entre dos o más sistemas para mantener datos sincronizados. |
| user_intent_examples | "El CRM no se sincroniza con la web", "Quiero que los pedidos de la tienda vayan al sistema", "Necesito integrar el ERP con el CRM" |
| typical_tools | CRM, ERP, ecommerce, plataformas, APIs, planillas, middleware |
| minimum_information_needed | sistemas origen y destino, APIs disponibles, frecuencia, volumen, direccionalidad, permisos |
| technical_feasibility_default | medium |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | APIs inestables o sin documentación, permisos insuficientes, datos críticos, MFA, costos de integración |
| safe_response_pattern | "Las integraciones dependen de las APIs disponibles. ¿Los sistemas que querés conectar tienen API documentada?" |
| notes | Si la integración involucra ERP, finanzas, datos sensibles o plataformas con MFA, activar human_review_required. |

### K. Browser automation

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de tareas en navegador cuando no hay API disponible |
| descripción | Automatización de acciones en interfaces web cuando la plataforma no ofrece API o integración directa. |
| user_intent_examples | "El sistema no tiene API, quiero automatizar la carga", "Necesito que un bot haga esto en la web todos los días" |
| typical_tools | Navegador, sistema web, planillas, datos de entrada |
| minimum_information_needed | plataforma, login, MFA/QR/Face ID/código, términos de uso, frecuencia, acción a automatizar, impacto si falla |
| technical_feasibility_default | medium |
| operational_feasibility_default | low |
| availability_status | feasible_not_packaged |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | special_case_human_review |
| human_review_required_default | true |
| key_risks | MFA, QR, Face ID, códigos de seguridad, cambios de interfaz, bloqueo de cuenta, términos de servicio, anti-bot, datos sensibles |
| safe_response_pattern | "La automatización por navegador es posible pero tiene riesgos. ¿La plataforma tiene API o exportación de datos?" |
| notes | Por defecto requiere human_review_required. No evadir controles nativos ni anti-bot. Si la plataforma pide MFA, QR o Face ID, esa validación debe hacerla el usuario. |

### L. ERP / sistemas administrativos

| Campo | Valor |
|-------|-------|
| automation_case | Automatización o integración parcial con ERP o sistemas administrativos |
| descripción | Automatización de procesos dentro de ERP o integración parcial con otros sistemas. |
| user_intent_examples | "Quiero que el ERP genere reportes automáticos", "Necesito pasar datos del sistema al ERP" |
| typical_tools | ERP (SAP, Odoo, otros), sistemas administrativos, planillas, APIs |
| minimum_information_needed | ERP específico, módulos, APIs, permisos, alcance, criticidad |
| technical_feasibility_default | medium |
| operational_feasibility_default | low |
| availability_status | feasible_not_packaged |
| service_maturity | PAQUETE_FUTURO |
| diagnosis_category | special_case_human_review |
| human_review_required_default | true |
| key_risks | APIs propietarias, permisos críticos, impacto operativo, MFA, datos financieros, costos, cumplimiento |
| safe_response_pattern | "Los ERP suelen requerir revisión técnica antes de prometer automatización. ¿Qué ERP usan y qué proceso específico quieren automatizar?" |
| notes | No prometer ERP amplio como paquete inmediato. Suele requerir revisión técnica y operativa. human_review_required por defecto. |

### M. Finanzas / bancos / pagos / conciliaciones

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de procesos financieros, conciliaciones y reportes bancarios |
| descripción | Automatización de procesos financieros: conciliación, reportes, clasificación de pagos, asistencia en cierres. |
| user_intent_examples | "Hago conciliación bancaria manualmente", "Quiero automatizar el cierre mensual", "Necesito reportes de pagos automáticos" |
| typical_tools | Bancos (web), sistemas contables, ERP, planillas, facturación |
| minimum_information_needed | tipo de operación, si hay dinero real, pagos, decisiones automáticas, controles humanos, regulaciones |
| technical_feasibility_default | medium |
| operational_feasibility_default | low |
| availability_status | future_opportunity |
| service_maturity | PAQUETE_FUTURO |
| diagnosis_category | future_opportunity |
| human_review_required_default | true |
| key_risks | Dinero real, decisiones financieras automáticas, cumplimiento, MFA bancario, QR, tokens, regulación, responsabilidad legal |
| safe_response_pattern | "Los procesos financieros requieren cuidado. Para reportes operativos podemos orientarte. Para conciliaciones o decisiones automáticas, necesitamos revisión del equipo." |
| notes | Reportes financieros simples pueden ser core. Conciliaciones bancarias y automatización financiera sensible: human_review_required y future_opportunity. Pagos, aprobaciones, rechazos, inversiones o decisiones financieras automáticas sin supervisión deben tratarse como not_recommended o blocked. No automatizar MFA, QR, tokens ni aprobaciones bancarias. |

### N. Marketplaces / ecommerce

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de publicaciones, stock, consultas y reportes en marketplaces |
| descripción | Automatización de procesos en plataformas de ecommerce y marketplaces. |
| user_intent_examples | "Quiero que las publicaciones se actualicen solas", "Necesito sincronizar stock entre mi sistema y Mercado Libre" |
| typical_tools | Mercado Libre, Shopify, WooCommerce, sistemas de stock, planillas |
| minimum_information_needed | plataforma, APIs, volumen, permisos, criticidad, términos de la plataforma |
| technical_feasibility_default | medium |
| operational_feasibility_default | medium |
| availability_status | feasible_not_packaged |
| service_maturity | PAQUETE_FUTURO |
| diagnosis_category | feasible_not_packaged |
| human_review_required_default | conditional |
| key_risks | APIs inestables, cambios de políticas, MFA de plataforma, riesgo de cuenta, datos de clientes, cumplimiento |
| safe_response_pattern | "Los marketplaces pueden automatizarse parcialmente. Depende de las APIs y permisos disponibles. ¿Qué plataforma usan?" |
| notes | Marketplaces complejos no deben tratarse como disponibilidad inmediata sin validación. Si hay MFA o credenciales compartidas, activar human_review_required. |

### O. Documentos y extracción de datos

| Campo | Valor |
|-------|-------|
| automation_case | Extracción de datos desde facturas, PDFs, formularios, contratos y remitos |
| descripción | Automatización de lectura y extracción de datos desde documentos digitales o escaneados. |
| user_intent_examples | "Recibo muchas facturas en PDF y las cargo a mano", "Necesito extraer datos de contratos automáticamente" |
| typical_tools | PDFs, facturas, formularios, contratos, sistemas, OCR |
| minimum_information_needed | tipo de documento, volumen, formato, confidencialidad, estructura |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Datos sensibles en documentos, formatos variables, calidad de OCR, documentos legales o financieros |
| safe_response_pattern | "La extracción desde documentos es factible si el formato es estable. ¿Qué tipo de documentos son y están en formato digital?" |
| notes | Si contiene datos personales sensibles, legales o financieros, activar human_review_required. |

### P. Agenda, turnos y recordatorios

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de recordatorios, coordinación de turnos y estados |
| descripción | Automatización de la gestión de turnos, agenda, recordatorios a clientes y estados. |
| user_intent_examples | "Quiero que los clientes reciban recordatorios de turnos", "Necesito automatizar la agenda" |
| typical_tools | Calendarios, WhatsApp, CRM, sistemas de turnos, planillas |
| minimum_information_needed | tipo de turno, canal de comunicación, consentimiento, frecuencia, volumen |
| technical_feasibility_default | high |
| operational_feasibility_default | medium |
| availability_status | available_with_validation |
| service_maturity | PILOTO_VALIDADO |
| diagnosis_category | available_now |
| human_review_required_default | conditional |
| key_risks | Mensajes a clientes, consentimiento, datos personales, privacidad, reputación |
| safe_response_pattern | "Los recordatorios automáticos son factibles si hay consentimiento y el canal está definido. ¿Hoy cómo confirman los turnos?" |
| notes | Si implica mensajes a clientes finales sin consentimiento explícito, activar human_review_required. |

### Q. Procesos legales, compliance o reclamos sensibles

| Campo | Valor |
|-------|-------|
| automation_case | Asistencia o clasificación en procesos legales, compliance o reclamos |
| descripción | Automatización parcial de procesos legales: clasificación de documentos, asistencia en búsqueda, resumen de casos. |
| user_intent_examples | "Necesito clasificar expedientes legales", "Quiero un asistente que busque en nuestros contratos" |
| typical_tools | Documentos legales, sistemas de gestión, bases de datos |
| minimum_information_needed | tipo de proceso, datos, cumplimiento, responsables, decisiones automatizadas |
| technical_feasibility_default | medium |
| operational_feasibility_default | low |
| availability_status | not_available |
| service_maturity | NO_OFRECER_AUN |
| diagnosis_category | special_case_human_review |
| human_review_required_default | true |
| key_risks | Decisiones legales automáticas, cumplimiento, responsabilidad profesional, datos sensibles, privacidad |
| safe_response_pattern | "Los procesos legales requieren cuidado. Podemos asistir en clasificación o búsqueda, pero no automatizar decisiones legales sin revisión especializada." |
| notes | human_review_required por defecto. No automatizar decisiones legales. Solo asistencia o clasificación. |

### R. Trading bot / decisiones automáticas de inversión

| Campo | Valor |
|-------|-------|
| automation_case | Automatización de decisiones de inversión o trading |
| descripción | Automatización de operaciones de compra/venta en mercados financieros basada en reglas o algoritmos. |
| user_intent_examples | "Quiero un bot que opere automáticamente", "Necesito automatizar mis decisiones de trading" |
| typical_tools | Plataformas de trading, APIs financieras, exchanges |
| minimum_information_needed | plataforma, estrategia, capital, regulación aplicable, responsable |
| technical_feasibility_default | low |
| operational_feasibility_default | low |
| availability_status | not_recommended |
| service_maturity | NO_OFRECER_AUN |
| diagnosis_category | not_recommended |
| human_review_required_default | true |
| key_risks | Pérdida financiera, regulación, cumplimiento, responsabilidad legal, alta complejidad |
| safe_response_pattern | "El trading automatizado tiene alto riesgo financiero y regulatorio. No podemos tratarlo como disponibilidad inmediata ni recomendarlo sin revision especializada." |
| notes | Clasificar como future_opportunity o not_recommended según contexto. Alto riesgo financiero. human_review_required siempre. |

---

## Tabla de clasificación rápida

| Caso | technical_feasibility | operational_feasibility | availability_status | service_maturity | diagnosis_category | human_review_required | Nota |
|------|----------------------|------------------------|--------------------|-----------------|-------------------|----------------------|-------|
| A. CRM + leads | high | high | available_now | CORE_VALIDADO | available_now | false | Validar acceso a CRM. |
| B. WhatsApp comercial | high | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | Consentimiento y clientes finales. |
| C. Facebook Ads / Meta | high | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | Permisos de cuenta publicitaria. |
| D. Excel / Sheets | high | high | available_now | CORE_VALIDADO | available_now | false | Datos sensibles elevan riesgo. |
| E. Reportes KPI | high | high | available_now | CORE_VALIDADO | available_now | false | Datos financieros elevan riesgo. |
| F. RAG documentos | high | medium | available_with_validation | CORE_VALIDADO | available_now | conditional | Documentos sensibles elevan riesgo. |
| G. Atención al cliente | high | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | Clientes finales sin supervisión. |
| H. Clasificación tickets | high | medium | available_now | PILOTO_VALIDADO | available_now | false | Acciones automáticas elevan riesgo. |
| I. Carga manual datos | medium | medium | available_with_validation | PILOTO_VALIDADO | available_now | false | Browser automation cambia categoría. |
| J. Integraciones | medium | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | ERP/finanzas elevan riesgo. |
| K. Browser automation | medium | low | feasible_not_packaged | PILOTO_VALIDADO | special_case_human_review | true | No evadir controles nativos. |
| L. ERP | medium | low | feasible_not_packaged | PAQUETE_FUTURO | special_case_human_review | true | Revisión técnica requerida. |
| M. Finanzas/bancos | medium | low | future_opportunity | PAQUETE_FUTURO | future_opportunity | true | MFA bancario no automatizable. |
| N. Marketplaces | medium | medium | feasible_not_packaged | PAQUETE_FUTURO | feasible_not_packaged | conditional | APIs y términos a validar. |
| O. Documentos/extracción | high | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | Documentos sensibles. |
| P. Agenda/turnos | high | medium | available_with_validation | PILOTO_VALIDADO | available_now | conditional | Consentimiento de clientes. |
| Q. Legal/compliance | medium | low | not_available | NO_OFRECER_AUN | special_case_human_review | true | Solo asistencia, no decisiones. |
| R. Trading bot | low | low | not_recommended | NO_OFRECER_AUN | not_recommended | true | Alto riesgo financiero. |

---

## Datos mínimos por familia de casos

### Para CRM / leads

- herramienta actual (CRM específico, planilla, ninguno)
- origen de leads (formulario, WhatsApp, Facebook, web, llamada)
- estados del embudo (nuevo, contactado, calificado, cerrado)
- volumen (leads por día/semana/mes)
- responsable (quién ejecuta el seguimiento)
- canal de seguimiento (WhatsApp, email, llamado)

### Para WhatsApp / mensajería

- tipo de mensajes (consultas, pedidos, reclamos, FAQs)
- consentimiento (opt-in existente, política de privacidad)
- volumen (mensajes por día)
- frecuencia (continuo, por campaña, horarios)
- objetivo (responder, clasificar, recordar, derivar)
- responsable humano (quién recibe las derivaciones)
- plataforma usada (WhatsApp personal, Business, Cloud API)

### Para reportes / KPI

- fuentes de datos (sistemas, planillas, CRM, APIs)
- frecuencia (diario, semanal, mensual, cierre)
- métricas (qué números se reportan)
- formato esperado (dashboard, PDF, Excel, correo)
- responsable (quién arma el reporte hoy)
- destino del reporte (quién lo recibe)

### Para RAG / documentos

- tipo de documentos (políticas, manuales, contratos, FAQs)
- volumen (cantidad de documentos o páginas)
- confidencialidad (público, interno, confidencial, sensible)
- permisos (quién puede acceder a cada documento)
- actualización (frecuencia con que cambian los documentos)
- preguntas esperadas (qué tipo de consultas recibirá el asistente)

### Para browser automation

- plataforma (sitio web específico)
- login (requiere usuario y contraseña)
- MFA / QR / Face ID / código (qué seguridad nativa tiene)
- términos de uso (permite automatización?)
- frecuencia (cada cuánto se ejecuta)
- acción a automatizar (qué se hace en la pantalla)
- impacto si falla (bloqueo, error, pérdida de datos)

### Para finanzas / bancos

- tipo de operación (reporte, conciliación, pago, decisión)
- si hay dinero real (transacciones, pagos, inversiones)
- si hay pagos (montos, destinatarios, frecuencia)
- si hay decisiones automáticas (aprobar, rechazar, invertir)
- controles humanos (quién aprueba cada paso)
- regulaciones o responsabilidades (cumplimiento aplicable)

---

## Patrones de respuesta por familia

### CRM / leads

> Por lo que contás, esto es un caso de automatización comercial.
> Si el CRM y los canales de entrada están claros, es factible.
> Para orientarte mejor: ¿qué CRM usan y de dónde vienen los leads?

### WhatsApp comercial

> WhatsApp comercial puede automatizarse parcialmente. Primero
> necesito saber si usás WhatsApp Business y qué tipo de consultas
> recibís. Esto requiere validar consentimiento y alcance.

### Reportes KPI

> Los reportes periódicos suelen ser un buen caso si las fuentes de
> datos están claras. ¿De dónde salen los números hoy y cada cuánto
> necesitás el reporte?

### RAG documentos

> Un asistente sobre documentos propios es factible si los documentos
> son digitales y hay permisos definidos. ¿Qué tipo de documentos son
> y quién debería poder consultarlos?

### Browser automation

> La automatización por navegador es posible pero tiene riesgos:
> si la plataforma tiene login, MFA o validaciones de seguridad, no
> podemos automatizarlas. ¿La plataforma tiene API o exportación de
> datos? Si no, esto requiere revisión del equipo.

### Finanzas / bancos

> Los procesos financieros requieren cuidado especial. Para reportes
> operativos podemos orientarte. Para conciliaciones bancarias o
> decisiones automáticas, necesitamos revisión del equipo antes de
> recomendar algo. Si implica pagos, inversiones o aprobaciones sin
> supervisión humana, no sería responsable automatizarlo.

### Caso no listado

> Este caso no aparece como disponibilidad inmediata en el catálogo
> actual, pero eso no significa que no pueda diagnosticarse. Con lo
> que contás, primero revisaría factibilidad técnica, datos
> disponibles, permisos y riesgo operativo. Si vemos que es viable,
> puede tratarse como solución a evaluar o caso particular para
> revisar con el equipo.

---

## Casos no listados

Si el usuario trae un caso no incluido en el catálogo, Vera no debe
cerrar con "no tenemos ese servicio" ni "no está en nuestro catálogo".

Debe responder:

1. Analizando factibilidad técnica y operativa con la información
   disponible.
2. Identificando datos faltantes.
3. Clasificando disponibilidad según la matriz de factibilidad.
4. Marcando si es factible no empaquetado, requiere más información,
   caso particular o futuro.

### Respuesta modelo

> Este caso no aparece como disponibilidad inmediata en el catálogo
> actual, pero eso no significa que no pueda diagnosticarse. Con lo
> que contás, primero revisaría factibilidad técnica, datos
> disponibles, permisos y riesgo operativo. Si vemos que es viable,
> puede tratarse como solución a evaluar o caso particular para
> revisar con el equipo.

### Regla

La ausencia del caso en el catálogo no autoriza a:

- Prometer que Team360 lo implementará.
- Pedir datos personales para "evaluar el caso".
- Ofrecerlo como si estuviera disponible sin validación.
- Derivar automáticamente a contacto sin dar valor diagnóstico.

---

## Referencias cruzadas

Este catálogo se apoya en los siguientes documentos del paquete
`pkg_sales_diagnosis`:

- [[team360_sales_diagnosis_package_manual]]: define alcance,
  oferta, madurez y reglas de conversación del asistente.
- [[team360_sales_diagnosis_slots_questions]]: define slots y
  preguntas dinámicas. Los datos mínimos por familia de casos
  se corresponden con slots definidos allí.
- [[team360_sales_diagnosis_feasibility_availability_matrix]]:
  matriz de factibilidad técnica, operativa y disponibilidad
  comercial. Los valores de clasificación rápida usan esta matriz.
- [[team360_sales_diagnosis_response_playbook]]: patrones de
  respuesta por categoría de diagnóstico. Los patrones por familia
  complementan el playbook general.
- [[team360_sales_diagnosis_security_hitl_policy]]: política de
  seguridad. Los riesgos listados en cada caso y las reglas de
  browser automation, scraping y finanzas siguen esta política.

---

## Límites

- **Este catálogo no es una lista cerrada de servicios.** Vera
  puede y debe diagnosticar casos no listados.
- **No convierte todos los casos en oferta activa.** Un caso puede
  ser diagnosticable y no estar disponible como paquete.
- **No reemplaza la matriz de factibilidad.** Los valores por
  defecto son orientativos; el diagnóstico final debe usar la
  matriz.
- **No reemplaza la política de seguridad / HITL.** Los riesgos
  listados son indicativos; la política de seguridad tiene
  prioridad.
- **No autoriza pedir credenciales.** Bajo ninguna circunstancia.
- **No autoriza evadir seguridad nativa.** No sugerir formas de
  saltar MFA, QR, Face ID, códigos o controles anti-bot.
- **No habilita Step-to-Action.** Step-to-Action, lead capture,
  diagnostic_code y WhatsApp handoff son capacidades futuras.
- **No habilita lead capture.** No capturar datos personales
  como parte del flujo normal de diagnóstico.
- **No habilita diagnostic_code.** El código de diagnóstico
  pertenece a una capa futura de continuidad comercial.
- **No habilita WhatsApp handoff.** La derivación por WhatsApp
  es una extensión planificada.
- **No define precios, tiempos ni alcance contractual.** El
  catálogo es una guía de diagnóstico, no una propuesta comercial.
- **No debe usarse para prometer implementación.** Diagnosticar
  factibilidad no es comprometer delivery.

---

## Historial de cambios

| Fecha | Cambio | Autor |
|------|--------|-------|
| 2026-06-14 | Creación draft inicial para producción por etapas. | Team360 |
