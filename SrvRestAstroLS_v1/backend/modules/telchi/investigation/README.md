# Telchi Investigation

Este árbol preserva investigación, auditoría, experimentación y evidencia reproducible de Telchi con una estructura reconocible respecto del workspace original.

## Propósito

Aquí viven reverse engineering SAP, SQL, contratos descubiertos, semántica, reglas, validadores, tests, backtests, gates, reconciliaciones, documentación y runners HANA de solo lectura.

**NOT PRODUCTION API.** Este package no registra endpoints, schedulers, frontend ni runtime productivo.

## Estructura preservada

La consolidación mantiene `atomic/`, `sql/`, `validation/`, `docs/` y `datalake/commercial_opportunities/`. No distribuye todavía la lógica entre `domain/`, `services/`, `inference/` o adapters productivos.

## Límites externos temporales

El código Python y SQL se resuelven desde este package. Los secretos continúan en el secret root legado aprobado; los datos físicos y la evidencia continúan fuera de Git. `paths.py` hace explícita esa separación temporal sin copiar datos al package.

La evidencia del gate de consolidación se preserva externamente en `ai/evidence/telchi/investigation-consolidation-v1/`, con clasificación y SHA-256. El safety snapshot está en `ai/backups/telchi-safety-20260902-investigation-consolidation-v1/`.

## Ejecución segura

Los imports deben realizarse desde el root de `SrvRestAstroLS_v1/backend`, por ejemplo con `modules.telchi.investigation...`. Los runners HANA conservan intención READ ONLY; no deben ejecutarse sin preflight y verificación de `SAP_WRITE_COUNT=0`.

Los generadores de JSON deben dirigir sus outputs a un evidence root externo antes de usarse de forma habitual. Los artefactos JSON históricos no se versionaron en este package y están preservados en el evidence root.

## Regla de promoción Investigation → Productive

Una capacidad solo puede salir de `investigation/` mediante promoción explícita cuando cumple todos estos criterios:

1. semántica cerrada;
2. atomicidad validada;
3. gate PASS;
4. contratos definidos;
5. tests suficientes;
6. responsabilidad productiva concreta;
7. servicio, endpoint o consumidor real definido;
8. independencia de evidence de investigación;
9. performance adecuada;
10. lineage preservado.

El código productivo no puede importar runners de `investigation/`. La investigación permanece como baseline histórico y regresión reproducible después de cada promoción.

## Próximo gate

`TELCHI_DATA_ROOT_ISOLATION_V1` podrá preparar el Data Root físico con `raw/`, `staging/`, `atomic/`, `business/`, `decision/`, `snapshots/` y `manifests/`, sin borrar el source original antes de verificar esta consolidación.
