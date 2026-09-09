# Telchi Investigation

**THIS IS INVESTIGATION, NOT DEVELOPMENT OR PRODUCTION RUNTIME.** La autoridad del modelo `ENTITY → DOMAIN → STAGE → SOURCES / OUTPUTS / POLICIES`, la arquitectura y las ubicaciones es [`../CONTEXT.md`](../CONTEXT.md).

## Propósito

Este root contiene la investigación Telchi: reverse engineering, análisis y auditoría SAP, atomicidad, SQL experimental, validación, tests, gates, backtests, reconciliación, reglas descubiertas, inferencias experimentales, documentación y legacy parity.

No registra endpoints, routes, schedulers, frontend ni runtime productivo.

## Estructura actual

La estructura conserva responsabilidades de investigación sin anticipar capas productivas.

| PATH | PURPOSE |
| --- | --- |
| `atomic/` | Contratos, semántica y extractores atómicos de investigación |
| `sql/current/` | SQL HANA vigente y validado para investigación |
| `sql/legacy_hana2/` | SQL legacy preservado como baseline |
| `validation/` | Tests, gates, auditorías, backtests y reconciliaciones |
| `docs/` | Reportes y evidencia documental de análisis |
| `datalake/commercial_opportunities/` | Package Python histórico de investigación; no es el Data Lake físico |
| `LAT.md`, `DECISIONS.md`, `STATUS_ACTUAL.md` | Decisiones y estado histórico; `../CONTEXT.md` prevalece para arquitectura actual |

## Nueva investigación

No escribir nuevos scripts Telchi de investigación fuera de este root, salvo tooling operacional explícitamente autorizado.

Los scripts y módulos nuevos deben quedar junto al dominio de investigación correspondiente. Los gates y tests focalizados deben ubicarse en `validation/`, y la documentación analítica en `docs/` cuando no sea documentación operativa del root.

## SQL y validation

El SQL fuente de investigación vive bajo `sql/`; no debe copiarse al Data Root.

Toda semántica nueva debe conservar trazabilidad SAP, cardinalidad, reglas anti-fanout, tests focalizados y evidencia reproducible. Los gates no deben declarar PASS solo por conectividad o HTTP 200.

## HANA read-only

SAP Business One / HANA es la fuente operacional y se consulta `READ ONLY` por defecto.

Antes de ejecutar runners HANA se exige preflight y confirmación de `SAP_WRITE_COUNT=0`. La investigación puede consultar, auditar, reconciliar, validar, medir y extraer datasets aprobados, pero no modificar SAP.

## Datos, secretos y evidencia externa

El código Python, SQL fuente, tests y Markdown viven aquí; los datos y la configuración privada viven fuera de este root.

- Data Root físico: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`, exclusivamente `DATA ONLY`.
- Private Root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi`, exclusivamente configuración HANA/VPN y secretos fuera de Git.
- Legacy Root: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience`, consulta histórica read-only.
- Evidencia externa aprobada: debe escribirse en su evidence root, nunca confundirse con source versionado.

No desarrollar Python o SQL fuente en el Data Root, no almacenar Parquet pesado aquí y no copiar secretos dentro de la investigación.

## Ejecución conceptual

Los imports deben realizarse desde `SrvRestAstroLS_v1/backend` mediante `modules.telchi.investigation...` y usando los paths centralizados del módulo.

Cada ejecución debe resolver su output al destino autorizado, evitar defaults hacia el source tree y mantener SAP en modo read-only.

## Promotion rule

La promoción es `INVESTIGATION → DEVELOPMENT → PRODUCTION`; cada transición requiere intención y gate explícitos.

Development toma conocimiento validado y crea una implementación separada bajo `modules/telchi/`, fuera de `investigation/`. Debe tener semántica y contratos validados, tests suficientes, responsabilidad concreta, consumidor real e independencia de evidencia experimental.

Production habilita una capacidad Development ya validada; crear un endpoint no equivale a desplegarlo. El código Development o Production no debe importar runners de `investigation/`.

Investigation no se mueve ni se destruye: permanece como baseline, prueba, auditoría, evidencia semántica y regresión. Deudas bajo `CRÉDITO_Y_DEUDORES` es el ejemplo canónico detallado en [`../CONTEXT.md`](../CONTEXT.md).
