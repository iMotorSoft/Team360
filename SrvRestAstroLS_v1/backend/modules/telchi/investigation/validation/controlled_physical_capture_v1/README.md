# Continuación segura de captura física

Este runner investigativo captura solo OITM; no publica Reference/Foundation ni cambia CURRENT. La implementación y las pruebas son offline. Cualquier conexión futura requiere una autorización nueva.

## Diagnóstico y preservación

El runner anterior creaba siempre un directorio nuevo y comenzaba con clave nula. Validar checkpoints no implementaba continuación. Ahora el checkpoint validado determina la clave inicial y la numeración de lotes.

- Original preservado: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-capture-20261028T174757Z`.
- Inspección read-only: 44 lotes, 4.400 filas únicas, hashes y orden estricto válidos; 47 archivos originales sin cambios.
- SHA-256 del checkpoint original: `88c1560d45352e61ae58c9782137e9b8e2f08a4822072fa3578d0fc9c4a144c2`.
- La continuación preparada usa una copia validada en otro destino privado. No se inventan claves ni se reconstruyen checkpoints manualmente.

## Protocolo y sesiones

Cada ejecución toma un bloqueo exclusivo del directorio antes de validar o escribir. Los lotes anteriores son inmutables; el checkpoint es el índice acumulado y las sesiones conservan sus propios registros.

- `--resume` exige un destino existente válido; sin ese flag, un destino existente se rechaza.
- `--resume --resume-from SOURCE` copia un prefijo validado a un destino **nuevo**, con hashes, sesiones anteriores y lineage en `origin.json`. La fuente también se bloquea durante la copia, sin escribirla.
- SQL fijo con `TOP` entero validado y `WHERE "ItemCode" > ? ORDER BY "ItemCode"`; la clave se pasa como parámetro. No hay OFFSET ni consultas de discovery/preflight adicionales dentro del runner.
- Se validan versión/source, nombres secuenciales, fingerprints SQL, hashes, columnas, cantidades, claves únicas y orden estricto entre todos los lotes.
- `pending.json` registra el checkpoint candidato y el hash del checkpoint base antes de guardar un lote. El lote se guarda con rename atómico y fsync; luego se actualiza el checkpoint.
- Si el lote durable existe, la próxima ejecución lo verifica y adopta sin repetir su consulta. Si no existe, se descarta solo el journal no confirmado: la clave sigue siendo la última confirmada.
- Recuperar un journal válido dos veces no cambia el resultado. Un journal corrupto, prefijo incompatible o lote sin journal/checkpoint se rechaza, sin conexión.
- `sessions/<uuid>.json` conserva inicio/fin, presupuesto, latencias, filas iniciales, hashes base/final, cierre de recursos y recuperación pendiente. Cada lote nuevo conserva `session_id` y `observed_at`; el prefijo legacy conserva sus fechas y `operation.json` originales.
- Consistencia: `MULTI_SESSION_INTERVAL_SCAN_NOT_TRANSACTIONAL_SNAPSHOT`. Nunca se acredita un snapshot transaccional. `analyze.py` rechaza capturas con sesiones nuevas hasta disponer de acreditación de consistencia y análisis session-aware separados.

## Comando preparado, no ejecutado

El siguiente comando es exclusivamente para una autorización SAP futura. Ejecuta un solo microbloque y preserva el original. El destino debe no existir; no reutilizarlo con `--resume-from`.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
UV_OFFLINE=1 uv run --no-sync python -m modules.telchi.investigation.validation.controlled_physical_capture_v1.capture \
  /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-capture-resume-20261028-offline-ready \
  --resume \
  --resume-from /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-capture-20261028T174757Z \
  --batch-size 25 --max-queries 5 --pause-seconds 10 --latency-seconds 1.5
```

El checkpoint destino será `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-capture-resume-20261028-offline-ready/checkpoint.json`. La primera consulta usa estrictamente la última clave confirmada como límite exclusivo, no un ordinal 4.401.

## Detención y validación posterior

El presupuesto es un máximo, no una meta obligatoria. No se inicia otro bloque automáticamente, no aumenta el lote y no hay reintentos ni reconexiones automáticos.

- Defaults y límites máximos: 25 filas por consulta, 5 consultas por ejecución, concurrencia 1, reintentos 0. Pausa mínima de 10 s entre consultas; pueden reducirse lote/presupuesto o aumentarse pausas.
- Latencia superior a 1,5 s: se valida y confirma el resultado ya recibido, pero no se inicia otra consulta. No significa cancelación de una consulta en vuelo. El timeout del cursor de 3 s es una protección distinta y dependiente del driver.
- Error de consulta, validación, escritura o interrupción: se detiene sin reintentar; se intenta cerrar cursor/conexión. Fallos de cierre se reflejan en la sesión.
- Presupuesto agotado: `PARTIAL` con `query_budget_exhausted`; EOF: `CAPTURE_COMPLETE` solo en el sentido de fin del recorrido, no de consistencia transaccional ni publicación. Un checkpoint con EOF no vuelve a consultarse.
- Revisar exit code, `stop_reason`, fechas, `queries <= 5`, `batch_size <= 25`, `retries = 0`, `concurrency = 1`, cursores cerrados y conexión cerrada. No basta un exit code 0 para declarar captura completa.
- Validar offline el destino tras el cierre con `recover()`; comprobar filas únicas y orden, hashes, sesiones, conservación del prefijo y de los 47 archivos originales. No ejecutar `analyze.py` como si todas las sesiones fueran una sola observación.

## Recuperación y siguiente ejecución explícita

Nunca borrar o editar a mano un journal, lote o checkpoint para forzar la continuación. La recuperación automática del journal ocurre bajo el mismo bloqueo antes de cualquier conexión.

- Para un siguiente bloque autorizado, ejecutar el mismo módulo sobre el **destino nuevo** con `--resume` y los mismos cuatro controles, **omitiendo `--resume-from`**. Esto puede consultar SAP y requiere autorización propia.
- Antes de SAP, un operador puede inspeccionar read-only con `read_checkpoint()`/`recover()`. Si hay journal, la vista checkpoint puede aún excluir el lote durable pendiente; no inferir que debe repetirse.
- Para resolver únicamente el journal sin SAP: utilizar `recover_pending(Path(destino))` dentro de `destination_lock(Path(destino))`. Esta operación escribe solo el destino de continuación; no utilizar el original.
- Corrupción o copia inicial interrumpida: detenerse y conservar evidencia. No reconstruir claves ni reparar hashes manualmente. Una copia nueva del original validado exige otro destino y ejecución explícitos; no sobrescribir el destino fallido.
- Un bloqueo ocupado se rechaza inmediatamente. No reiniciar servicios, eliminar lockfiles ni terminar procesos ajenos; el bloqueo del directorio se libera al cerrar el descriptor o terminar el proceso.

## Pruebas offline y límites

Las pruebas usan únicamente fixtures sintéticos, incluyendo un prefijo de 44 lotes y 4.400 claves. No usan la captura privada como destino ni importan configuración HANA para ejecutar el capturador.

```bash
cd SrvRestAstroLS_v1/backend
UV_OFFLINE=1 uv run --no-sync pytest --import-mode=importlib -q \
  modules/telchi/investigation/validation/controlled_physical_capture_v1/test_capture.py \
  modules/telchi/datalake/tests/test_physical_reference_offline.py::test_identity_validation_rejects_duplicates_remaps_and_cross_source_merge \
  modules/telchi/datalake/tests/test_reference_update.py::test_duplicate_guard_rejects_source_keys \
  modules/telchi/datalake/tests/test_reference_update.py::test_canonical_id_is_deterministic_and_role_sensitive
```

Resultado offline: **50 PASS** (47 tests del capturador y 3 regresiones relacionadas), sin consultas SAP. La fixture de 4.400 filas continúa con 125 nuevas claves en cinco consultas; el prefijo permanece intacto y no hay duplicados ni solapamientos.

Las interrupciones se inyectan antes del lote, después de guardarlo y después del checkpoint. Se verifica idempotencia, prefijo intacto, primera clave exclusiva, presupuesto, pausas, errores, latencia, corrupción, sesiones y exclusión entre procesos.

Para no cargar el disco compartido, los tests sustituyen fsync y verifican por separado que el protocolo solicita flush de archivo y directorio. No simulan un corte eléctrico real ni certifican almacenamiento/driver HANA. Una consulta interrumpida antes de guardar un lote no puede garantizar exactamente una ejecución remota: solo se garantiza no repetir lotes confirmados.

La presión de I/O produjo dos timeouts iniciales (suite con flushes reales e intento de inventario completo del Data Lake); ambos se abandonaron sin defecto de integridad demostrado. La validación final usa pruebas acotadas y hashes de los dos manifests compartidos, no un scan completo del Data Lake.

Los cambios/altas/bajas del maestro entre sesiones y las diferencias de collation SQL/Python siguen siendo riesgos de consistencia: una infracción de orden se rechaza; no se infiere cobertura global ni ausencia de cambios anteriores a la última clave. No hay autorización de publicación ni validación online.
