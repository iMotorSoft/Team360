# Guia breve para el revisor de negocio

Esta guia acompana al paquete de revision del gold de Compound Intent. El revisor
es una persona del negocio que entiende que quiso pedir el usuario. **Pi no es el
revisor humano y no firma esta revision.**

## Que es este paquete

- 10 casos conocidos ya usados en la investigacion (8 controles simples + los 2
  casos de Abraham). **No** son holdout.
- Para cada caso: el mensaje original, el contexto conversacional anterior y los
  requisitos que el gold *propone* conservar.
- **No se muestran predicciones de ningun candidato.** Ni de Luna, ni de V1, ni
  de futuro V2. Esta decision es deliberada: el gold describe la intencion del
  usuario, no lo que un extractor supo responder.

## Que NO hay que hacer

- No abrir `rows.jsonl`, `evaluation.json` ni ninguna salida de modelo.
- No corregir el gold para que coincida con lo que "deberia" responder el sistema.
- No completar decisiones por aproximacion. Si no se entiende, se marca
  `INSUFFICIENT_CONTEXT` y se explica por que.

## Decisiones admitidas

| Decision | Significado |
| --- | --- |
| `ACCEPT` | El requisito propuesto refleja fielmente lo que pidio el usuario. |
| `CORRECT` | El requisito esta mal o incompleto. Completar `requisito_corregido` y `motivo`. |
| `AMBIGUOUS` | El mensaje admite mas de una lectura legitima. Explicar en `motivo`/`observaciones_caso`. |
| `INSUFFICIENT_CONTEXT` | Con el contexto disponible no se puede juzgar. Explicar en `motivo`/`observaciones_caso`. |

Una celda vacia significa "todavia no revisado".

## Que archivo completar

1. `pilot_cases.csv` — una fila por caso.
   - `decision_caso`: `ACCEPT`, `CORRECT`, `AMBIGUOUS` o `INSUFFICIENT_CONTEXT`.
   - `observaciones_caso`: obligatorio si la decision no es `ACCEPT`. Es tambien
     donde se registra la adjudicacion final si hubo desacuerdo o duda.
2. `pilot_requirements.csv` — una fila por requisito propuesto.
   - `decision_requisito`: la misma escala.
   - `requisito_corregido`: obligatorio si la decision es `CORRECT`.
   - `motivo`: obligatorio si la decision es `CORRECT`, `AMBIGUOUS` o
     `INSUFFICIENT_CONTEXT`.
3. `reviewer.json` — identidad y declaracion de independencia.
   - `is_implementation_author`: `false` solo si el revisor no diseno ni
     implemento el extractor.
   - `no_candidate_predictions_used`: `true` si reviso sin ver predicciones.

Guardar los CSV en formato CSV (UTF-8). No cambiar los nombres de las columnas
ni los identificadores (`turn_id`, `review_id`).

## Como se procesa la revision

```bash
uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.review_import \
  --review-dir ../../data/reports/telchi/compound_intent_v2_benchmark/review
```

La herramienta:

- valida que cada caso y requisito tenga fila y que las decisiones sean validas;
- exige justificacion/correccion en las decisiones no `ACCEPT`;
- rechaza cualquier referencia al holdout sellado;
- regenera `review_coverage.json`, `review_status.json` y `review_coverage.md`.

## Procedimiento posterior (corpus y holdout)

- El piloto se construye solo con el gold (`annotated_seed.json`). No lee
  `rows.jsonl` ni ninguna salida de candidato.
- Para extender a los 104 turnos LlmFit: dos anotadores reanotan por separado y
  un tercero adjudica los desacuerdos; cada lote registra `reviewer_id` y las
  correcciones aplicadas (trazabilidad de quien reviso que).
- El holdout de 20 turnos se anota bajo custodia separada: sus etiquetas no se
  mezclan con el corpus de calibracion, no se muestran a quien disena el
  extractor y se congelan antes de la evaluacion.
- Ningun revisor ve predicciones de V1, Luna o candidatos futuros.

## Requisitos objetivos para alcanzar `CERTIFIED`

1. Un revisor humano independiente del autor, declarado en `reviewer.json`.
2. Los 10 casos piloto completos a nivel de caso y de requisito.
3. Toda decision `CORRECT` con texto corregido; toda duda con `motivo`.
4. Sin adjudicaciones pendientes.
5. Los 104 turnos LlmFit reanotados, revisados y adjudicados con el mismo
   esquema (fuera del alcance de este piloto).
6. Las correcciones aplicadas al gold y el esquema revalidado con
   `gold_schema.validate_set`.
7. El holdout de 20 turnos revisado bajo custodia separada, sin contaminar la
   evaluacion.

El estado `CERTIFIED` no se concede automaticamente: mientras falte corpus o
adjudicacion, la herramienta reporta `PILOT_REVIEW_IN_PROGRESS` o
`PILOT_COMPLETE_CORPUS_PENDING` y `certified=false`.
