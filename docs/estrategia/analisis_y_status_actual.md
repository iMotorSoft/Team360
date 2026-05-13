# Analisis y status actual

Proyecto: Team360
Cliente piloto: JudaismoEnVivo / judaismoenvivo.com
Estado: documento de continuidad para retomar trabajo.

## Contexto leido

Documentos revisados:

- `docs/estrategia/informe_estrategia_tecnica_negocio_openclaw_2026-05-06.md`
- `docs/negocio/contexto_negocio_team360_erp_ai_layer_2026-05-06.md`

Tesis consolidada:

- Team360 debe ser la plataforma, fuente de verdad, permisos, auditoria, workflows y producto.
- OpenClaw, Playwright u otros ejecutores deben actuar como workers acotados, no como orquestador principal.
- LangGraph es una buena eleccion para runtime de workflows agentic/HITL, pero Team360 debe conservar el control plane.
- Postgres debe guardar jobs, eventos, auditoria, versiones, configuracion por tenant y snapshots de ejecucion.
- AG-UI/SSE debe ser la capa visible de timeline y estados en vivo.

## Decision fria sobre agentes

Arquitectura recomendada:

```text
Team360 Orquestador = control plane / fuente de verdad
LangGraph = runtime de workflows agentic, pausables y con HITL
Workers = OpenClaw, Playwright, OCR, APIs, conectores externos
Postgres = estado contractual, auditoria, versiones y snapshots
AG-UI/SSE = timeline visible
```

Regla:

```text
Team360 decide.
LangGraph ejecuta workflows.
Workers realizan tareas acotadas.
Postgres registra la verdad.
```

No poner en LangGraph:

- permisos del tenant;
- facturacion;
- auditoria legal;
- allowlist de tools;
- contratos de integracion;
- historial oficial de jobs;
- versiones activas por cliente.

## Versionado por cliente

No usar branches por cliente.

Modelo recomendado: artefactos inmutables versionados y asignacion por tenant.

Artefactos a versionar:

- `workflow_template_version`
- `agent_profile_version`
- `tool_contract_version`
- `connector_version`
- `prompt_version`
- `policy_version`
- `knowledge_base_version`
- `ui_capability_version`

Cada `Job` debe guardar snapshot de versiones para reconstruir exactamente que corrio:

```json
{
  "tenant_id": "judaismoenvivo",
  "workflow_id": "jev_inbound_sales",
  "workflow_version": "1.0.0",
  "agent_profile_version": "1.0.0",
  "policy_version": "1.0.0",
  "knowledge_base_version": "jev_kb_2026_05",
  "tools": {
    "whatsapp_send_message": "1.0.0",
    "lead_upsert": "1.0.0",
    "offer_recommend": "1.0.0"
  }
}
```

## Politica MFA/RPA incorporada

Team360 no debe prometer bypass de seguridad.

Carriles:

- `HITL_CODE_INJECTION`: SMS OTP, email OTP, TOTP, backup codes, token numerico leido por humano.
- `REMOTE_MIRRORING`: QR, push approval, aprobacion en app movil.
- `HARDWARE_PROXIMITY`: FIDO2/YubiKey, FaceID/TouchID obligatorio, smart card USB, certificados no exportables.

Estados base:

```text
RUNNING
WAITING_FOR_MFA
WAITING_FOR_HUMAN_APPROVAL
WAITING_FOR_HARDWARE_ACTION
BLOCKED_BY_POLICY
COMPLETED
FAILED
```

Frase comercial recomendada:

> Automatizamos procesos administrativos incluso cuando hay MFA, con intervencion humana controlada cuando el sistema lo exige. Donde hay firma fuerte, hardware fisico o biometria obligatoria, el agente prepara la operacion y el humano autoriza.

## Cliente piloto: JudaismoEnVivo

Oportunidad:

Convertir audiencia social en trafico propio, contactos, ventas e inscripciones para que judaismoenvivo.com sea sostenible.

Embudo objetivo:

```text
Reel viral
-> visita
-> WhatsApp/email
-> propuesta
-> inscripcion/venta
-> onboarding
-> seguimiento
```

Decision fria:

Para este cliente no empezar por ERP/SAP. Empezar con un modulo tipo `Revenue Ops Agent` para audiencia, mensajeria, contenidos, soporte, pagos y seguimiento.

## Informacion publica observada

Facebook:

- URL revisada: `https://www.facebook.com/judaismoenvivo`
- Nombre visible: `judaismoenvivo.com`
- Dato visible: `165K followers`
- Facebook limita contenido publico con modal/login; sin acceso a Meta Business no se puede obtener ranking real de reels, comentarios, clicks ni mensajes.

Web:

- URL: `https://judaismoenvivo.com/`
- Marca: `Judaismoenvivo AI / JAI`
- Referente: Rabino Natan Menashe
- Producto central: `MORIA`, tutor de IA 24/7 para Torah y sabiduria judia.
- Promesa: cursos interactivos, biblioteca, recursos, comunidad MORIA y encuentros en vivo.
- La web muestra comunidad en Facebook de `94K` y YouTube de `44K`. Esto difiere del dato visible en Facebook de `165K followers`; revisar si la web esta desactualizada o si mide otra cosa.

Linktree:

- URL: `https://linktr.ee/judaismoenvivo.com`
- Perfil: `@judaismoenvivo`
- Descripcion: `Rab Natan Menashe`
- Links visibles: Facebook, Instagram, YouTube, WhatsApp, Email, Payment, Telegram.
- Tambien hay links a `Rab. Natan Grupo 1` hasta `Rab. Natan Grupo 5`.

## Productos monetizables detectados

### Vida judIA

URL:

- `https://judaismoenvivo.com/landing/sp/cursos/general-vida_judia_a1_ins/`

Oferta:

- Curso de 6 meses.
- Tutor MORIA 24/7.
- Evaluaciones flexibles.
- Clase magistral en vivo por fase aprobada.
- Certificado final.

Precios:

- Plan mensual: USD 22/mes.
- Plan trimestral: USD 60/trimestre.
- Plan semestral: USD 108/semestre.

### Matrimonio Judio

URL:

- `https://judaismoenvivo.com/landing/sp/cursos/general-matrimonio_judio_a1_ins/`

Oferta:

- Curso de 4 semanas.
- Sesiones en vivo.
- Material exclusivo.
- Soporte por WhatsApp.
- Certificado.

Precios:

- Plan individual: USD 39.
- Plan pareja: USD 62.

### Mistica Judia: Universo Interior

URL:

- `https://judaismoenvivo.com/landing/sp/cursos/general-mistica_judia_universo_interior_a1_ins/`

Oferta:

- Curso de 12 semanas.
- Tres fases: Despertar, Exploracion, Microcosmos.
- Tutor MORIA 24/7.
- Enfoque Aryeh Kaplan.

Precios:

- Plan mensual: USD 22/mes.
- Plan trimestral: USD 49/trimestre.

### Cruzando el Puente Angosto

URL:

- `https://judaismoenvivo.com/landing/sp/libros/breslov-cruzando_el_puente_a1_presentacion/`

Oferta:

- Libro/experiencia educativa sobre Rebe Najman y Breslov.
- Acceso anonimo o acceso completo.
- MORIA como tutor de estudio.

## Lectura comercial

El problema no parece ser falta de producto.

Ya existen:

- audiencia grande;
- contenido viral;
- marca personal religiosa;
- cursos pagos accesibles;
- tutor IA diferenciador;
- WhatsApp;
- pagos;
- comunidad;
- activos en Facebook, Instagram, YouTube, Telegram y email.

El problema probable es conversion, seguimiento y medicion:

- llevar views a contacto propio;
- identificar intencion real;
- recomendar oferta concreta;
- cerrar pago/inscripcion;
- hacer onboarding;
- recuperar interesados tibios;
- medir ingresos por contenido/campana.

## Workflows iniciales recomendados

Pack de workflows para tenant `judaismoenvivo`:

```text
jev_campaign_signal_v1
Detecta reels/contenidos con traccion y propone campana/CTA.

jev_lead_capture_whatsapp_v1
Recibe interesados desde WhatsApp/Messenger y los etiqueta.

jev_offer_router_v1
Deriva segun intencion: Vida Judia, Matrimonio, Mistica, Libro, Comunidad o Soporte.

jev_inbound_sales_v1
Atiende, califica, recomienda oferta, responde objeciones simples y deriva a humano si corresponde.

jev_support_faq_v1
Responde dudas frecuentes sobre cursos, acceso, pagos, MORIA, comunidad y proximos pasos.

jev_followup_7d_v1
Recupera interesados que no compraron o no terminaron inscripcion.

jev_content_repurpose_v1
Convierte reels ganadores en email, articulo, clase corta, post y secuencia comercial.
```

## MVP 60 a 90 dias

Prioridad: convertir audiencia actual en ingresos, no construir tecnologia amplia.

### Semana 1-2

- Crear base de contactos/leads.
- Definir ofertas activas y CTAs.
- Conectar WhatsApp/Messenger intake.
- Cargar 20 a 40 FAQs.
- Crear tags de intencion.
- Crear landing o rutas de CTA por producto.

### Semana 3-4

- Activar workflow de ventas.
- Activar derivacion humana.
- Registrar estados de lead.
- Activar seguimiento automatico basico.
- Medir conversaciones, leads calificados y pagos.

### Semana 5-8

- Automatizar conversion de reels a emails/articulos/clases cortas.
- Crear campanas por reel ganador.
- Crear reportes simples.
- Revisar mensajes, objeciones y abandono.

### Semana 9-12

- Optimizar segmentos.
- Automatizar campanas recurrentes.
- Mejorar KB de soporte.
- Cruzar ingresos por producto/campana.
- Preparar version repetible para otros clientes de contenidos/comunidad.

## Datos necesarios para analisis completo

Solicitar acceso o export de:

- Meta Business Suite / Insights ultimos 90 dias.
- Top 50 reels por views, retencion, comentarios, compartidos y clicks.
- Comentarios y mensajes entrantes.
- Clicks de Linktree.
- Conversiones/pagos por producto.
- Lista de preguntas frecuentes de WhatsApp.
- Productos/ofertas activas y prioridad comercial.
- Pasarela de pago usada.
- Estado actual de CRM/listas/email.

## Backlog tecnico inmediato

1. Definir modelo minimo:
   - `tenants`
   - `contacts`
   - `lead_events`
   - `campaigns`
   - `offers`
   - `conversations`
   - `jobs`
   - `job_events`
   - `audit_log`

2. Definir estados de lead:
   - `NEW`
   - `ENGAGED`
   - `QUALIFIED`
   - `OFFER_SENT`
   - `PAYMENT_PENDING`
   - `ENROLLED`
   - `NEEDS_HUMAN`
   - `LOST`

3. Definir intenciones iniciales:
   - `curso_vida_judia`
   - `curso_matrimonio`
   - `curso_mistica`
   - `libro_breslov`
   - `comunidad`
   - `soporte_pago`
   - `soporte_acceso`
   - `consulta_religiosa_sensible`
   - `donacion`
   - `otro`

4. Definir politicas:
   - No dar dictamen religioso delicado sin humano.
   - No prometer conversion, estatus religioso ni decisiones halajicas.
   - Escalar preguntas sensibles al Rabino/equipo.
   - Registrar consentimiento y origen del contacto.
   - Respetar opt-in/opt-out en WhatsApp/email.

5. Definir primer graph:
   - `jev_lead_capture_whatsapp_v1`
   - entrada: mensaje/contacto/origen/campana
   - salida: lead actualizado, intencion, oferta sugerida, respuesta, evento de auditoria

## Proxima accion recomendada

Retomar por una de estas dos rutas:

1. Si hay que construir: implementar el esqueleto de tenant `judaismoenvivo` en Team360 con modelos minimos, versionado y primer workflow de captura/calificacion.
2. Si hay que planificar venta: armar propuesta comercial de 60-90 dias para JudaismoEnVivo, con entregables, metricas, accesos requeridos y precio piloto.
