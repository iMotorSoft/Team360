"""Build the human review package for the Compound Intent V2 gold.

This is material preparation only. It does not certify, does not implement V2 and
never shows candidate predictions. It emits a small, tabular, business-readable
pilot of the 10 known cases (8 simple controls + Abraham 001/002) plus the
decision sheets a human reviewer fills in.

Emit with (from ``SrvRestAstroLS_v1/backend``)::

    uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.review_package \\
      --output ../../data/reports/telchi/compound_intent_v2_benchmark/review

The sealed 20-turn holdout is never loaded into the package.
"""

import argparse
import json
from pathlib import Path

from . import review_contract as contract

GUIDE = """# Guia breve para el revisor de negocio

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
uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.review_import \\
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
"""


def _render_case_markdown(cases):
    lines = [
        '# Paquete piloto para revision humana',
        '',
        'Sin predicciones de candidatos. El gold describe la intencion del usuario.',
        'Holdout de 20 turnos sellado y fuera de este paquete.',
        '',
    ]
    for case in cases:
        lines += [
            '## ' + case['turn_id'] + ' - conversacion ' + case['conversation_id']
            + ', turno ' + str(case['turn_index']) + ' (' + case['group'] + ')',
            '',
            '- **Mensaje original:** ' + case['user_message'],
            '- **Contexto anterior:** ' + (contract.previous_message(case, cases) or '(sin turno previo)'),
            '- **Accion esperada:** ' + case['expected_action'],
            '- **Independencia actual:** ' + case['independence']['level'],
            '',
            '| review_id | categoria | procedencia | requisito propuesto | evidencia literal |',
            '| --- | --- | --- | --- | --- |',
        ]
        for req in case['requirements']:
            lines.append('| `' + req['req_id'] + '` | ' + req['category'] + ' | '
                         + req['provenance'] + ' | ' + contract.describe_requirement(req)
                         + ' | ' + (req.get('evidence', '') or '') + ' |')
        lines += ['', 'Notas del gold: ' + (case.get('notes', '') or '(ninguna)'), '']
    return '\n'.join(lines)


def _artifact_hashes(out_dir, names):
    return {name: contract.sha256_file(Path(out_dir) / name) for name in names}


def build_package(out_dir, seed_path=None, corpus_path=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = contract.pilot_cases(seed_path)
    corpus_ids = contract.corpus_turn_ids(corpus_path)

    case_rows = contract.build_case_rows(cases)
    req_rows = contract.build_requirement_rows(cases)

    contract.write_csv(out / 'pilot_cases.csv', contract.CASE_COLUMNS, case_rows)
    contract.write_csv(out / 'pilot_requirements.csv', contract.REQUIREMENT_COLUMNS, req_rows)
    (out / 'reviewer.json').write_text(
        json.dumps(contract.REVIEWER_TEMPLATE, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (out / 'pilot_review_guide.md').write_text(GUIDE, encoding='utf-8')
    (out / 'pilot_review.md').write_text(_render_case_markdown(cases), encoding='utf-8')

    report = contract.analyze(cases, case_rows, req_rows, contract.REVIEWER_TEMPLATE, corpus_ids)
    contract.write_reports(out, report)

    names = [
        'pilot_cases.csv', 'pilot_requirements.csv', 'reviewer.json',
        'pilot_review_guide.md', 'pilot_review.md', 'review_decisions.json',
        'review_coverage.json', 'review_status.json', 'review_coverage.md',
    ]
    source_files = [str(Path(seed_path) if seed_path else contract.DEFAULT_SEED)]
    if corpus_path:
        source_files.append(str(Path(corpus_path)))
    manifest = {
        'benchmark_version': contract.BENCHMARK_VERSION,
        'kind': 'HUMAN_REVIEW_PACKAGE',
        'pilot_cases': [case['turn_id'] for case in cases],
        'pilot_size': len(cases),
        'holdout_turn_ids_excluded': sorted(contract.holdout_ids()),
        'holdout_included_in_pilot': False,
        'candidate_predictions_included': False,
        'source_files_read': source_files,
        'artifact_sha256': _artifact_hashes(out, names),
        'artifact_sha256_note': 'Hashes captured right after generation; the decision sheets change once the reviewer fills them.',
        'status': report['coverage']['status'],
    }
    (out / 'review_package_manifest.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def main(args):
    manifest = build_package(args.output, seed_path=args.seed, corpus_path=args.corpus)
    print(json.dumps({
        'status': manifest['status'],
        'pilot_size': manifest['pilot_size'],
        'pilot_cases': manifest['pilot_cases'],
        'holdout_included_in_pilot': manifest['holdout_included_in_pilot'],
        'candidate_predictions_included': manifest['candidate_predictions_included'],
    }, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--seed', default=None)
    parser.add_argument('--corpus', default=None)
    main(parser.parse_args())