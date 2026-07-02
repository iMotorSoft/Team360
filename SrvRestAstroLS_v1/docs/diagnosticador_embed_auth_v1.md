# Diagnosticador embebible — contrato backend auth v1

## Proposito

Definir el contrato backend para clientes embebibles multi-tenant del
Diagnosticador Team360/Vera.

Decision 8B:

- se mantiene `POST /api/diagnosis/embed/auth`;
- no se introduce token efimero ni JWT en esta fase;
- el contrato publico controlado v1 usa firma delegada por turno;
- el backend sigue resolviendo contexto exclusivamente desde `embed_clients`.

Regla central:

> Cuando un request incluye `client_id`, el backend ignora cualquier contexto
> enviado por frontend y resuelve el contexto exclusivamente desde PostgreSQL.

## Tabla PostgreSQL

Migracion preparada:

- `backend/db/migrations/008_create_embed_clients.sql`

Seed de ejemplo no automatico:

- `backend/db/migrations/008_create_embed_clients_seed_example.sql`

Aplicacion local controlada validada el `2026-06-30`:

- DB target: `team360` en `localhost:5432`
- backup logico previo local no versionado
- seed real de prueba insertado: `client_id=local_embed_demo`
- origins locales permitidos:
  - `http://127.0.0.1:3050`
  - `http://localhost:3050`
- secreto usado para smoke: no real, solo local

Columnas operativas:

- `client_id` — identificador publico del cliente embebible.
- `hmac_secret` — secreto compartido para verificar HMAC-SHA256.
- `assistant_instance_code`
- `organization_code`
- `workspace_code`
- `package_code`
- `knowledge_scope_code`
- `allowed_origins` — array JSONB de origins exactos permitidos.
- `is_active`
- `label`
- `metadata_jsonb`
- `created_at_utc`
- `updated_at_utc`

Indices y constraints:

- `idx_ec_client_id` unico;
- `idx_ec_is_active` parcial para clientes activos;
- `chk_ec_client_id_not_empty`;
- `chk_ec_hmac_secret_not_empty`;
- `chk_ec_allowed_origins_is_array`;
- `chk_ec_metadata_jsonb_is_object`.

## Request sin `client_id`

No cambia el flujo actual de Vera:

- usa defaults publicos existentes;
- mantiene la allowlist minima de Fase 7A;
- `/t360` y Vera conservan compatibilidad.

## Request con `client_id`

Body requerido:

```json
{
  "client_id": "public_demo_client",
  "timestamp": 1710000000,
  "session_id": "embed_session_001",
  "message": "Quiero automatizar turnos por WhatsApp"
}
```

Header requerido:

```text
X-T360-Signature: sha256=<hex_hmac>
```

Notas:

- `session_id` es obligatorio cuando hay `client_id`.
- `signature` no viaja en body.
- los campos de contexto del frontend quedan sin efecto cuando hay `client_id`.

## Endpoint publico controlado v1 de firma server-side

Ruta v1:

```text
POST /api/diagnosis/embed/auth
```

Request:

```json
{
  "client_id": "local_embed_demo",
  "session_id": "embed_demo_session_001",
  "message": "Quiero automatizar consultas por WhatsApp"
}
```

Headers esperados:

- `Origin` o `Referer`

Response:

```json
{
  "client_id": "local_embed_demo",
  "timestamp": 1780000000,
  "signature": "sha256=..."
}
```

Reglas:

- el endpoint genera `timestamp` server-side;
- aplica rate limit antes del lookup en DB;
- valida `client_id`, `is_active` y origin permitido;
- no crea sesion;
- no contacta LLM;
- no devuelve `hmac_secret`, tenant, scope ni `allowed_origins`.
- la firma emitida es valida solo para la combinacion exacta de
  `client_id.timestamp.session_id.message`.

## Rate limiting operativo v1

Aplica sobre:

```text
POST /api/diagnosis/embed/auth
```

Decision 8C:

- implementacion in-memory por proceso;
- sin Redis;
- sin tabla nueva de auditoria/rate limit;
- interfaz minima para futura evolucion distribuida.

Configuracion por entorno:

```text
TEAM360_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS=60
TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS=20
TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_KEYS=10000
```

Clave actual:

```text
client_id + origin + remote_ip
```

Notas:

- `origin` usa `Origin`, con fallback a `Referer` normalizado;
- `remote_ip` usa la IP del socket del request;
- no se confia en `X-Forwarded-For` por defecto en esta fase porque no hay
  politica explicita de proxy confiable declarada en el repo;
- la implementacion limpia ventanas expiradas y limita la cantidad de claves
  en memoria.

## Auditoria segura 8C

Cada intento de `POST /api/diagnosis/embed/auth` registra un evento seguro:

- `embed_auth_allowed`
- `embed_auth_rejected`
- `embed_auth_rate_limited`

Reason codes usados:

- `allowed`
- `unknown_client`
- `inactive_client`
- `invalid_origin`
- `rate_limited`
- `validation_error`

Campos registrados:

- `timestamp_utc`
- `event_type`
- `reason_code`
- `status_code`
- `client_id_hash`
- `origin_hash`
- `remote_ip_hash`
- `request_id`
- `user_agent_hash`

Campos prohibidos:

- `hmac_secret`
- firma completa
- mensaje completo
- tenant/scope
- `allowed_origins`
- contexto embed resuelto.

## Canonical string firmada

Formato v1:

```text
client_id.timestamp.session_id.message
```

Reglas:

- `message` se firma ya normalizado con `trim()`;
- separador fijo `.` ;
- algoritmo `HMAC-SHA256`;
- comparacion en tiempo constante con `hmac.compare_digest`;
- el secreto nunca se loguea ni se devuelve al cliente.

## Validaciones backend

Orden de validacion cuando existe `client_id`:

1. cargar cliente desde `embed_clients`;
2. verificar que exista;
3. verificar `is_active = true`;
4. validar `Origin`, con fallback a `Referer` normalizado al origin;
5. validar `timestamp` dentro de la ventana;
6. validar HMAC;
7. resolver contexto server-side desde la fila DB;
8. ejecutar runtime solo si todo lo anterior paso.

## Origins permitidos

`allowed_origins` contiene origins exactos:

```text
https://team360.live
https://cliente.com
https://app.cliente.com
```

No se aceptan:

- wildcard amplio;
- substring match;
- path match;
- override desde frontend.

## Timestamp window

Default:

```text
±300 segundos
```

Configurable por entorno:

```text
TEAM360_EMBED_CLIENT_TIMESTAMP_TOLERANCE_SECONDS
```

En v1 esto cubre replay basico por ventana temporal. No hay nonce store ni
deduplicacion persistente todavia.

## Errores

Cuando falla autorizacion de embed:

- status `403`;
- mensaje generico;
- sin leak de `client_id`, origins permitidos, tenant, scope o secret.

Cuando falla por rate limit:

- status `429`;
- mensaje generico `Too many embed authentication requests.`;
- header `Retry-After`;
- sin leak de `client_id`, origins, tenant, scope o secret.

Cuando la autorizacion embed no esta disponible por infraestructura DB:

- status `503`;
- mensaje generico `Embed client authorization is unavailable.`

## Validacion real de Fase 7C

Resultado sobre backend real `http://127.0.0.1:7050`:

- request sin `client_id`: `201 Created`;
- request con `client_id=local_embed_demo`, HMAC valida y origin permitido:
  `201 Created`;
- request con `client_id` valido y contexto malicioso en body: `201 Created`,
  con contexto efectivo persistido desde DB;
- `client_id` desconocido: `403 Forbidden`;
- firma invalida: `403 Forbidden`;
- origin invalido: `403 Forbidden`;
- timestamp vencido o futuro excesivo: `403 Forbidden`.

## Validacion adicional de Fase 8B

- `POST /api/diagnosis/embed/auth` sigue respondiendo solo
  `client_id`, `timestamp`, `signature`;
- una firma emitida para un mensaje no autoriza otro mensaje distinto;
- `sendPublicTurn(..., { embedAuth })` envia:
  - body: `client_id`, `timestamp`, `session_id`, `message`, `locale`,
    `interaction_response`;
  - header: `X-T360-Signature`;
- cuando existe `embedAuth`, el frontend no mezcla tenant ni scope en el body;
- Playwright demo inspecciona request/response de auth y turn sin leak de
  `hmac_secret`, `organization_code`, `workspace_code`, `package_code`,
  `knowledge_scope_code` ni `allowed_origins`.

Verificacion adicional:

- los `403` devolvieron solo `Embed client request is not authorized.`;
- no hubo leak de tenant, `allowed_origins`, `client_id` real ni `hmac_secret`;
- no se crearon filas de estado conversacional para requests rechazados.

## Validacion adicional de Fase 8C

- tests nuevos de backend:
  - under limit: PASS;
  - over limit -> `429`: PASS;
  - scope por client/origin: PASS;
  - error generico sin leak: PASS;
  - sin sesion ni firma cuando rate limit bloquea: PASS;
  - auditoria segura para `allowed`, `unknown_client`, `invalid_origin`: PASS;
  - reset de ventana: PASS.
- validacion focalizada:
  `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`
  -> `83/83 PASS`.
- validacion backend completa:
  `uv run pytest tests/ -x --ignore=tests/test_db_module.py`
  -> `1089 PASS, 9 skipped`.

## Validacion real de Fase 8A

Resultado adicional sobre backend real:

- `POST /api/diagnosis/embed/auth` con `local_embed_demo` y
  `Origin: http://127.0.0.1:3050`: `200 OK`;
- la respuesta devolvio solo `client_id`, `timestamp`, `signature`;
- la firma emitida autorizo luego `POST /api/diagnosis/turn` con `201 Created`;
- un body malicioso con `workspace_code` / `package_code` /
  `knowledge_scope_code` manipulados siguio resolviendo contexto desde DB;
- `client_id` desconocido: `403`;
- origin invalido: `403`.

## Storage del secreto

Decision v1:

- `hmac_secret` se almacena en plaintext dentro de PostgreSQL;
- no se guarda en codigo ni en seeds reales;
- no se loguea;
- el seed del repo usa placeholder.

Deuda explicitada:

- rotacion de secrets;
- cifrado at-rest o vault;
- UI/admin para alta y rotacion;
- invalidacion coordinada de clientes.

## Compatibilidad

- Vera `/t360` permanece en el flujo historico sin `client_id`;
- el backend conserva `PublicDiagnosisContext` y la allowlist 7A para el modo
  publico actual;
- el wrapper/SDK embebible queda para una fase posterior.
