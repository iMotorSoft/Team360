# Team360 Platform

Team360 is an AI Workflow Layer over real company operations. It must not be positioned as a generic chatbot, WhatsApp bot or uncontrolled automation agent.

## Product Thesis

Team360 should be the platform for:

- tenants and workspaces;
- assistant instances;
- contracted automation packages;
- worker governance;
- permissions;
- audit trails;
- operational workflows;
- ERP and administrative processes;
- knowledge scopes;
- events and telemetry;
- customer-facing experiences.

## Control Plane

Team360 is the control plane and source of truth.

External tools, browser automation, desktop automation, LangGraph, LiteLLM, RAG and workers are subordinate execution or interpretation layers.

Rule:

```text
Team360 decides.
Workers execute.
AI interprets.
Postgres records truth.
AG-UI/SSE shows state.
```

## WhatsApp transport boundary

Evolution transporta WhatsApp; Team360 posee la conversación, el routing, la autorización y la auditoría. Un transporte DEV validado no implica que su adaptador Team360 esté implementado.

El laboratorio usa WhatsApp Cloud API oficial con activos Meta propios de Team360. `backend/globalVar.py` resuelve su bloque Meta exclusivamente desde `META_TEAM360_*`, sin fallback a Vertice360 ni credenciales históricas iMotorSoft.

Se conservan los nombres públicos `TEAM360_META_*` y el default no secreto Graph `v20.0`. Sin token, phone number ID o verify token Team360, `team360_meta_whatsapp_enabled()` retorna falso aunque exista configuración de otro proyecto. Evolution y su PostgreSQL técnico no sustituyen la autoridad conversacional de Team360.

El adapter de respuesta fija reutiliza `InboundMessage`, `OutboundMessageReceipt` y `WhatsAppMessageSenderPort`, con conversación en `message_threads`/`message_events`, no en Flow. Su alta y esquema respetan [[team360-global-orchestration#Team360 — Orquestación global#Modelo de ownership modular#GLOBAL]].

La latencia Team360 sin LLM se mide desde recepción del webhook hasta inicio del port y hasta callback delivered, separada de la línea base Evolution. El scope son los pings exactos: otros textos se conservan y reportan aparte, sin ocultar intentos válidos duplicados/desordenados ni replies indebidos.

El cierre exige cruzar los IDs con el transporte y verificar replays y recuperación contra datos persistidos, no inferir éxito desde el contador de una sonda. Se conserva cualquier evidencia original incorrecta para explicar la corrección. No introducir Redis, brokers ni otro framework sin evidencia.

Fuente técnica existente: [Messaging README](../SrvRestAstroLS_v1/backend/modules/messaging/README.md); estado, límites y enlaces a evidencia en el [único status técnico GLOBAL](../SrvRestAstroLS_v1/docs/status_actual.md). LAT no certifica disponibilidad operacional ni acumula resultados diarios.

### Fixed response conversation ownership

Team360 confirma el inbound y un intent antes de enviar por el port; el transporte no decide conversación ni routing. La autorización de un número es exclusivamente una allowlist DEV, no un permiso de negocio.

Scope persistido por provider/instancia/canal e índices únicos aseguran una conversación por identidad y un intento de respuesta por inbound. Los estados received/sent/delivered/read/failed/unknown son ortogonales a los estados operacionales core.

Callback y aceptación comparten lock transaccional; los estados tempranos se reconcilian después de conocer el ID externo. Delivery/read no retroceden por callbacks tardíos. Los payloads Evolution y secretos terminan en el borde; el core recibe contratos internos.

Ante timeout o corte, no se reintenta automáticamente un intent. Puede quedar sin respuesta o con resultado incierto; la POC preserva la conversación y evita duplicar despachos, pero no promete exactly-once delivery ni recuperación automática.

### Adapter unit specifications

Las pruebas verifican texto, identidad, IDs, filtros, delivery, errores saneados, configuración DEV, autorización e idempotencia sin depender de WhatsApp ni secretos reales.

Se exige transformación exacta de los veinte pings, protección HTTP y ausencia de payload proveedor en el service. El reporte omite métricas ausentes y usa percentiles interpolados, sin inferir tráfico real desde fixtures.

### Adapter local integration specifications

Las pruebas usan PostgreSQL Team360 y HTTP loopback reales para demostrar persistencia, unicidad concurrente y gestión de fallos sin enviar mensajes WhatsApp ni reiniciar infraestructura compartida.

Repetir inbound produce una sola fila y una sola llamada de salida. Sender no autorizado no persiste ni responde. Error, timeout, respuesta inválida y conexión rechazada conservan evidencia sin reintento; reconstruir app/pool conserva la conversación y los intents.

Se verifican status tempranos, duplicados y fuera de orden. Estos tests no reemplazan los veinte intercambios humanos, el delivery Meta ni los reinicios reales exigidos por el gate.

### Benchmark traffic isolation tests

El benchmark cuenta solo los veinte comandos exactos que enrutan a respuesta fija. Los textos fuera de ese contrato se conservan y reportan aparte, sin ocultar pings válidos repetidos, desordenados ni respuestas indebidas.

Se verifica que 20 pares y 3 textos no enrutados producen 20 muestras y 3 registros extra auditables, no una violación artificial 23/20. Un segundo ID para un ping válido, secuencia inválida o reply a texto no enrutado sigue bloqueando completitud.

Las métricas primarias T0→T4 y T0→T6 necesitan veinte muestras completas; falta de T6 en el último par invalida completitud aunque exista read, sin inventar un delivered timestamp.

### Replay candidate tests

La prueba de duplicado selecciona un inbound con respuesta aceptada, no un saludo anterior sin outbound. Esto demuestra idempotencia de la respuesta, además de idempotencia del registro inbound.

Sin candidato aceptado, la sonda espera y no marca una prueba fallida ni provoca un nuevo envío. El verificador de cierre cruza IDs con Evolution y repite los IDs existentes tras reiniciar solo su backend.

### Messaging-only DEV bootstrap

El perfil explícito `TEAM360_DEV_PROFILE=messaging-only` monta las rutas Messaging existentes y health PostgreSQL, sin importar registry, Flow, Telchi, Vera ni módulos AI. El modo normal sigue siendo default y conserva sus preflights.

El bootstrap valida configuración DEV, PostgreSQL Team360, binding e índices de la migración 026. Abrir pool sucede solo en startup; Evolution se verifica al activar tráfico real, no como dependencia del arranque HTTP. Producción y puertos ocupados se rechazan.

### Messaging-only DEV bootstrap tests

Los tests comprueban los checks normales con sockets realmente cerrados, importación y startup aislados, y arranque del launcher con PostgreSQL real mientras Milvus/LiteLLM no están disponibles en los endpoints de prueba.

Health y webhook HTTP deben funcionar y persistir un inbound idempotente. No hay conexiones fake ni health falsificado; módulos ajenos no aparecen en `sys.modules`, y los procesos de prueba se cierran por su PID propio.

## Business Positioning

Preferred positioning:

```text
Operational intelligence and automation layer over ERP, administrative processes and real business channels.
```

Avoid positioning as:

- chatbot;
- generic bot;
- tool that bypasses security;
- fully autonomous agent for sensitive operations;
- SAP-certified solution unless that certification exists.

## Priority Verticals

Initial and premium verticals include:

- SAP Business One / ERP AI Layer;
- administrative workflows;
- document reconciliation;
- marketplace operations;
- revenue operations;
- support and knowledge assistants;
- automation diagnosis.
