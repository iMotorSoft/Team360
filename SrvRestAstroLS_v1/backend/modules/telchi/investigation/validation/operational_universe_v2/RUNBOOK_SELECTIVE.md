# Extractor selectivo — ejecución futura

Procedimiento investigativo, no promoción. Esta fase acredita lógica offline; **ningún comando HANA de este documento está autorizado ni se ejecutó durante la implementación**.

## Contrato y origen

El plan inmutable conserva su etiqueta histórica offline; el transporte separado integra ahora su ejecución controlada sin regenerarlo ni ampliar identidades.

- Módulo: `modules.telchi.investigation.validation.operational_universe_v2.transport`.
- Fuente: [universo acreditado](../../../../../../../data/reports/telchi/operational-universe-v2-20261029-final/report.md).
- Plan: `data/reports/telchi/operational-universe-v2-20261029-final/selective_plan.json`.
- SHA-256 del archivo del plan: `fa8441322b141e7205b7639378cfc979350359f2a1c5b2b7d96ef05069e1285c`.
- SHA-256 del inventario fuente: `d08a8cf343cbf3e17d1a7878146e15f56807bd3b81dcb69f292c1e7af844d7fb`.
- 8.001 identidades únicas = 4.759 capturadas + 3.242 pendientes; 1.276 físicas explícitas; 43 sin Reference conservadas, sin fabricar identidad canónica.
- 130 lotes / 26 bloques. Primeros 129 lotes: 25 identidades; último: 17. Primer bloque: máximo 125 identidades. Restan 3.117 tras confirmarlo completo.
- `validate_origin()` verifica hashes de todos los artefactos, checkpoint histórico y filas capturadas, partición de identidades y procedencia. Discrepancia implica detenerse, nunca regenerar el plan para eludirla.

SQL único: `SELECT "ItemCode", "U_FormaFarmac" FROM "TELCHI"."OITM" WHERE "ItemCode" IN (?, …) ORDER BY "ItemCode"`. Solo varía el número de placeholders, de 1 a 25; valores vinculados, nunca concatenados. No SELECT adicional, COUNT, OFFSET, otras tablas ni barrido general.

## Preflight previo a nueva autorización

El owner debe autorizar explícitamente la microcaptura y su ventana. El flag de CLI documenta esa decisión; no la sustituye ni habilita por sí solo acceso SAP.

1. Confirmar rama `feature/console-backend-core`, scope exclusivo del destino y ausencia de otro capturador SAP. No limpiar Git ni cambiar VPN, credenciales, servicios o límites.
2. Evaluar host mediante `uptime`, `free -m`, `vmstat 1 3`, procesos sin argumentos secretos y espacio del destino. I/O global no mide sobrecarga HANA. Si no es seguro, `RESOURCE_BLOCKED`; no iniciar.
3. Confirmar VPN existente con el owner y rutas locales mediante `ip -brief link` / `ip route`; no levantar ni reconectar VPN. No realizar pruebas TCP, conexiones HANA o SELECT 1 fuera de la nueva autorización.
4. Desde `SrvRestAstroLS_v1/backend`, verificar adapter/configuración sin imprimir valores ni abrir conexiones:

```bash
uv run python - <<'PY'
from hdbcli import dbapi
from modules.telchi.datalake.source import hana_config
c = hana_config()
assert c['schema'] == 'TELCHI' and 'qmark' in dbapi.paramstyle
assert 1 <= int(c['port']) <= 65535
print('ADAPTER_CONFIG_VALIDATED_NO_CONNECTION')
PY
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.transport validate
```

5. Revisar configuración por el mecanismo privado normal; nunca copiar secretos al reporte. El adapter del capturador anterior aporta conexión configurada, autocommit y timeouts; no se introduce pool ni estrategia paralela. Primer SELECT autorizado sirve como prueba funcional, sin consulta preliminar adicional.
6. El runner verifica dispositivo físico del destino, capacidad, dos intervalos de presión y probe durable. Dispositivo desconocido, solo lectura, presión sostenida o persistencia lenta detienen el arranque. No desactivar el guard.

## Microcaptura real de un bloque

Comando preparado, **no ejecutado**. Requiere nueva autorización y destino inexistente; todos los datos quedan privados, fuera del Data Lake productivo.

Desde la raíz del repositorio:

```bash
cd SrvRestAstroLS_v1/backend
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.transport run \
  --destination /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-selective-phase3-20261029-micro-v1 \
  --max-blocks 1 --seconds 300 \
  --authorize-hana SELECTIVE_CAPTURE_EXPLICITLY_AUTHORIZED
```

No crear el destino manualmente. Si ya existe, detenerse e inspeccionarlo; no eliminarlo, sobrescribirlo ni elegir `--resume` por conveniencia. La creación usa directorio privado y fsync del padre.

## Controles y detención

Los límites son fijos y separados por subsistema; un resultado HTTP o una conexión exitosa no acredita la captura.

- Hasta 25 ItemCode/SELECT; hasta 5 SELECT/bloque. Una conexión activa, ejecución secuencial, sin threads, pools, paralelismo ni reintentos automáticos.
- Pausa mínima 10 s entre consultas; 30 s entre bloques. Reanudación: pausa conservadora de 30 s incluso dentro de un bloque.
- Consulta + fetch medidos: umbral HANA 1,5 s. Si excede, terminar persistencia válida y detener consultas nuevas. Nunca descartar una respuesta válida para repetirla.
- Driver: query timeout 3 s y connection/communication timeout heredados de 3.000 ms. Son límites cooperativos/granulares, **no garantía de cancelación física a 1,5 s**. No se abandonan threads para fingirlo.
- Persistencia de intent + journal + lote + checkpoint + verificación + reporte de sesión: presupuesto 10 s. Un fsync iniciado termina antes de evaluar el exceso; no se cancela. Preservar estado y detener nuevas consultas si excede.
- Presupuesto cooperativo: 300 s en los comandos, máximo admitido 1.800 s; reserva de cierre 60 s más driver 3 s y persistencia 10 s. Rechequeo tras pausas, preflight, conexión e intent. Harness externo, si existe, con al menos 2.400 s y sin kill prematuro.
- Enviar SIGINT una vez al proceso foreground (Ctrl-C) o SIGTERM solo a su PID verificado. Se termina la transacción en curso y se cierran cursor/conexión. No `kill -9`, killall, reinicios ni eliminación de temporales.
- Excepciones del adapter, errores de forma/orden/duplicados y claves ajenas detienen el proceso, sin retry. Mensajes de error del driver no se vuelcan a logs.

## Verificación posterior al primer bloque

Antes de continuar, validar datos y evidencia offline. La falta de una identidad en un fetch completo es terminal `NOT_RETURNED`, no NULL ni prueba de eliminación en SAP.

```bash
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.transport recover \
  --destination /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-selective-phase3-20261029-micro-v1
```

Exigir `completed=5`, `unresolved_request=false`, sin pending ni temporales sin resolver. Comparar los cinco lotes con los primeros cinco conjuntos solicitados; unión de filas y `not_returned` = 125 identidades, sin duplicados. El checkpoint referencia hashes de cada lote y vuelve a verificar su contenido.

Revisar `sessions/*.json`: `BLOCKS_COMPLETE`, cinco consultas, cinco cursores abiertos/cerrados, conexión cerrada, latencias ≤1,5 s, persistencia ≤10 s y hashes del checkpoint/plan. Separar errores del adapter, latencia HANA, presión del dispositivo y tiempo local. El runner comprueba que la captura histórica queda idéntica.

Conservar inventario SHA-256 del destino, sesiones, checkpoint, tiempos y resumen de presentes/no devueltos en un reporte nuevo bajo `data/reports/telchi/`; no publicar Reference/Foundation ni modificar CURRENT, Atomic o facts. Un microbloque `PARTIAL` o cierre no certificado requiere revisión, no continuación automática.

## Recuperación e incertidumbre

La recuperación lógica es idempotente sobre datos confirmados. La durabilidad física del equipo requiere el preflight real; los tests offline no simulan un corte de energía del hardware.

- A: interrupción antes del SELECT con intent durable bloquea por prudencia; puede no haber consulta física.
- B: resultados recibidos, antes del journal durable: resultado físico incierto. Puede ser necesario repetir **solo ese lote**, tras revisión explícita.
- C: journal parcial permanece bloqueado; escrituras parciales de lote/checkpoint se recuperan desde el journal completo, preservando bytes interrumpidos en `interrupted/`.
- D: journal temporal completo tras fsync se valida, re-fsync y adopta; el lote/checkpoint se reconstruyen sin SAP.
- E/F: journal guardado o checkpoint ya actualizado se concilian, verifican hashes y completan el protocolo sin reconsulta.
- G/H: bloque completo y lote durable pendiente se retoman desde el siguiente índice confirmado, nunca desde el inicio.
- I/J: cambio del plan/corrupción rechaza recuperación; el lock exclusivo del inode de directorio rechaza otro proceso.

`recover` nunca abre HANA. Si quedan request o temporales parciales sin journal recuperable, inspeccionar y preservar evidencia. No borrar archivos manualmente ni prometer exactamente una ejecución física.

Solo tras revisión humana documentada, el comando offline siguiente archiva intent/temporales y habilita una **posible repetición física posterior**; no consulta SAP. Sustituir el motivo por la decisión real:

```bash
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.transport review-uncertain \
  --destination /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-selective-phase3-20261029-micro-v1 \
  --reason 'REVISION_HUMANA: resultado físico incierto; repetición del lote no confirmado autorizada'
```

El review rechaza un journal completo recuperable y no altera lotes confirmados. Corrupción del checkpoint/lote o plan distinto requiere investigación, nunca review para saltar integridad. Conservar destinos incompletos; no copiar el ledger a otro destino para esquivar el lock.

## Continuación hasta 3.242 identidades

Después de acreditar el microbloque y obtener autorización para continuar, ejecutar un bloque por invocación, siempre sobre el mismo destino y plan verificados.

```bash
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.transport run \
  --destination /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-selective-phase3-20261029-micro-v1 \
  --resume --max-blocks 1 --seconds 300 \
  --authorize-hana SELECTIVE_CAPTURE_EXPLICITLY_AUTHORIZED
```

Repetir manualmente tras cada revisión posterior: 25 bloques adicionales si la microcaptura confirmó los primeros cinco lotes. No usar loop ciego ni retry automático. Cada reanudación valida todo el prefijo y solo ejecuta el próximo índice pendiente. Una ejecución completa posterior devuelve `COMPLETE`, cero consultas.

Final: `completed=130`, conjunto solicitado exacto de 3.242 identidades, último lote de 17; todas las identidades clasificadas como devueltas o `NOT_RETURNED`, hashes válidos y cero duplicados. No denominar captura íntegra de valores a las identidades no devueltas. Publicación al Data Lake queda fuera de esta autorización.

## Validación offline reproducible

La suite usa adapter simulado; los tests de almacenamiento sobre tmpfs acreditan protocolo lógico y llamadas fsync, no persistencia ante caída del equipo. No se omiten controles en el runner real.

```bash
uv run pytest --import-mode=importlib \
  --basetemp=/dev/shm/telchi-selective-phase3-NUEVA-CORRIDA \
  modules/telchi/investigation/validation/operational_universe_v2 \
  modules/telchi/investigation/validation/controlled_physical_capture_v1 \
  modules/telchi/investigation/validation/operational_products_offline_v1 \
  modules/telchi/datalake/tests/test_product_business_classification.py \
  modules/telchi/datalake/tests/test_physical_reference_offline.py \
  modules/telchi/datalake/tests/test_physical_reference_end_to_end.py \
  -k 'not real_sales_and_returns_exclude_canceled_documents' -q
```

Usar siempre un basetemp nuevo: pytest puede eliminar el directorio elegido. La exclusión evita el scan del catálogo/Foundation compartidos en este gate offline; no excluye reconciliación de artefactos ni transporte. LAT y `git diff --check` se ejecutan desde la raíz del repositorio.
