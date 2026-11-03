# Actualización controlada de clasificación física SAP

Procedimiento de operación compartida preparado, NO ejecutado. La candidata física offline del 29/10 tiene un cierre separado. DEVELOPMENT; este documento no autoriza conexiones HANA, escrituras compartidas ni promoción. Contrato: [clasificación física](PHYSICAL_PRODUCT_CLASSIFICATION_V1.md).

## Preparación offline acreditada posterior

El [cierre Reference/Foundation](../../../../../data/reports/telchi/reference-v2-foundation-offline-final-r2/report.md) usa las capturas ya terminadas y la API `prepare_physical_reference`; no necesita los SELECT ni el refresh completo descritos como procedimiento futuro.

La base es la Reference enriquecida del snapshot Foundation acreditado, no el pointer histórico divergente. La preparación no escribe pointers. No repetir el Paso A para publicar esta candidata. El wrapper de publicación compartida continúa pendiente; requiere autorización separada.

El snapshot de datos del reader (`1408` en esta evidencia) y el de derivación (`1322`) deben permanecer distintos. `publish_reference_only` recibe `base_data_snapshot_id` acreditado para los stores offline; en operación real lo comprueba con el reader del connector. El manifest nuevo conserva `reference_data_snapshot_id` y las transiciones encadenadas no lo cambian.

## Dictamen histórico y límites de operación compartida

El ensayo sintético acredita compatibilidad conservadora, no la compatibilidad del próximo maestro real ni la disponibilidad de SAP. El gate estático permanece fallido por referencias ajenas al productor.

El CLI `reference_update` NO tiene capture-only, prepare-only, publish-only ni selección exclusiva de OITM. Ejecutarlo sin fixtures extrae y activa `manifests/reference_current.json` en su Data Root. NO usarlo sobre el root compartido en el Paso A.

`publish_reference_only` es una API Python existente en `update.py`, NO una opción CLI. No ejecuta extracción SAP ni escribe facts. No invocar `update.py`, ni siquiera `--dry-run`: ese flag sí lee SAP.

La API publica Foundation pero NO sincroniza `reference_current.json`, NO toma por sí misma el lock de productores y NO ejecuta el guard de recursos. No existe hoy un único comando de operación segura que reúna captura, revisión, instalación inmutable y sincronización de ambos estados.

La adaptación mínima pendiente es un wrapper local del productor existente que: selle captura completa; prepare sin activar el pointer compartido; tome lock/guard; instale Reference y crosswalk sin sobrescribir; compruebe base/identidad/contratos; publique vía API existente; y registre/reconcilie ambos pointers tras interrupción. No debe construir otro motor de publicación. Este documento no presenta ese wrapper como implementado.

## Precondiciones y configuración

Antes de autorizar una ejecución, el owner debe asignar una ventana exclusiva de productores y comprobar salud del host y disponibilidad de SAP/VPN sin modificar servicios ni credenciales.

- CWD para todos los comandos: `SrvRestAstroLS_v1/backend` desde la raíz del repositorio.
- Runtime ya instalado: `uv run --no-sync`; no instalar dependencias ni extensiones.
- SAP: `TEAM360_TELCHI_SAP_PRIVATE_CONFIG` apunta al archivo privado. Claves: `TELCHI_SAP_HANA_HOST`, `TELCHI_SAP_HANA_PORT`, `TELCHI_SAP_HANA_SCHEMA`, `TELCHI_SAP_HANA_USER`, `TELCHI_SAP_HANA_PASSWORD`. Overrides existentes: `HANA_HOST`, `HANA_PORT`, `HANA_SCHEMA`, `HANA_USER`, `HANA_PASSWORD`. No mostrar valores ni pasarlos por argumentos.
- El SQL de maestros fija el schema `TELCHI`; `HANA_SCHEMA` no lo cambia. Validar que sea la empresa autorizada.
- Paso A: `CAPTURE_DIR`, `CANDIDATE_ROOT`, `EVIDENCE_DIR`: rutas absolutas nuevas, aisladas y fuera del Data Root compartido; nunca repositorio para datos operacionales sensibles. `CANDIDATE_ROOT` contendrá SOLO copias de Reference/crosswalk y un pointer local.
- `TEAM360_TELCHI_DATA_ROOT` controla el builder Reference al importarlo. No redirige universalmente todos los módulos (por ejemplo `update.DATA_ROOT` tiene su propio default). No usarlo como garantía de sandbox de Foundation.
- Paso B requerirá configuración privada DuckLake: `TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG`, claves `TELCHI_DUCKLAKE_PG_HOST`, `TELCHI_DUCKLAKE_PG_PORT`, `TELCHI_DUCKLAKE_PG_DATABASE`, `TELCHI_DUCKLAKE_PG_USER`, `TELCHI_DUCKLAKE_PG_PASSWORD`, `TELCHI_DUCKLAKE_DATA_PATH`. No se abrió ese catálogo en el cierre offline.
- No asumir contraseña vigente. Fallo de autenticación cancela; la rotación corresponde al owner, no a este procedimiento.

## Alcance real de extracción

`reference_update.extract_from_sap` hace cinco SELECT secuenciales: un SELECT 1 y cuatro consultas completas de maestros. No es una extracción exclusiva de OITM ni un snapshot transaccional entre tablas.

| Consulta | Columnas retornadas / tablas |
| --- | --- |
| Conectividad | `SELECT 1 AS "ok" FROM DUMMY` |
| OITM | `ItemCode`, `ItemName`, `validFor`, `frozenFor`, `InvntItem`, `SellItem`, `PrchseItem`, `ItmsGrpCod`, `InvntryUom`, `SalUnitMsr`, `BuyUnitMsr`, `AvgPrice`, `LastPurPrc`, `UpdateDate`, `U_FormaFarmac` |
| OCRD | `CardCode`, `CardName`, `CardType`, `GroupCode`, `GroupNum`, `validFor`, `frozenFor`, `LicTradNum`, `CreditLine`, `UpdateDate` |
| OWHS | `WhsCode`, `WhsName`, `Locked`, `Inactive`, `updateDate`, `U_BRANCH_OFFICE_ID`, `U_TYPE`, `U_WAREHOUSE_DMS` |
| OSLP | `SlpCode`, `SlpName`, `Active`, `U_CATVENDEDOR`, `SalespersonCategoryName`, `CategorySourceLabel`; joins existentes a `CUFD` (`TableID`, `AliasID`, `FieldID`) y `UFD1` (`TableID`, `FieldID`, `FldValue`, `Descr`) |

`HanaReadOnlySource._execute` verifica SQL read-only y abre una conexión hdbcli por consulta, sin pool; cierra cursor, rollback y conexión en finally. Cinco conexiones totales en una ejecución satisfactoria; máximo una consulta activa. `fetchmany(1000)` agrupa transferencia, no limita filas: el resultado completo se acumula en memoria.

No hay retry automático, timeout explícito de conexión/statement ni cancel token en esta ruta. No afirmar que existan. El adapter configura `encrypt="false"`; la operación requiere aceptación explícita del canal privado/VPN por el owner, sin cambiar infraestructura en esta tarea.

El timestamp de `SAP_MASTER_SOURCE_AS_OF` se asigna al terminar los SELECT; no acredita simultaneidad ni fecha efectiva de negocio. La latencia/costo real sigue NOT_TESTED. No agregar COUNT, discovery ni rereads de diagnóstico.

## Paso A: captura sin publicación

Las siguientes instrucciones son para una futura autorización de lectura HANA. No se ejecutaron. Esta composición usa las funciones reales y no activa ningún pointer.

Una sola ejecución, sin otros productores ni extracción de facts. Establecer previamente las tres rutas aisladas y configuración privada, sin valores secretos en shell history. Capturar una vez:

```bash
uv run --no-sync python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
from modules.telchi.datalake.reference_update import extract_from_sap, duplicate_guard, write_json
from modules.telchi.datalake.source import HanaReadOnlySource
capture = Path(os.environ['CAPTURE_DIR']).resolve()
capture.mkdir(mode=0o700, parents=False, exist_ok=False)
rows, metadata = extract_from_sap(HanaReadOnlySource())
duplicate_guard(rows)
files = {}
for table, values in rows.items():
    path = capture / (table + '.json')
    path.write_text(json.dumps(values, ensure_ascii=False, default=str) + '\n')
    files[table] = {'rows': len(values), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
write_json(capture / 'capture_complete.json', {'source': 'SAP_HANA', 'metadata': metadata, 'files': files})
PY
```

Un directorio sin `capture_complete.json` NO es una captura aceptada; no usar sus partes. Preservarlo para revisión privada, sin retry automático. La captura no se guarda incrementalmente durante los SELECT: una interrupción puede perder lo leído en memoria. Repetir SAP requiere nueva decisión explícita.

Validar offline los hashes contra `capture_complete.json`; duplicados y claves vacías; cantidades recibidas y desapariciones contra la versión vigente; roles OCRD; cobertura de crosswalks y facts mediante evidencia existente/revisión local acotada, nunca consultas SAP adicionales. Cero filas o caídas inesperadas requieren revisión, aunque `duplicate_guard` no rechace datasets vacíos.

Confirmar columna `U_FormaFarmac`, distribución `0..5`, nulos/ausentes/UNKNOWN y casos de cada código observado; no exigir que SAP contenga los seis códigos. No inferir valores ausentes. Conservar el marcador con timestamp/query hashes/filas/duraciones como evidencia de origen.

Preparar `CANDIDATE_ROOT` con copias completas de las versiones Reference y crosswalk EXACTAS que usa Foundation vigente, incluidos enriquecimientos. Crear SU pointer local con rutas locales. No copiar facts ni el catálogo y no apuntar el pointer local a carpetas compartidas. Rechazar divergencia entre Foundation y el pointer Reference vigente antes de continuar.

Construir localmente con el CLI real, sin conexión SAP y sin mover Foundation CURRENT:

```bash
TEAM360_TELCHI_DATA_ROOT="$CANDIDATE_ROOT" uv run --no-sync python -m modules.telchi.datalake.reference_update --fixture-dir "$CAPTURE_DIR" --evidence-dir "$EVIDENCE_DIR"
```

La etiqueta `NOT_RUN_FIXTURE` del builder describe la reproducción offline, NO prueba que la captura anterior fuera sintética. La procedencia real se demuestra sólo con el marcador de captura; el builder no lo valida ni conserva automáticamente su timestamp original. Mantener ambos artefactos enlazados por hashes; no presentar el nuevo observed_at local como instante remoto exacto.

Comparar con `reference_compatibility.reference_projection(base_reference_path, candidate_reference_path)` y validar identities/contratos. NOOP no requiere publicación. Nuevos productos, cambios comerciales, otras columnas o diferencias incompatibles se rechazan; no reconstruir derivados ni facts en esta ventana. Los contadores de cobertura del resumen del builder no sustituyen reconciliación real: algunos son constantes, no mediciones.

## Paso B: publicación con autorización separada

El Paso B sigue bloqueado hasta revisión del candidato real y autorización de escritura compartida. El API permite conservar ocho componentes, pero no sustituye el wrapper operativo pendiente ni permite saltarse guards.

La llamada real disponible es:

```python
from modules.telchi.datalake.update import publish_reference_only
result = publish_reference_only(
    connector=connector,
    foundation_store=store,
    reference={"reference_version": version, "reference_path": str(immutable_reference_path),
               "source_as_of": capture_source_as_of},
)
```

`connector` debe ser `DuckLakeConnector`; `store` se construye como en `run_update`: `FoundationPublicationStore(connection_factory=lambda: connector.session(read_only=False))`. No se construyen en este cierre. No hay un comando CLI Reference-only completo que pueda recomendarse como operación lista para ejecutar.

Bajo lock exclusivo y resource preflight, el wrapper debe verificar expected Foundation ID y Reference base, instalar únicamente las nuevas carpetas Reference/crosswalk inmutables en sus rutas finales, verificar contenido y contratos y llamar a esa API. Una carpeta existente distinta/incompleta bloquea, nunca se sobreescribe.

Exigir ocho entradas: Reference, Sales, Credit Memo, OINM, OITW, Material Supply, Receivables & Collections, Purchasing. Las siete no Reference y `base_snapshot_id` deben permanecer exactos. Validar manifest, resolvers, hashes, proyecciones, snapshots y lectura FoundationReader. Dependencias desconocidas/incompatibles bloquean explícitamente.

El commit lógico usa compare-and-swap y transacción de metadata. Tras éxito verificar CURRENT único y reader fijado al snapshot anterior, sin escribir facts. Sólo después reconciliar el pointer Reference con registro durable y comparación de base. No existe transacción única filesystem/PostgreSQL; si se interrumpe entre ambos, detener productores y reconciliar bajo autorización, no repetir extracción SAP.

Antes del commit: CURRENT anterior permanece válido. Después del commit: un error de entrega del resultado puede coexistir con publicación completa; inspeccionar identidad/estado antes de decidir reintento. Nunca asumir rollback por excepción. Una repetición compatible puede ser NOOP. No ejecutar rollback real sin autorización específica y expected-current.

## Contingencias y cancelación

La prioridad es detener nuevas operaciones, conservar evidencia y no ampliar carga. No manipular Podman/VPN, credenciales, servicios ni procesos ajenos.

| Incidente | Acción conservadora |
| --- | --- |
| SAP lento | No iniciar más consultas/productores. Owner define presupuesto antes de la ventana; ruta actual carece de timeout/cancel explícitos, por lo que la cancelación remota verificable necesita coordinación DBA o adaptación. No prometer límite duro. |
| VPN perdida | Cancelar la operación, conservar captura incompleta como no válida; esperar conexión estable y nueva autorización antes de releer. No reiniciar VPN. |
| Auth fallida | Cero retry automático. Owner verifica vigencia/privilegios de credenciales fuera de Git. |
| Extracción interrumpida | Sin marcador completo no construir. No reutilizar mezcla de capturas. Nueva captura completa sólo con decisión autorizada. |
| Filas inconsistentes | Rechazar candidato; conservar evidencia y baseline. No usar el resumen PASS como prueba suficiente de cobertura. |
| Copia inmutable interrumpida | CURRENT anterior no cambia. Reintento falla cerrado si destino está incompleto; revisión y cuarentena autorizada de destinos no referenciados, jamás borrado/sobrescritura automática. Luego repetir desde captura congelada. |
| Reference incompatible | No publicar ni retocar dependencias para hacerla pasar. Revalidación específica fuera de esta ventana. |
| Foundation rechaza | Mantener CURRENT anterior si no hubo commit; comprobar metadata antes de reintentar. Conservar FAILED/evidencia y versiones históricas. |
| Fallo posterior al commit | Verificar nueva publicación íntegra, ocho componentes y snapshot. Reconciliar pointer pendiente bajo lock; rollback sólo con autorización adicional. |
| Presión de host | RESOURCE_BLOCKED/BLOCKED_HOST; no iniciar nuevas tareas, no elevar límites ni matar procesos ajenos. |

## Evidencia offline

El cierre reproducible y sus limitaciones están en [reporte](../../../../../data/reports/telchi/physical-reference-offline-close/report.md). Ningún PASS sintético es autorización de extracción ni publicación.
