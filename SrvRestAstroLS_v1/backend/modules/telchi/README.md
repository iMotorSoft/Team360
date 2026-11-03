# Telchi

Telchi es un módulo de Team360. La autoridad sobre sus límites, ubicaciones y reglas vigentes es [`CONTEXT.md`](CONTEXT.md).

## Estado actual

El [estado local vigente](status_actual.md) distingue Foundation productiva, candidatos sin promoción y frontend en trabajo sin gate/deploy. Existe el módulo y su investigación consolidada; no se declara API/runtime productivo Telchi formal, `routes.py` ni scheduler. La foundation opt-in, sin ingesta real ni startup hook, está en [`RUNTIME_FOUNDATION.md`](RUNTIME_FOUNDATION.md).

El Data Lake Telchi V1 permanece cerrado (`TELCHI_DATALAKE_V1_CLOSED=YES`). Los párrafos siguientes conservan el cierre Receivables V3; su ID corresponde a aquella promoción, no a una lectura actual de CURRENT. El gate `TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V3_PASS` publicó de forma aditiva Receivables & Collections en foundation CURRENT `foundation_d222a203801cc84e9a14164d26aa67a0`, con 7 componentes lógicos y sin modificar los seis existentes.

La capacidad productiva soporta deuda abierta, current/overdue, aging, cierre histórico diario y cobranzas por cash, transfer, check y card, incluidos pagos con métodos mixtos. Reutiliza el componente sellado `receivables_collections_633d1fbbfdd87e6665b1aad3` (fingerprint `633d1fbbfdd87e6665b1aad39719f0c9bf5277ada1be6585ad09f900d65889ae`). Los intentos Foundation V1 y V2 fueron revertidos; V3 es el único resultado productivo. QR permanece `UNRESOLVED_SOURCE_EVIDENCE`, sin inferencia y sin bloquear Foundation.

Para la cohorte CG2A RAW_MATERIAL analizada, los 2.136 documentos tienen términos comerciales equivalentes a efectivo y due date igual a document date; 2.134 se liquidaron el mismo día, 2 después y ninguno quedó parcial o abierto al 2026-09-28. SAP/HANA no expone para este caso una operación de negocio nativa explícita llamada `CONTADO`: el Data Lake deriva la semántica comercial desde hechos financieros fuente y no la presenta como un campo nativo de SAP.

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
