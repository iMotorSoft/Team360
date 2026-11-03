# Frontera efectiva de PostgreSQL

Inspección del 2026-10-14, exclusivamente read-only. Se acredita separación física respecto del backend productivo oficial; no se certifica seguridad multitenant ni runtime Srv05 autenticado.

## Evidencia actual

Las sondas usaron el resolver real de configuración, sin importar aplicaciones, abrir pools runtime ni imprimir DSN, contraseñas o tokens.

| Contexto | Host cliente / puerto | DB / esquema | Rol | System identifier | Clasificación |
| --- | --- | --- | --- | --- | --- |
| Shell local heredada | localhost:5432 | team360 / public | administrator | 7630993354699489317 | DEV_VERIFIED para destino local designado |
| Override backend-dev.local | localhost:5432 | team360 / public | administrator | 7630993354699489317 | DEV_VERIFIED para destino local designado |
| Srv01 desplegado en destino oficial | localhost:5432 en host remoto | team360 / esquema no consultado | administrator | 7559180602161319971 | PRODUCTION_VERIFIED |
| Pool de Srv05 vivo | No observado | No observado | No observado | No observado | UNKNOWN |
| Otros consumidores productivos no inventariados | No observado | No observado | No observado | No observado | UNKNOWN |

Local: PostgreSQL 18.4, pgvector 0.8.2, dirección servidor 172.18.0.2/32. Remoto: PostgreSQL 18.3, también 172.18.0.2/32. Igual IP Docker, nombre DB y rol **no significan mismo servidor**.

[database_probe.json](database_probe.json) registra SQL, configuración sanitizada y resultados. [production_probe.json](production_probe.json) obtiene el entorno de los procesos Srv01 existentes, PIDs 2237139/2237143, en el cwd productivo canónico y consulta su destino con READ ONLY. SSH exit 0; no se leyó ningún .env remoto.

[container_inventory.json](container_inventory.json) vincula el destino local con imotorsoft-postgres, imagen PG18, red 172.18.0.2 y volumen físico local bajo /media/issajar/DEVELOP/docker-data. Es una instancia local distinta del destino remoto oficial, no una segunda DB creada dentro de producción.

La designación DEV del cluster local consta en el [aprovisionamiento autorizado previo](../../telchi/whatsapp-assistant-dev-live-v1/real_provisioning_report.md), sección 1. No se reutiliza su aceptación administrativa como prueba física: la comparación de clusters es nueva.

## Resolución y consumidores

La configuración es compartida por varios módulos; no existe una conexión runtime exclusiva Business Semantics en la composición inspeccionada.

Prioridad efectiva en modules/db/settings.py: TEAM360_DB_URL → TEAM360_DB_URL_PSQL → DB_PG_V360_URL reemplazando la DB por team360 → globalVar.get_team360_db_url_psql. En ambos contextos locales prevalece **DB_PG_V360_URL**. TEAM360_ENV no cambia el DSN.

ls_iMotorSoft_Srv05.py delega create_app a Srv01. routes/automation_diagnosis.py crea/setea el pool con get_database_settings; la composición Telchi obtiene ese pool; handler/resolver reciben su conexión. Flow, Console, Diagnosis y Messaging también consumen el pool/configuración. Cambiar el rol global impactaría esos consumidores.

La muestra pg_stat_activity local registra LiteLLM en su propia DB y sólo la sonda en team360. Esto no prueba ausencia permanente de otros consumidores. El cluster contiene también v360, evolution_api, concilia_fce, tebaai y catálogo DuckLake; no se tocaron esas bases.

## Alcance y reproducción

Se demuestra separación del destino productivo oficial actual, no todos los despliegues posibles, ausencia de copias de datos productivos ni segregación de credenciales.

No había listener/backend local Srv05 al inspeccionar. El launcher normal todavía inicia Srv01; no fue ejecutado. Por ello EFFECTIVE_DB_IDENTIFIED queda PARTIAL para la exigencia estricta de observar el pool Srv05 vivo.

Desde backend:

```bash
PYTHONPATH=. uv run --no-sync python ../../data/reports/team360/business_semantics_security_unblock_v1/probe_readonly.py
```

La sonda impone default_transaction_read_only=on, statement_timeout=5s, connect_timeout=5s y rollback. Sólo consulta metadatos e inventarios agregados. No ejecutar live_evidence.py: hace seed y commit, además de pruebas posteriores con rollback.
