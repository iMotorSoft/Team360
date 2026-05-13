# Informe: estrategia tecnica y negocio con OpenClaw

Fecha: 2026-05-06
Proyecto destino: Team360
Tesis de negocio: ERP AI Workflow Layer para pymes y empresas medianas, con SAP Business One como vertical premium.

## Resumen ejecutivo

La sugerencia tecnica es correcta en direccion general: Team360 no necesita comprar una plataforma externa completa. Ya existe una base propia fuerte en los proyectos revisados:

- `Vertice360`: SSE/AG-UI, broadcaster, workflows, mensajeria Meta/Gupshup, CRM demo y LangGraph.
- `concilia`: wizard, conciliacion, uploads, ingesta, SSE por `run_id`, acciones y fallback en memoria.
- `SolFXHub`: laboratorio AG-UI/SSE con patrones por oleadas.
- `SpendIQ`: OCR, document AI, audio, Telegram/webhooks.
- `JudaismoenVivo`: auth, roles, pagos, producto educativo, RAG/Milvus/Arango.
- `Team360`: repo destino, estructura modular, Mercado Libre browser lab y foco multicanal.

La conclusion recomendada:

> Team360 debe ser el cerebro de negocio, control, auditoria y producto. OpenClaw puede ser un worker de ejecucion sandboxeado y reemplazable, no el orquestador principal ni la fuente de verdad.

Esto preserva el valor defendible del negocio: procesos administrativos, ERP, datos, seguridad, workflows auditables y verticalizacion.

## Decision recomendada

Usar OpenClaw, pero subordinado a Team360.

Arquitectura objetivo:

| Capa | Responsabilidad | Tecnologia sugerida |
|---|---|---|
| Producto / plataforma | Tenants, usuarios, permisos, pricing, auditoria, UI, historial | Team360 |
| Orquestacion de negocio | Workflows deterministas, aprobaciones, estados, SLA | Team360 + LangGraph |
| Ejecucion de tareas | Browser automation, herramientas acotadas, OCR, llamadas operativas | OpenClaw worker |
| Streaming visible | Timeline de acciones, estados en vivo, eventos al frontend | AG-UI/SSE |
| Canales | WhatsApp, portal, webhooks, Mercado Libre, email futuro | Gupshup/Meta/Meli adapters |
| Datos operativos | ERP, SAP B1, DB comun, documentos, conciliacion | Conectores + Postgres |
| Inteligencia | Clasificacion, extraccion, anomalias, recomendaciones | OpenAI/LangGraph/Data Science |

## Correccion tecnica sobre OpenClaw

La sugerencia dice "envolver scripts como OpenClaw Skills". El concepto es bueno, pero conviene precisarlo:

- En OpenClaw, las acciones reales son **tools**: funciones tipadas que el agente puede invocar.
- Las **skills** son archivos `SKILL.md` que enseñan al agente cuando y como usar esas tools.
- Los **plugins** empaquetan tools, skills, providers, canales y otras capacidades.

Por lo tanto, la implementacion correcta no es solo crear skills. Es:

1. Crear tools/plugins OpenClaw para acciones concretas.
2. Agregar skills `SKILL.md` con reglas, precondiciones, limites y ejemplos.
3. Hacer que Team360 habilite solo las tools permitidas para cada tenant, rol y caso de uso.

Fuentes:

- OpenClaw Tools and plugins: `https://docs.openclaw.ai/tools`
- OpenClaw Skills: `https://docs.openclaw.ai/skills`
- OpenClaw CLI skills: `https://docs.openclaw.ai/cli/skills`

## Principio rector

OpenClaw debe ejecutar, no gobernar.

Team360 debe decidir:

- quien puede hacer que;
- sobre que datos;
- con que aprobaciones;
- con que limites;
- que queda auditado;
- que evento se emite;
- que resultado se persiste;
- que accion requiere humano.

OpenClaw debe recibir tareas acotadas:

- leer una pantalla;
- descargar un archivo;
- ejecutar OCR;
- navegar una UI externa;
- llamar una API;
- devolver JSON validado;
- reportar progreso.

## Ensamble de piezas actuales

### 1. Cerebro: de Vertice360 a Team360

Piezas a portar:

- `Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/broadcaster.py`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/routes.py`
- `Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/sse.js`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_orquestador_demo/`

Uso en Team360:

- timeline en vivo del agente;
- estados de jobs;
- workflow auditable;
- dashboard operativo;
- eventos para portal interno y soporte.

Consideracion:

El broadcaster en memoria sirve para fase piloto. Para producto multi-tenant o multi-instancia, migrar a Redis, Postgres LISTEN/NOTIFY, NATS o equivalente.

### 2. Musculo: OpenClaw + Mercado Libre browser lab

Piezas actuales:

- `Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/actions.py`
- `browser/context.py`
- `browser/session_store.py`
- `browser/pages.py`
- `browser/selectors.py`
- `probes/smoke_login.py`
- `probes/smoke_inbox.py`
- `probes/smoke_reply_draft.py`
- `probes/smoke_questions_*`

Como integrarlo:

- Convertir acciones estables en tools:
  - `meli_check_login`
  - `meli_list_questions`
  - `meli_read_thread`
  - `meli_prepare_reply_draft`
  - `meli_save_screenshot`
- Agregar skill `mercadolibre_seller_ops` que indique:
  - no enviar respuestas sin aprobacion;
  - no tocar settings;
  - guardar screenshot;
  - devolver JSON estructurado;
  - cortar si detecta login inseguro;
  - reportar selector fallido.

Beneficio:

- Se aprovecha el browser lab ya escrito.
- OpenClaw puede operar como ejecutor aislado.
- Team360 conserva control, permisos y auditoria.

Riesgo:

No dejar que el agente "improvise" acciones de alto impacto en Mercado Libre. Para negocio real, primero leer, clasificar, redactar borrador y pedir aprobacion.

### 3. Ingreso de datos: concilia + SpendIQ

Piezas actuales:

- `SpendIQ/SrvRestAstro_v2/mistral_v1.py`
- `SpendIQ/SrvRestAstro_v2/routers/analytics.py`
- `concilia/SrvRestAstroLS_v1/routes/v1/uploads_v2_concilia.py`
- `concilia/SrvRestAstroLS_v1/routes/v1/ingest_confirm.py`
- `concilia/SrvRestAstroLS_v1/services/ingest/`
- `concilia/SrvRestAstroLS_v1/services/reconcile/`
- `concilia/SrvRestAstroLS_v1/routes/v1/reconcile_*`

Skill/tool propuesta:

- Tool: `document_extract_ocr`
- Tool: `document_normalize_invoice`
- Tool: `bank_statement_ingest`
- Tool: `reconcile_preview`
- Skill: `procesar_documento_pyme`

Flujo recomendado:

1. Cliente envia PDF, Excel o imagen por WhatsApp/portal.
2. Team360 registra documento y tenant.
3. Team360 decide workflow por tipo documental.
4. OpenClaw ejecuta OCR/extraccion como worker.
5. Team360 valida schema y confianza.
6. Si es extracto/factura, alimenta pipeline de conciliacion.
7. Si hay baja confianza, pide revision humana.
8. Emite eventos SSE en cada paso.

No recomendado:

- Que el agente lea un PDF y decida libremente impactos contables.
- Que escriba directo en ERP sin validacion y auditoria.

### 4. Usuarios, roles y permisos

Piezas a reutilizar:

- JudaismoenVivo para referencia de auth/usuarios/roles.
- Team360 con Postgres/psycopg para modelo nuevo multi-tenant.

Modelo recomendado:

- `tenants`
- `users`
- `roles`
- `permissions`
- `channels`
- `provider_accounts`
- `workflows`
- `tools_allowed`
- `jobs`
- `job_events`
- `documents`
- `audit_log`

Flujo de permisos:

1. Entra webhook Gupshup/Meta/Meli/portal.
2. Team360 identifica tenant y usuario.
3. Team360 carga rol y permisos.
4. Team360 crea job.
5. Team360 instancia worker OpenClaw con allowlist de tools.
6. OpenClaw ejecuta solo lo permitido.
7. Team360 persiste resultados y auditoria.

Ejemplos:

- Vendedor: consulta stock, crea borrador de respuesta, no concilia banco.
- Administracion: procesa facturas, extractos, conciliacion, no cambia precios.
- Gerencia: consulta indicadores, aprueba acciones, recibe alertas.
- Produccion: consulta insumos, recetas, faltantes y ordenes.

## Donde entra SAP Business One

SAP B1 no debe tratarse como una integracion mas. Debe ser el ancla premium del producto.

Team360 ERP AI Layer debe ofrecer:

- lectura segura de datos SAP B1;
- modelo operativo comun;
- consultas conversacionales;
- alertas;
- workflows;
- conciliacion documental;
- data science administrativo;
- auditoria;
- permisos por rol.

OpenClaw no deberia conectarse libremente a SAP B1. Deberia llamar tools controladas por Team360, por ejemplo:

- `sapb1_query_customer_debt`
- `sapb1_query_stock`
- `sapb1_get_purchase_orders`
- `sapb1_compare_invoice_to_po`
- `sapb1_get_margin_variation`
- `sapb1_create_draft_activity`

Regla:

Lectura primero. Escritura solo con aprobacion, idempotencia y log de auditoria.

## Casos de uso priorizados

### Piloto 1: Mercado Libre operational inbox

Objetivo:

- demostrar worker OpenClaw + browser lab + SSE + auditoria.

Flujo:

1. Team360 crea job "leer preguntas Mercado Libre".
2. OpenClaw ejecuta tool sobre Playwright existente.
3. Devuelve preguntas estructuradas.
4. Team360 clasifica intencion.
5. Genera borrador de respuesta.
6. Usuario aprueba.
7. Team360 guarda evento y muestra timeline.

Valor:

- bajo riesgo;
- no requiere SAP B1 inicial;
- muestra automatizacion visible;
- valida permisos y workers.

### Piloto 2: documento pyme a conciliacion

Objetivo:

- conectar SpendIQ + concilia + Team360.

Flujo:

1. PDF/extracto por WhatsApp o portal.
2. OCR/extraccion.
3. Normalizacion a schema.
4. Ingesta.
5. Preview de conciliacion.
6. Aprobacion humana.
7. Resultado auditado.

Valor:

- muy alineado con procesos administrativos reales;
- abre venta a finanzas/administracion;
- prepara SAP B1.

### Piloto 3: SAP B1 read-only assistant

Objetivo:

- validar el vertical premium sin riesgo de escritura.

Casos:

- deuda vencida;
- stock bajo;
- proveedores con variacion de precio;
- margen erosionado;
- facturas pendientes;
- pedidos demorados.

Valor:

- conecta directo con ticket mas alto;
- muestra ROI claro;
- habilita partners ERP.

## Consideraciones de negocio

La sugerencia tecnica sirve al negocio si evita convertir Team360 en un "chatbot con tools".

El producto vendible es:

> Capa de inteligencia operativa sobre ERP y procesos administrativos.

OpenClaw ayuda a acelerar ejecucion, pero no es el diferencial comercial. El diferencial es:

- conectores ERP;
- conocimiento funcional;
- workflows por area;
- auditoria;
- reportes;
- alertas;
- data science;
- plantillas verticales;
- integracion con WhatsApp y portal;
- soporte y onboarding.

## Packaging recomendado

### Team360 Ops Starter

Para pymes sin SAP B1 o con procesos mixtos.

Incluye:

- WhatsApp operativo;
- documentos;
- conciliacion simple;
- alertas basicas;
- portal minimo;
- 1 o 2 workflows.

Objetivo:

- caja inicial;
- aprender operaciones;
- casos de exito.

### Team360 ERP AI Layer for SAP B1

Paquete premium.

Incluye:

- conector SAP B1 read-only inicial;
- consultas conversacionales;
- alertas;
- workflow administrativo;
- centro documental;
- auditoria;
- permisos por rol.

Objetivo:

- ticket alto;
- venta via partners;
- posicionamiento defendible.

### Team360 Data Science Operations

Paquete avanzado.

Incluye:

- anomalias;
- margenes;
- costos;
- stock;
- compras;
- proveedores;
- produccion;
- predicciones y recomendaciones.

Objetivo:

- clientes medianos;
- expansion mensual;
- diferenciacion regional.

## Riesgos tecnicos

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| OpenClaw toma demasiado control | Riesgo operativo y de seguridad | Team360 como gatekeeper, tools acotadas |
| Skills de terceros inseguras | Robo de datos/credenciales | No usar skills externas sin auditoria, allowlist estricta |
| Memoria del agente como verdad | Inconsistencia | Estado en Postgres/Team360 |
| Browser automation fragil | Fallas por cambios UI | Probes, screenshots, selectors versionados, fallback humano |
| Multi-tenant mal aislado | Fuga de datos | Workspace/container por tenant/job, secretos aislados |
| SSE en memoria | No escala | Redis/Postgres/NATS en fase producto |
| Escritura en ERP sin control | Daño financiero/operativo | Read-only primero, aprobaciones, idempotencia |
| Payload AG-UI ad-hoc | Refactor futuro | Compatibility layer `CUSTOM`, schema interno |
| Rutas absolutas/secrets legacy | Deuda de seguridad | Config por ambiente, secret manager |

## Riesgos de negocio

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| Vender WhatsApp chatbot | Commodity, bajo ticket | Posicionar ERP AI Workflow Layer |
| Hacer proyectos a medida infinitos | Margen bajo | Paquetes verticales y templates |
| SAP B1 tarda en entrar | Ciclo comercial largo | Pilotos pyme documentales/Meli para caja |
| Soporte consume al fundador | Escala bloqueada | Runbooks, portal, auditoria, implementador funcional |
| Partners no venden solos | Pipeline lento | Demo concreta, comision clara, casos por industria |
| Seguridad insuficiente | Bloquea medianas empresas | Auditoria, permisos, logs, aprobaciones |

## Alcance real frente a 2FA/MFA agresivo

Para Team360 con Bridge Local, el limite no lo marca Playwright, Puppeteer, OpenClaw ni el LLM. Lo marca el tipo de prueba de presencia que exige el sistema externo.

Regla practica:

> Si el segundo factor puede convertirse en dato, el flujo puede automatizarse con usuario presente. Si exige presencia fisica, biometria nativa o criptografia ligada a hardware, no debe considerarse automatizable por software remoto.

Por lo tanto, la estrategia profesional no es "romper MFA". Es clasificar procesos en tres carriles:

1. Automatizacion total via API oficial o integracion tecnica.
2. Automatizacion asistida con HITL, donde el humano aprueba o inyecta el factor.
3. Proceso manual consultivo, cuando el control exige hardware, biometria o aprobacion bancaria fuerte.

### Carril 1: HITL code injection

Incluye:

- SMS OTP;
- email OTP;
- TOTP / Google Authenticator / Microsoft Authenticator en modo codigo;
- backup codes de un solo uso;
- token fisico OTP que muestra un numero en pantalla, si el humano lo lee e ingresa.

Arquitectura valida:

1. El agente remoto inicia login u operacion.
2. El Bridge Local / Browser Worker detecta el challenge.
3. Team360 emite evento `MFA_REQUIRED`.
4. El usuario recibe solicitud por WhatsApp, app o panel.
5. El usuario introduce el codigo OTP.
6. Team360 inyecta el codigo en la sesion local.
7. El navegador continua y todo queda auditado.

Modelo recomendado:

```json
{
  "mfa_mode": "HITL_CODE_INJECTION",
  "risk": "medium",
  "automation_level": "assisted",
  "requires_user": true
}
```

Condiciones minimas:

- usuario legitimo presente;
- codigo recibido por canal autorizado;
- no almacenar secretos permanentes sin contrato y custodia formal;
- registrar quien aprobo, cuando, para que operacion y desde que tenant/workspace;
- no automatizar enrolamiento inicial sin intervencion humana.

Casos tipicos:

- SAP B1 Web Client con IdP que pide TOTP;
- NetSuite con TOTP;
- portal de proveedor con OTP por email;
- homebanking que pide SMS para login, pero no para firmar operaciones criticas.

### Carril 2: remote mirroring

Incluye:

- QR dinamico que debe escanearse con app movil;
- push notification de aprobacion;
- Microsoft Authenticator push;
- Oracle / SAP / IdP corporativo con aprobacion manual;
- homebanking que pide confirmar desde app movil;
- QR login de autorizacion.

Arquitectura valida:

1. El portal muestra QR o push challenge.
2. El Bridge Local captura pantalla o estado.
3. Team360 muestra un espejo remoto seguro.
4. El usuario escanea QR o aprueba push en su dispositivo.
5. El portal confirma el challenge.
6. El Bridge continua la automatizacion.

Modelo recomendado:

```json
{
  "mfa_mode": "REMOTE_MIRRORING",
  "risk": "medium-high",
  "automation_level": "assisted",
  "requires_user": true,
  "requires_session_continuity": true
}
```

Este modelo sirve para consultas, descarga de reportes, carga de datos, conciliaciones, preparacion de lotes y procesos administrativos. No conviene prometer ejecucion autonoma de operaciones bancarias sensibles.

En bancos, la aprobacion push puede estar ligada a monto, destino, alta de beneficiario, firma de lote, geolocalizacion, dispositivo registrado o token transaccional. Team360 debe tratar esos casos como aprobacion humana fuerte, no como automatizacion completa.

### Carril 3: hardware proximity y muros duros

Incluye:

- FIDO2/WebAuthn/YubiKey con toque fisico;
- passkeys ligadas al dispositivo con user presence / user verification;
- FaceID / TouchID obligatorio sin fallback;
- smart card fisica o token USB bancario con certificado;
- firma digital con certificado en tarjeta criptografica;
- app bancaria con dispositivo enrolado y biometria local;
- desktop ERP que valida certificado local, lector USB o modulo criptografico;
- entornos con EDR, VDI controlado, device compliance o postura de seguridad.

Modelo recomendado:

```json
{
  "mfa_mode": "HARDWARE_PROXIMITY",
  "risk": "hard-stop",
  "automation_level": "not_remote_automatable",
  "requires_user_physical_presence": true
}
```

Dictamen:

- no vender como automatizable remoto;
- no intentar bypass de FIDO2, FaceID, TouchID, smart cards o tokens USB;
- usar API oficial, cuenta tecnica autorizada, proceso manual, aprobacion humana o ejecucion on-premise bajo politica del cliente;
- USB-over-IP o redireccion remota puede evaluarse solo como proyecto on-premise controlado, con aceptacion formal de riesgo, auditoria y segregacion de funciones.

### Anti-bot y alcance comercial

Team360 no debe posicionarse como plataforma para pelear contra sistemas anti-bot. Ese camino es fragil, riesgoso y malo para clientes empresariales.

Playwright es valido como RPA para ERP, portales propios o portales autorizados. Para bancos, marketplaces o plataformas con anti-bot fuerte, usarlo solo si:

- existe autorizacion contractual;
- no viola terminos;
- hay fallback manual;
- se prioriza API oficial;
- el cliente acepta mantenimiento alto.

### Clasificacion operativa

| Mecanismo MFA | Tipo | Automatizacion viable | Recomendacion |
|---|---|---|---|
| Email OTP | HITL injection | Alta | Automatizar con webhook y auditoria |
| SMS OTP | HITL injection | Alta-media | Automatizar con usuario presente |
| TOTP / authenticator app | HITL injection | Alta | No almacenar semilla salvo acuerdo formal |
| Backup code | HITL injection | Media | Usar solo emergencia, auditar |
| Push approval | Remote mirroring | Media | Requiere usuario presente |
| QR dinamico | Remote mirroring | Media | Captura y aprobacion rapida |
| App bancaria con confirmacion | Espejo/manual | Baja-media | No prometer autonomia |
| FIDO2 / YubiKey | Hardware proximity | No remoto | Manual, API u oficina cliente |
| FaceID / TouchID obligatorio | Biometria local | No remoto | Manual o API |
| Smart Card USB | Hardware proximity | No SaaS remoto | Solo on-prem controlado |
| Certificado software exportable | Depende | Media | Revisar compliance |
| Certificado no exportable | Hardware/OS-bound | Baja/no | Manual u on-prem |
| Portal con anti-bot agresivo | Anti-detect | Inestable | API o acuerdo formal |

### Estados y eventos Team360

Estados de ejecucion recomendados:

- `RUNNING`
- `WAITING_FOR_MFA`
- `WAITING_FOR_HUMAN_APPROVAL`
- `WAITING_FOR_HARDWARE_ACTION`
- `BLOCKED_BY_POLICY`
- `COMPLETED`
- `FAILED`

Evento estandar para OTP:

```json
{
  "type": "MFA_REQUIRED",
  "workspace_id": "cliente_producto",
  "run_id": "uuid",
  "provider": "netsuite",
  "mechanism": "TOTP",
  "mode": "HITL_CODE_INJECTION",
  "expires_in_seconds": 30,
  "risk_level": "medium",
  "user_action_required": true,
  "allowed_actions": ["submit_code", "cancel"]
}
```

Evento estandar para QR / push:

```json
{
  "type": "MFA_REQUIRED",
  "mechanism": "PUSH_OR_QR",
  "mode": "REMOTE_MIRRORING",
  "expires_in_seconds": 60,
  "mirror_url": "internal-secure-session-url",
  "allowed_actions": ["approve_on_device", "cancel"]
}
```

Evento para muro duro:

```json
{
  "type": "AUTOMATION_BLOCKED",
  "mechanism": "FIDO2_SECURITY_KEY",
  "mode": "HARDWARE_PROXIMITY",
  "reason": "Requires local user presence on registered authenticator",
  "recommended_next_step": "Manual approval or official API integration"
}
```

### Implicancia para producto

Donde Team360 si es producto:

- descargar reportes;
- consultar facturas, stock y estados de cuenta;
- cargar pedidos y comprobantes;
- preparar transferencias sin firmarlas;
- generar lotes;
- iniciar conciliaciones;
- consultar SAP B1, NetSuite y portales de proveedores;
- agente hace el 90% operativo y humano aprueba el 10% sensible.

Donde Team360 debe vender consultoria/proceso gobernado:

- transferencias bancarias;
- alta de beneficiarios;
- firma de nomina;
- presentaciones fiscales con certificado;
- operaciones con token USB;
- confirmaciones biometricas;
- WebAuthn/YubiKey obligatorio;
- homebanking corporativo con doble aprobacion.

Frase comercial recomendada:

> Automatizamos procesos administrativos incluso cuando hay MFA, con intervencion humana controlada cuando el sistema lo exige. Donde hay firma fuerte, hardware fisico o biometria obligatoria, el agente prepara la operacion y el humano autoriza.

Esto protege tecnica, legal y comercialmente a Team360. El diferencial no es prometer bypass, sino automatizacion gobernada, trazabilidad, aprobacion humana y respeto por los controles de seguridad del cliente.

## Roadmap recomendado

### Fase 0: decision y contratos

Duracion: 1 a 2 semanas.

- Definir contrato `Job`, `ToolCall`, `JobEvent`, `AuditLog`.
- Definir envelope SSE/AG-UI interno.
- Definir allowlist de tools por rol.
- Definir contrato `MfaChallenge`, estados de espera y eventos `MFA_REQUIRED` / `AUTOMATION_BLOCKED`.
- Definir primer plugin OpenClaw experimental.

Salida:

- especificacion tecnica corta;
- skeleton en Team360;
- criterios de seguridad.

### Fase 1: OpenClaw worker piloto con Mercado Libre

Duracion: 2 a 4 semanas.

- Portar/agregar AG-UI SSE desde Vertice360 a Team360.
- Crear worker OpenClaw con tool `meli_list_questions`.
- Reusar Mercado Libre browser lab.
- Persistir jobs/eventos.
- UI timeline.

Salida:

- demo end-to-end;
- screenshots;
- auditoria;
- borradores aprobables.

### Fase 2: documentos administrativos

Duracion: 4 a 6 semanas.

- Tool OCR SpendIQ.
- Tool ingesta concilia.
- Workflow documento -> schema -> preview -> aprobacion.
- SSE por run.
- Portal minimo para revision.

Salida:

- caso vendible a administracion;
- base para conciliacion real.

### Fase 3: SAP B1 read-only

Duracion: 6 a 10 semanas.

- Conector inicial SAP B1 read-only.
- Modelo comun de clientes, proveedores, stock, documentos.
- 5 consultas conversacionales seguras.
- 5 alertas.
- Dashboard ejecutivo.

Salida:

- demo premium para partners SAP B1;
- oferta comercial concreta.

### Fase 4: producto repetible

Duracion: 3 a 6 meses.

- Multi-tenant serio.
- Secrets por tenant.
- Templates por vertical.
- Roles/permisos.
- Onboarding.
- Documentacion.
- Monitoring.
- Billing/planes.

Salida:

- ISV regional inicial.

## Criterios de arquitectura

1. Team360 siempre es fuente de verdad.
2. OpenClaw nunca decide permisos.
3. Las tools deben ser pequeñas, typed, idempotentes cuando aplique.
4. Las skills solo instruyen; no reemplazan contratos.
5. Todo job debe tener timeline auditable.
6. Toda accion sensible requiere aprobacion.
7. Toda salida de OCR/LLM debe validarse contra schema.
8. ERP primero read-only.
9. Browser automation siempre con screenshots/reportes.
10. No usar skills externas sin revision.
11. MFA blando se automatiza solo con usuario presente y auditoria.
12. Hardware, biometria y firma fuerte son frontera manual/API/on-prem, no bypass remoto.

## Conclusion

La propuesta es buena si se corrige el rol de OpenClaw.

No conviene construir "Team360 sobre OpenClaw". Conviene construir:

> Team360 como plataforma ERP AI Workflow Layer, usando OpenClaw como worker operativo para ejecutar tools controladas.

Esto alinea tecnologia y negocio:

- acelera pilotos;
- reutiliza codigo existente;
- baja costo de desarrollo;
- mantiene control y auditoria;
- permite vender a pymes primero;
- prepara SAP B1 como vertical premium;
- evita quedar atrapados en un producto commodity de WhatsApp.

La prioridad no es agregar autonomia. La prioridad es agregar confianza operativa: permisos, trazabilidad, workflows, datos ERP y decisiones visibles.

## Documentos relacionados

- [Inventario cruzado de capacidades reutilizables](capacidades_reutilizables_inventario_2026-05-06.md)
- [Contexto de negocio: Team360 ERP AI Layer](../negocio/contexto_negocio_team360_erp_ai_layer_2026-05-06.md)
