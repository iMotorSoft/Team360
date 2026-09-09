# Telchi

Telchi es un módulo de Team360. La autoridad sobre sus límites, ubicaciones y reglas vigentes es [`CONTEXT.md`](CONTEXT.md).

## Estado actual

Hoy existe el módulo y su árbol de investigación consolidado. No existe todavía una API o runtime productivo Telchi formal, `routes.py`, scheduler ni frontend.

Los gates de consolidación, registro Git, aislamiento del Data Root, migración de secretos y conexión post-migración están en PASS; SAP/HANA permanece read-only con `SAP_WRITE_COUNT=0`.

## Etapas y promoción

Telchi usa tres etapas consistentes: `INVESTIGATION → DEVELOPMENT → PRODUCTION`. Toda nueva investigación, auditoría, validación y SQL experimental vive en [`investigation/`](investigation/README.md).

Si Telchi está confirmado y no se pide construir o desplegar una capacidad de forma explícita, la etapa es `INVESTIGATION`. `DEVELOPMENT` crea una capacidad concreta bajo este módulo y fuera de `investigation/`; `PRODUCTION` requiere un gate posterior para habilitar una capacidad Development validada.

Investigation permanece como baseline, evidencia y regresión después de promover conocimiento. El código Development o Production no debe importar runners de investigación.

## Roots externos

Los roots externos separan datos físicos, configuración privada y fuentes legacy del software versionado. SAP/HANA y legacy son fuentes; Data Lake es infraestructura y puede ser source u output, no una etapa Telchi.

- Data Root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi` (`DATA ONLY`).
- Private Root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi` (`PRIVATE CONFIG ONLY`, fuera de Git).
- Legacy DS/DS0: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience` (fuente histórica externa, no apta para nuevo desarrollo).

## Trabajo de investigación

Antes de investigar, revisar [`CONTEXT.md`](CONTEXT.md), trabajar desde `SrvRestAstroLS_v1/backend` usando imports `modules.telchi.investigation...` y ejecutar el preflight correspondiente.

Si se consulta HANA, el modo es `READ ONLY` por defecto. El código y SQL fuente permanecen en `investigation/`; únicamente los datasets físicos aprobados van al Data Root y los secretos permanecen en el Private Root.
