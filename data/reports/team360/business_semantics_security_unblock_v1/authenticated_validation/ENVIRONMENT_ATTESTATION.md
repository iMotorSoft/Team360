# Destino y privilegios efectivos

Lectura real del 2026-10-14T17:41Z; ninguna escritura DB, autenticación humana ni aplicación iniciada. DEV_ISOLATION=PASS para el cluster local designado, no certificación integral de seguridad.

## Conexiones comprobadas

La sonda conecta usando los resolvers existentes y el archivo privado existente, sin imprimir DSN ni claves. Evidencia SQL y resultados: [environment_probe.json](environment_probe.json).

| Camino | Origen | Host:puerto / DB / esquema | Rol observado |
| --- | --- | --- | --- |
| Shell heredada | DB_PG_V360_URL, sustitución DB por team360 | localhost:5432 / team360 / public | administrator |
| Override launcher DEV | ../.env.backend-dev.local → DB_PG_V360_URL | localhost:5432 / team360 / public | administrator |
| Config de CLI autenticada | issuer.json → runtime_dsn | localhost:5432 / team360 / public | team360_business_semantics_dev_runtime |
| Pool vivo Srv05 | No observado | NOT_OBSERVED | NOT_OBSERVED |

Los tres probes observaron PG18.4, dirección servidor 172.18.0.2/32, system_identifier 7630993354699489317, search_path="$user", public y transaction_read_only=on. El pin privado coincide. Guard checked_target(runtime=True)=PASS en conexión real.

## Aislamiento físico y alcance

Se reutiliza la acreditación física previa y se confirma que el destino local conserva el mismo cluster, contenedor y volumen; no se volvió a conectar a producción.

[DATABASE_BOUNDARY.md](../DATABASE_BOUNDARY.md) compara el cluster remoto oficial 7559180602161319971 con el local 7630993354699489317 y enlaza su designación DEV autorizada. [provenance.json](provenance.json) actualiza contenedor, mounts, red y listeners locales.

PASS acredita separación del despliegue productivo oficial documentado, no exclusividad del cluster: comparte otros proyectos y publica 5432 en interfaces globales. No acredita firewall, ausencia de copias productivas ni todos los despliegues posibles. Sólo operaciones DEV autorizadas y acotadas; no crear otras bases/esquemas.

## Privilegios y rutas

El rol dedicado está probado en la DB real y en la configuración que usa la CLI; no se extrapola al pool global ni a una sesión de usuario.

administrator: SUPERUSER=true, BYPASSRLS=true, CREATEROLE=true, CREATEDB=true; propietario de las ocho tablas semánticas. Rol dedicado: los cuatro flags=false, INHERIT=false, sin membresías ni ownership público según guard; SELECT/INSERT/UPDATE semánticos, sin DELETE; credenciales sólo SELECT; intentos SELECT/INSERT/UPDATE; core_events sólo INSERT.

RLS: ocho tablas semánticas con relrowsecurity=false y relforcerowsecurity=false; pg_policies vacío. row_security=on NO implica políticas activas. Rol dedicado puede leer varios tenants a nivel SQL: sólo predicados de aplicación, sin defensa DB independiente.

modules/telchi/assistant/composition.py obtiene get_pool; PostgresConversationStore recibe esa conexión; handler invoca resolver con ella. routes/automation_diagnosis.py construye el pool global desde get_database_settings. No consume issuer.json. Console, Flow, Diagnosis, Messaging y Telchi comparten configuración/pool: no se cambió.

No hay entrypoint Srv01/Srv05/dev_runtime_http detectado ni listener backend en la muestra. pg_stat_activity no observó runtime team360, sólo la sonda; LiteLLM sí utiliza su DB. No se inició servidor con lifecycle/automatización compartida. EFFECTIVE_RUNTIME_ROLE=PARTIAL: rol CLI real PASS; runtime global no restringido ni observado autenticado.

## Reproducción y recursos

El probe es metadatos/contadores agregados con read-only forzado, timeout 5s y rollback; no consulta contenido privado de tenants.

```bash
cd SrvRestAstroLS_v1/backend
PYTHONPATH=. uv run --no-sync python ../../data/reports/team360/business_semantics_security_unblock_v1/authenticated_validation/attest_readonly.py
```

Host SAFE: 8 cores, carga 1.72/1.42/1.12, MemAvailable 6514 MiB, swap 1982 MiB estable, vmstat si/so=0 durante muestras, CPU idle 85–88%. Una conexión a la vez; pytest un worker; cero browsers/contenedores/servicios nuevos; cero procesos ajenos terminados. No se repitió preparación ni migraciones.
