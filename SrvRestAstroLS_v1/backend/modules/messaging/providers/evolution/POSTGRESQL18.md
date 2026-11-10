# Evolution — PostgreSQL 18: configuración y preflight

Runbook canónico de PostgreSQL para Evolution en Team360. Conserva la investigación acreditada y un procedimiento futuro de solo lectura; documentarlo no implica haberlo vuelto a ejecutar.

## Autoridad y alcance

[Messaging](../../README.md) es la entrada canónica del transporte. Este documento detalla su dependencia PostgreSQL, no habilita WhatsApp ni concede permisos operativos.

- PostgreSQL es un servicio externo e independiente de Evolution: se reutiliza el servidor existente, no se instala otro junto al adapter.
- Evolution API **v2.3.7**, con el backport local documentado en Messaging, corre en Podman rootless como `evolution-api`; PostgreSQL conserva sus entidades y `data/store` sus archivos.
- El laboratorio operativo existente es `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api`. Sus scripts siguen siendo autoridad de instalación; no copiar ni ejecutar `start.sh` como preflight.
- La base y el schema son `evolution_api`; la tabla investigada es `evolution_api."Message"` (mayúscula y comillas significativas).
- El runtime acreditado usa **`evodevv1_runtime`**. El rol `evolution_api` descrito en la instalación histórica no debe confundirse con el runtime actual ni usarse para inferir sus permisos.
- La base Team360 y sus tablas `message_threads`/`message_events` son persistencia del adapter, distinta de las tablas internas Evolution. La migración Team360 026 no acredita permisos sobre `"Message"`.
- Referencias generales: [driver PostgreSQL](../../../../../../lat.md/postgres-driver-policy.md), [metodología de preflight](../../../../../../lat.md/service-preflight-methodology.md) y [setup histórico Team360](../../../../../docs/postgresql_live_team360_setup.md). Sus inventarios históricos no sustituyen esta configuración Evolution.

## Configuración y conexiones separadas

La conexión administrativa Team360 se reutilizó desde [modules/db/settings.py](../../../db/settings.py) hacia `globalVar.py`. No se instaló `psql` ni se cambiaron permisos.

El resolver `get_database_settings()` prioriza `TEAM360_DB_URL`, `TEAM360_DB_URL_PSQL`, `DB_PG_V360_URL` (sustituye la base por `team360`) y finalmente `globalVar.get_team360_db_url_psql()`. Normaliza `postgresql+psycopg` a `postgresql`.

Esa conexión permite inspección administrativa con las credenciales ya disponibles; **no es** la identidad que usa Evolution. Para inspeccionar Evolution se selecciona explícitamente `dbname=evolution_api`, sin modificar la configuración ni su archivo fuente.

Evolution obtiene su conexión del entorno efectivo del contenedor, `DATABASE_PROVIDER` y `DATABASE_CONNECTION_URI`; la URI Prisma selecciona base y schema. El entorno privado que recrea el contenedor puede divergir de su entorno cargado: inspeccionar este último sin imprimirlo. No copiar contraseñas, tokens ni URI/DSN completos, tampoco en excepciones o logs.

## Evidencia acreditada y matriz de permisos

Los siguientes resultados fueron aportados como confirmados: configuración del contenedor contrastada con conexión real. No constituyen una nueva medición ni una garantía permanente de disponibilidad.

| Comprobación | Resultado acreditado |
| --- | --- |
| PostgreSQL | 18.4 |
| Base / schema / runtime | `evolution_api` / `evolution_api` / `evodevv1_runtime` |
| Autenticación runtime | PASS |
| CONNECT a la base | TRUE |
| USAGE del schema | TRUE |
| SELECT sobre `evolution_api."Message"` | TRUE |
| INSERT sobre `evolution_api."Message"` | TRUE, mediante catálogo |
| UPDATE sobre `evolution_api."Message"` | FALSE |
| DELETE sobre `evolution_api."Message"` | FALSE |
| Secuencia de Message | NOT_APPLICABLE |
| INSERT funcional ejecutado en la investigación | NO |
| Corrección requerida | NONE |

UPDATE y DELETE no están concedidos y no se demostró su necesidad para el incidente investigado. No recomendar privilegios adicionales sin identificar una operación funcional que los justifique. Esta matriz no afirma suficiencia para todas las operaciones de Evolution.

La denegación histórica de INSERT ya no se reproduce en los privilegios efectivos actuales. No hay evidencia de cuándo ni cómo cambió: no atribuir la resolución a una intervención concreta.

`has_table_privilege(..., 'INSERT') = true` acredita autorización de tabla por catálogo, **no un INSERT funcional**. Constraints, RLS, defaults, triggers, relaciones y otras tablas pueden imponer requisitos adicionales. No ejecutar INSERT, ni siquiera seguido de rollback, como parte de este preflight.

## Preflight obligatorio de solo lectura

Ejecutar antes de depender de esta integración, sin arrancar servicios. Usar el entorno backend existente con `uv`, `psycopg` y Podman; no instalar `psql`, no usar las sondas de sesión que habilitan webhooks.

### Estado y red del contenedor

Estos comandos consultan el contenedor existente. Si está detenido o falta, registrar bloqueo de entorno; no iniciarlo, reiniciarlo ni recrearlo desde este procedimiento.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api
./status.sh
podman port evolution-api
podman exec evolution-api node -e '
const net = require("net");
const u = new URL(process.env.DATABASE_CONNECTION_URI);
const s = net.connect({host: u.hostname, port: Number(u.port || 5432)});
s.setTimeout(5000);
s.on("connect", () => { console.log("CONTAINER_DB_TCP=PASS"); s.end(); });
s.on("timeout", () => { console.log("CONTAINER_DB_TCP=TIMEOUT"); s.destroy(); process.exitCode=1; });
s.on("error", () => { console.log("CONTAINER_DB_TCP=FAIL"); process.exitCode=1; });
'
```

La sonda TCP no autentica ni prueba permisos. La autenticación SQL siguiente se hace desde el host contra el endpoint administrativo existente, con las credenciales runtime del contenedor. La comprobación de red anterior es separada.

### Autenticación y consultas de catálogo

Este bloque usa dos conexiones secuenciales, acotadas y read-only. No imprime secretos ni lee mensajes. El SQL incluido es el procedimiento reproducible; no es un servicio nuevo ni se ejecuta al leer este documento.

Desde la raíz Team360, con el entorno privado habitual ya disponible:

```bash
cd SrvRestAstroLS_v1/backend
uv run python - <<'PY'
import asyncio
import json
import subprocess
from urllib.parse import urlsplit, parse_qs, unquote

import psycopg
from psycopg.conninfo import conninfo_to_dict
from modules.db.settings import get_database_settings

IDENTITY = """
SELECT current_setting('server_version') AS version,
       current_database() AS database, current_user AS role,
       session_user AS login_role, inet_server_addr()::text AS server_address,
       inet_server_port() AS server_port,
       current_setting('transaction_read_only') AS read_only,
       current_setting('search_path') AS search_path,
       to_regnamespace('evolution_api')::text AS schema,
       to_regclass('evolution_api."Message"')::text AS message_table
"""
PRIVILEGES = """
SELECT has_database_privilege(current_user, current_database(), 'CONNECT'),
       has_schema_privilege(current_user, 'evolution_api', 'USAGE'),
       has_table_privilege(current_user, 'evolution_api."Message"', 'SELECT'),
       has_table_privilege(current_user, 'evolution_api."Message"', 'INSERT'),
       has_table_privilege(current_user, 'evolution_api."Message"', 'UPDATE'),
       has_table_privilege(current_user, 'evolution_api."Message"', 'DELETE')
"""
COLUMNS = """
SELECT a.attname, a.attidentity,
       pg_get_expr(d.adbin, d.adrelid) AS default_expression,
       pg_get_serial_sequence('evolution_api."Message"', a.attname) AS sequence
FROM pg_attribute a
LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
WHERE a.attrelid='evolution_api."Message"'::regclass
  AND a.attnum>0 AND NOT a.attisdropped
ORDER BY a.attnum
"""
TABLES = """
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity, c.relforcerowsecurity,
       has_table_privilege(current_user, c.oid, 'SELECT') AS can_select,
       has_table_privilege(current_user, c.oid, 'INSERT') AS can_insert,
       has_table_privilege(current_user, c.oid, 'UPDATE') AS can_update,
       has_table_privilege(current_user, c.oid, 'DELETE') AS can_delete
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='evolution_api' AND c.relkind IN ('r','p')
ORDER BY c.relname
"""

async def main():
    # Inspect se captura solo en memoria: nunca imprimir su JSON/Config.Env.
    result = subprocess.run(
        ['podman', 'inspect', 'evolution-api'], capture_output=True,
        text=True, check=True, timeout=10,
    )
    container = json.loads(result.stdout)[0]
    if container['State']['Status'] != 'running':
        raise ValueError('container_not_running')
    env = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
    uri = urlsplit(env['DATABASE_CONNECTION_URI'])
    query = parse_qs(uri.query)
    if env.get('DATABASE_PROVIDER') != 'postgresql':
        raise ValueError('provider_mismatch')
    if (uri.scheme not in ('postgres', 'postgresql')
        or unquote(uri.path.lstrip('/')) != 'evolution_api'
        or unquote(uri.username or '') != 'evodevv1_runtime'
        or query.get('schema') != ['evolution_api']):
        raise ValueError('runtime_configuration_mismatch')
    # No ignorar opciones SSL: admitir solo las compatibles conocidas.
    if set(query) - {'schema', 'sslmode'}:
        raise ValueError('review_uri_options_privately')
    print('CONTAINER_PROVIDER_DATABASE_SCHEMA_ROLE=PASS')
    print('CONTAINER_IMAGE=' + container['Config']['Image'])
    admin = conninfo_to_dict(get_database_settings().dsn)
    admin['dbname'] = 'evolution_api'
    options = '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'
    common = dict(connect_timeout=5, options=options, application_name='evolution-pg18-readonly')
    async with await psycopg.AsyncConnection.connect(**(admin | common)) as conn:
        row = await (await conn.execute(IDENTITY)).fetchone()
        print('ADMIN_IDENTITY=', row)
        server = row[4:6]
    # Endpoint host explicitamente reutilizado; no usar SET ROLE como autenticación.
    runtime = {k: admin[k] for k in ('host', 'hostaddr', 'port') if k in admin}
    runtime.update(dbname='evolution_api', user=unquote(uri.username or ''),
                   password=unquote(uri.password or ''))
    if 'sslmode' in query:
        runtime['sslmode'] = query['sslmode'][0]
    async with await psycopg.AsyncConnection.connect(**(runtime | common)) as conn:
        row = await (await conn.execute(IDENTITY)).fetchone()
        print('RUNTIME_IDENTITY=', row)
        if row[1:4] != ('evolution_api', 'evodevv1_runtime', 'evodevv1_runtime') or row[4:6] != server:
            raise ValueError('database_role_or_server_mismatch')
        print('DB_AUTHENTICATION=PASS')
        print('CONNECT_USAGE_SELECT_INSERT_UPDATE_DELETE=',
              await (await conn.execute(PRIVILEGES)).fetchone())
        for column in await (await conn.execute(COLUMNS)).fetchall():
            print('MESSAGE_COLUMN=', column)
            if column[3]:
                print('SEQUENCE_USAGE_SELECT=', await (await conn.execute(
                    "SELECT has_sequence_privilege(current_user, %s, 'USAGE'), "
                    "has_sequence_privilege(current_user, %s, 'SELECT')",
                    (column[3], column[3]),
                )).fetchone())
        for table in await (await conn.execute(TABLES)).fetchall():
            print('TABLE_OWNER_RLS_PRIVILEGES=', table)
    print('ACTUAL_INSERT_EXECUTED=NO')

try:
    asyncio.run(main())
except Exception as exc:
    # No str(exc), traceback ni stderr de inspect: podrían contener credenciales.
    print('PREFLIGHT=BLOCKED', 'error_type=' + type(exc).__name__,
          'sqlstate=' + str(getattr(exc, 'sqlstate', None)))
    raise SystemExit(1)
PY
```

Revisar explícitamente: versión esperada 18.4 (una actualización exige registrar la nueva versión), base/schema/tabla presentes, roles correctos, read-only `on` y los cuatro primeros privilegios TRUE. UPDATE/DELETE FALSE reproducen la matriz, no son un fallo del incidente.

La reutilización del endpoint administrativo requiere confirmar que el host/puerto del contenedor apunta al mismo servidor (instalación conocida: `host.containers.internal:5432` hacia PostgreSQL existente). Comparar en privado URI y publicación de PostgreSQL; si hay dos servidores posibles, el preflight queda **PENDING**, no inferir equivalencia por nombres de base. No sustituir automáticamente un endpoint desconocido.

Si todas las secuencias asociadas son NULL y ningún default usa una secuencia, registrar `MESSAGE_SEQUENCE=NOT_APPLICABLE`. Revisar también expresiones `nextval(...)` de defaults con secuencias no asociadas; consultar sus privilegios con `has_sequence_privilege` sin llamar `nextval` ni `setval`. Para identity/serial, interpretar según la operación concreta: no conceder USAGE/SELECT por rutina.

Un fallo de catálogo por schema/tabla inexistente bloquea el preflight. Una consulta exitosa tampoco convierte valores FALSE en PASS. Registrar resultados y hora por separado, sin DSN, números WhatsApp ni contenido de mensajes.

### Errores de base de datos

Revisar una ventana de logs que cubra el último arranque y, si existe, el incidente. Los logs pueden contener secretos heredados: no volcarlos ni adjuntarlos en bruto a la conversación o evidencia.

Ejemplo acotado desde cualquier directorio, que solo publica conteos de patrones, no líneas originales:

```bash
uv run --project SrvRestAstroLS_v1/backend python - <<'PY'
import re
import subprocess
r = subprocess.run(['podman', 'logs', '--since', '1h', '--tail', '2000', 'evolution-api'],
                   capture_output=True, text=True, timeout=15)
if r.returncode:
    print('DB_LOG_REVIEW=BLOCKED')
    raise SystemExit(1)
text = r.stdout + r.stderr
for pattern in ('permission denied', 'authentication failed', 'database .* does not exist',
                'schema .* does not exist', 'relation .* does not exist',
                'P1000', 'P1001', 'P1010', 'PrismaClient', 'connection refused'):
    print(pattern, len(re.findall(pattern, text, re.I)))
print('LOG_WINDOW=1h; MAX_LINES=2000; RAW_LOGS_NOT_PRINTED')
PY
```

Cero coincidencias solo significa ausencia de esos patrones en la ventana limitada. Revisar privadamente otros errores Prisma/PostgreSQL, logs de PostgreSQL si están disponibles y cobertura temporal; registrar `PENDING` si no se cubrió el incidente. HTTP 200/health por sí solo no acredita permisos ni ausencia de errores.

## Diagnóstico de permission denied for table Message

No aplicar GRANT por reflejo. Primero correlacionar hora, contenedor, base, schema, rol y operación real del error; compararlos con el preflight y la matriz acreditada.

1. **Base/schema equivocados:** comprobar `current_database()`, `search_path`, `to_regclass` cualificado y el parámetro `schema` Prisma; no asumir `public."Message"` ni `message` sin comillas.
2. **Rol equivocado:** contrastar usuario cargado en `DATABASE_CONNECTION_URI`, `session_user` y `current_user` de una autenticación real. `SET ROLE` administrativo no prueba el password runtime.
3. **Privilegios efectivos:** comprobar CONNECT, USAGE y la operación concreta con `has_*_privilege`; una ACL explícita no muestra por sí sola privilegios heredados, ownership o PUBLIC. Revisar RLS si corresponde.
4. **Migraciones nuevas:** inventariar tablas, particiones, defaults, identity y secuencias con las consultas anteriores. Una tabla nueva puede tener owner/ACL diferentes; permisos de `"Message"` no cubren todo el schema.
5. **Owner o ACL cambiados:** comparar inventario antes/después; revisar en privado `pg_class.relacl`, `pg_namespace.nspacl`, membresías de `pg_roles`/`pg_auth_members` y `pg_default_acl` del rol creador. Default privileges no son retroactivos ni globales para todos los creadores.
6. **Divergencia de configuración:** contrastar contenedor efectivo, configuración privada de recreación y servidor real. El archivo `.env` actual no prueba qué cargó el contenedor existente.
7. **Decisión:** si INSERT sigue TRUE, no atribuir el error histórico al estado actual. Buscar otro momento/servidor/rol/objeto u operación; preservar evidencia y no inventar una corrección retrospectiva.

Cualquier cambio de privilegios requiere tarea y alcance propios, operación funcional justificada y regresión específica. Este runbook **no autoriza GRANT, ALTER ROLE, migraciones ni cambios de propietario**, manuales o automáticos.

## Checklist de mantenimiento y piloto

Aplicar después de migraciones Evolution, cambios de rol/permisos o recreación del contenedor, y antes de un piloto WhatsApp real. Revalidar no implica autorizar esos cambios ni activar el piloto.

- [ ] Registrar versión Evolution/imagen y PostgreSQL, fecha y cambio que motiva la revisión.
- [ ] Comparar configuración efectiva con la esperada sin guardar secretos; confirmar endpoint/base/schema/rol y autenticación real.
- [ ] Ejecutar el preflight read-only completo y revisar logs con cobertura declarada.
- [ ] Comparar inventario de tablas/owners/RLS y defaults/secuencias antes/después; no limitarse a `"Message"` si aparecieron objetos nuevos.
- [ ] Asociar cada tabla nueva y permiso requerido a la operación Evolution que la consume. Detectar brechas antes de habilitar tráfico.
- [ ] Revisar privilegios por defecto del creador de las migraciones y ACL de objetos ya creados; no suponer herencia automática ni otorgar permisos de schema completo.
- [ ] Si el runtime restringido no puede migrar, detener la promoción y separar la ejecución de migraciones autorizada; no elevarlo ni ejecutar el entrypoint migrador como diagnóstico.
- [ ] Mantener `ACTUAL_INSERT_EXECUTED=NO` para este preflight. Una validación funcional posterior requiere alcance propio y no se acredita con catálogo.
- [ ] Ante brechas, registrar bloqueo y proponer el mínimo cambio justificado, sin ejecutarlo automáticamente.
- [ ] Antes del piloto, exigir además los gates funcionales/seguridad/operación de Messaging; esta matriz no habilita Meta, Cloudflare, webhooks ni envío WhatsApp.

## Automatización futura propuesta

Conviene extraer posteriormente este procedimiento a una utilidad read-only del proveedor Evolution, reutilizando `modules/db/settings.py` y psycopg existentes, sin servicio ni pool paralelo.

La propuesta debe producir un reporte saneado de identidad/configuración, catálogo, tablas nuevas, secuencias y cobertura de logs; fallar cerrado ante divergencias y distinguir `CATALOG_INSERT_ALLOWED` de `FUNCTIONAL_INSERT_NOT_RUN`. No incluir auto-GRANT, migraciones, reinicios o activación de canales. Probarla con fixtures antes de una ejecución real autorizada. **No implementada en esta tarea.**
