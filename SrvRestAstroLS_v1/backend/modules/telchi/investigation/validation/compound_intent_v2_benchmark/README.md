# Compound Intent V2 — Preparación de benchmark

**Autoridad de contexto:** [`../../CONTEXT.md`](../../CONTEXT.md). Este documento describe una entrega de `INVESTIGATION`; no declara promoción, no implementa V2 y no modifica runtime.

## Estado

`PROVISIONAL`.

El benchmark queda construido y reproducible, pero **no** se declara `BENCHMARK_READY` porque el gold no tiene revisión humana independiente. La anotación es `MODEL_ASSISTED_PROVISIONAL`; `gold_status=PROVISIONAL_GOLD`. El contrato de autorización de [`authorization.py`](authorization.py) rechaza explícitamente autorizar V2 mientras el gold no sea `CERTIFIED`.

## Propósito

V1 fue rechazada por el RCA. El RCA mostró que las 86 regresiones estructurales no equivalen a 86 errores semánticos nuevos y que el evaluador tenía dos definiciones de "exacto" (12 vs 10). Esta etapa entrega un contrato de medición defendible antes de implementar V2, sin volver a ejecutar un benchmark con LLM: sólo re-puntúa artefactos congelados de `compound_intent_v1/run01`.

## Qué incluye y qué no

Incluye:

- Esquema de gold con procedencia explícita y una guía de anotación.
- Conjunto anotado de 10 casos conocidos (8 controles simples + Abraham 001/002).
- Holdout sellado de 20 turnos nuevos en 5 conversaciones.
- Evaluador determinístico por capas con equivalencias de representación declaradas y tests.
- Resolución documentada de la inconsistencia 12/10.
- Métricas baseline recalculadas sobre criterios estables.
- Criterios objetivos para autorizar o rechazar la implementación de V2.

No incluye (por restricción explícita):

- Extractor V2 ni conexión al runtime.
- Nuevas llamadas LLM, SQL, Foundation, SAP, WhatsApp o servidores.
- Cambios en State Engine, permisos, catálogo o plan ejecutable.

## Contrato de medición

Cuatro capas se puntúan por separado y nunca se mezclan:

| Capa | Qué mide | `evaluate.py` |
| --- | --- | --- |
| `source_ledger` | preservación literal del mensaje original | `literal_preserved` |
| `request_extraction` | requisitos solicitados vs gold (raw y canónico) | `request_raw`, `request_canonical` |
| `accepted_state` | estado/acción aceptada vs gold | `accepted_state_exact` |
| `execution_eligibility` | allowed/blocked vs acción esperada | `eligibility` (TP/FP/FN/TN) |

Dentro de `request_extraction` se reportan predicados con nombre propio, nunca un "exacto" ambiguo:

| Predicado | Significado | Reemplaza a |
| --- | --- | --- |
| `RECALL_COMPLETE` | el candidato contiene todos los átomos del gold | — |
| `SET_EXACT` | sin faltantes y sin añadidos (universo completo de 16 campos) | predicado primario |
| `LEGACY_RECALL_FAMILY_EXACT` | reproduce `run.summarize` | 12 |
| `LEGACY_GOLD_KEYS_EXACT` | reproduce `evaluate.raw_score` | 10 |

La normalización de representación sólo aplica las equivalencias declaradas en [`canonicalize.py`](canonicalize.py): `end → end_exclusive`, `sort` dict→lista, `eq → in`, y OR de `eq` del mismo campo → un `in`. Cualquier otra diferencia se reporta como divergencia real.

## Resolución 12 vs 10

| Predicado | LlmFit exactos | Turnos que discrepan |
| --- | ---: | --- |
| `run.summarize` | 12 | `TCS_003_T02`, `TCS_020_T01` |
| `evaluate.raw_score` / detalle | 10 | los mismos |

Causa determinística: `run.summarize` filtra los átomos del candidato a las familias de campo donde el gold tiene al menos un átomo, por lo que los facet añadidos en familias vacías del gold son invisibles. `evaluate.raw_score` restringe por claves presentes en el gold, por lo que los facet añadidos en campos vacíos pero presentes sí cuentan. Ambos son respuestas a preguntas distintas: **12 = "no perdió requisitos"**, **10 = "no perdió ni inventó requisitos"**. El benchmark usa `SET_EXACT` (el criterio conservador) como primario y publica ambos.

## Métricas baseline recalculadas

Sobre `compound_intent_v1/run01` (104 turnos LlmFit), sin LLM ni runtime:

| Métrica | Baseline | V1 |
| --- | ---: | ---: |
| `SET_EXACT` raw (sin normalizar) | 96/104 | 6/104 |
| `SET_EXACT` canónico | 96/104 | 22/104 |
| `RECALL_COMPLETE` canónico | 96/104 | 74/104 |
| átomos preservados raw | 853/883 | 723/883 |
| átomos preservados end-key-only | 853/883 | 791/883 |
| átomos preservados canónico | 853/883 | 794/883 |

El salto `6 → 22` exactos y `723 → 794` átomos es recuperación por representación: 16 turnos pasan a `SET_EXACT` sólo al normalizar la representación. Las 77 regresiones canónicas restantes son divergencias que la representación no explica.

Estos números reconcilian con el RCA: `791/883` (end-key-only) y `723/883` (raw) son los diagnósticos publicados.

## Gold, independencia y holdout

- [`seed_gold.py`](seed_gold.py) anota los 10 casos conocidos de forma request-aware. Abraham 001/002 siguen siendo aceptación conocida, no holdout.
- [`holdout.py`](holdout.py) sella 20 turnos nuevos en 5 conversaciones con hashes por caso y agregado, y reglas de no contaminación.
- [`gold_schema.py`](gold_schema.py) mantiene separadas cuatro procedencias: `CURRENT_REQUEST`, `INHERITED_CONTEXT`, `USER_ASSERTED_UNVERIFIED`, `VERIFIED_EVIDENCE`. Ningún requisito existe sin evidencia literal y ninguna afirmación del usuario puede certificarse.
- `gold_status=PROVISIONAL_GOLD` porque `human_reviewed_cases=0`.

## Autorización de V2

[`authorization.py`](authorization.py) define las precondiciones duras y las compuertas de comportamiento. Sin gold `CERTIFIED` el resultado es `INSUFFICIENT_EVIDENCE`; con gold certificado, cualquier autorización nueva, bloqueo nuevo, regresión de medición, certificación de afirmaciones, llamada LLM extra o exceso de overhead produce `REJECT`. La especificación de diseño pasivo está en [`v2_passive_contract.md`](v2_passive_contract.md).

## Revisión humana (piloto)

La certificación no la produce un modelo. [`review_package.py`](review_package.py) prepara un paquete tabular para un revisor de negocio independiente y [`review_import.py`](review_import.py) importa sus decisiones y valida consistencia. Ninguno lee predicciones de candidatos ni incluye el holdout sellado; Pi no se declara revisor humano.

- `data/reports/telchi/compound_intent_v2_benchmark/review/pilot_cases.csv`: 10 casos conocidos, decisión por caso.
- `.../pilot_requirements.csv`: 26 requisitos propuestos, decisión por requisito.
- `.../pilot_review_guide.md`, `.../pilot_review.md`, `.../reviewer.json`.
- `.../review_coverage.md`, `.../review_status.json`: cobertura pendiente y criterios objetivos.

Decisiones admitidas: `ACCEPT`, `CORRECT`, `AMBIGUOUS` e `INSUFFICIENT_CONTEXT`. Toda decisión no `ACCEPT` exige observación o motivo; `CORRECT` exige texto corregido. `CERTIFIED` exige revisor humano independiente, piloto completo, correcciones adjudicadas, los 104 turnos LlmFit reanotados y revisados bajo el mismo esquema, y el holdout bajo custodia separada; una revisión incompleta nunca se convierte en `CERTIFIED`.

## Reproducción

Desde `SrvRestAstroLS_v1/backend`:

```bash
uv run pytest modules/telchi/investigation/validation/compound_intent_v2_benchmark -q
uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.recompute_baseline \
  --source ../../../data/reports/telchi/compound_intent_v1/run01 \
  --output ../../../data/reports/telchi/compound_intent_v2_benchmark
uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.holdout \
  --output ../../../data/reports/telchi/compound_intent_v2_benchmark
uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.seed_gold \
  --output ../../../data/reports/telchi/compound_intent_v2_benchmark
```

Evidencia generada en `data/reports/telchi/compound_intent_v2_benchmark/`.

## Límites

- No hay revisión humana independiente: el gold es provisional y no certifica generalización.
- Los números recalculados describen mecanismos estructurales observados, no efectos causales.
- `end-key-only` y canónico son diagnósticos del scorer, no salidas reparadas del candidato.
- La preservación de solicitudes en turnos ASK/BLOCK queda cubierta por el esquema, pero el corpus reanotado completo permanece pendiente de adjudicación.

## Próximo paso

El paquete piloto de revisión humana está preparado en `data/reports/telchi/compound_intent_v2_benchmark/review/`. El siguiente paso humano es revisar los 10 casos piloto, validar las instrucciones y luego reanotar/revisar el corpus LlmFit. Sólo entonces `gold_status` puede pasar a `CERTIFIED` y `authorization.py` puede evaluar una implementación pasiva de V2.