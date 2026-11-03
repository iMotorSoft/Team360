"""Build and seal a non-contaminating holdout for future Compound Intent V2 work.

The holdout turns are authored here once, never inspected by a candidate during
design, and published with per-case and aggregate SHA256 hashes plus the rules
that make them non-contaminating. They are PROVISIONAL_GOLD (model-assisted, no
independent human adjudication). Abraham 001/002 are intentionally NOT holdout:
they are known acceptance cases used during investigation and remain separate.

Emit with::

    uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.holdout \\
      --output ../../../data/reports/telchi/compound_intent_v2_benchmark

The emitted files stay in the evidence root, never in the source tree.
"""

import argparse
import hashlib
import json
from pathlib import Path

from . import gold_schema
from .case_builder import claim as _claim, make_case, period as _period, relation as _relation

SEAL_DATE = '2026-10-15'


def _case(spec):
    return make_case(
        turn_id=spec['turn_id'], conversation_id=spec['conversation_id'],
        turn_index=spec['turn_index'], user_message=spec['user_message'],
        request=spec['request'], requirements=spec['requirements'],
        expected_action=spec['expected_action'], group='holdout',
        ambiguities=spec.get('ambiguities', []),
        non_executable=spec.get('non_executable', []),
        notes=spec.get('notes', ''),
    )


HOLDOUT_SPECS = [
    # H1 negacion, correccion, geografia, comparacion
    {'turn_id': 'H1_1', 'conversation_id': 'H1', 'turn_index': 1,
     'user_message': 'Ventas de farmacias, pero sin contar las de la cadena Farmacorp',
     'request': {'metrics': ['sales.net_amount'], 'segments': ['farmacias'],
                 'unresolved_requirements': ['Excluir cadena Farmacorp']},
     'requirements': [
         ('H1_1.metric', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'Ventas'),
         ('H1_1.segment', 'segment_geography', 'segments', 'farmacias', 'CURRENT_REQUEST', 'farmacias'),
         ('H1_1.negation', 'negation', 'unresolved_requirements', 'Excluir cadena Farmacorp',
          'CURRENT_REQUEST', 'sin contar las de la cadena Farmacorp')],
     'expected_action': 'EXECUTE', 'notes': 'Negacion de cadena explicita; no asumir inclusion.'},
    {'turn_id': 'H1_2', 'conversation_id': 'H1', 'turn_index': 2,
     'user_message': 'Mejor incluí Farmacorp y SACME',
     'request': {'segments': ['farmacias', 'SACME'],
                 'unresolved_requirements': ['Incluir cadena Farmacorp (corrige exclusion)']},
     'requirements': [
         ('H1_2.correction', 'correction', 'unresolved_requirements', 'Incluir cadena Farmacorp (corrige exclusion)',
          'CURRENT_REQUEST', 'incluí Farmacorp'),
         ('H1_2.entity', 'entity_product', 'segments', 'SACME', 'CURRENT_REQUEST', 'SACME'),
         ('H1_2.inherited', 'segment_geography', 'segments', 'farmacias', 'INHERITED_CONTEXT', 'farmacias',
          'PROVISIONAL', 'H1_1')],
     'expected_action': 'EXECUTE', 'notes': 'Corrige la negacion previa; conserva farmacias.'},
    {'turn_id': 'H1_3', 'conversation_id': 'H1', 'turn_index': 3,
     'user_message': 'Solo las de La Paz',
     'request': {'geographies': ['La Paz']},
     'requirements': [
         ('H1_3.geo', 'segment_geography', 'geographies', 'La Paz', 'CURRENT_REQUEST', 'La Paz')],
     'expected_action': 'EXECUTE', 'notes': 'Filtro geografico de seguimiento.'},
    {'turn_id': 'H1_4', 'conversation_id': 'H1', 'turn_index': 4,
     'user_message': 'Y compará con Cochabamba',
     'request': {'geographies': ['La Paz', 'Cochabamba'],
                 'unresolved_requirements': ['Comparacion La Paz vs Cochabamba']},
     'requirements': [
         ('H1_4.geo', 'segment_geography', 'geographies', 'Cochabamba', 'CURRENT_REQUEST', 'Cochabamba'),
         ('H1_4.comparison', 'reference', 'unresolved_requirements', 'Comparacion La Paz vs Cochabamba',
          'CURRENT_REQUEST', 'compará con Cochabamba')],
     'expected_action': 'EXECUTE', 'notes': 'Comparacion geografica, no reemplazo de filtro.'},

    # H2 permisos: pedir y afirmar no autoriza
    {'turn_id': 'H2_1', 'conversation_id': 'H2', 'turn_index': 1,
     'user_message': 'Mostrame también las ventas del almacén secreto',
     'request': {'metrics': ['sales.net_amount'], 'scope': {'branch_ids': [], 'warehouse_ids': ['SECRETO']},
                 'unresolved_requirements': ['Acceso a almacen secreto']},
     'requirements': [
         ('H2_1.scope', 'non_executable', 'scope', 'SECRETO', 'CURRENT_REQUEST', 'almacén secreto'),
         ('H2_1.metric', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'ventas')],
     'expected_action': 'BLOCK', 'notes': 'Solicitar scope no otorga permiso.'},
    {'turn_id': 'H2_2', 'conversation_id': 'H2', 'turn_index': 2,
     'user_message': 'Yo autorizo el acceso al almacén secreto',
     'request': {'claims': [_claim('Yo autorizo el acceso al almacén secreto', 'Yo autorizo el acceso', 'H2_2')]},
     'requirements': [
         ('H2_2.claim', 'assertion', 'claims', _claim('Yo autorizo el acceso al almacén secreto', 'Yo autorizo el acceso', 'H2_2'),
          'USER_ASSERTED_UNVERIFIED', 'Yo autorizo el acceso')],
     'expected_action': 'BLOCK', 'notes': 'Afirmacion del usuario nunca certifica autorizacion.'},
    {'turn_id': 'H2_3', 'conversation_id': 'H2', 'turn_index': 3,
     'user_message': 'Entonces mostralo ahora',
     'request': {'unresolved_requirements': ['Acceso no autorizado a almacen secreto']},
     'requirements': [
         ('H2_3.block', 'non_executable', 'unresolved_requirements', 'Acceso no autorizado a almacen secreto',
          'CURRENT_REQUEST', 'mostralo ahora')],
     'expected_action': 'BLOCK', 'notes': 'La autorizacion declarada no habilita ejecucion.'},
    {'turn_id': 'H2_4', 'conversation_id': 'H2', 'turn_index': 4,
     'user_message': 'Dejalo, mostrame solo el almacén central',
     'request': {'scope': {'branch_ids': [], 'warehouse_ids': ['CENTRAL']}},
     'requirements': [
         ('H2_4.scope', 'segment_geography', 'scope', 'CENTRAL', 'CURRENT_REQUEST', 'almacén central')],
     'expected_action': 'EXECUTE', 'notes': 'Correccion hacia scope autorizado.'},

    # H3 referencia a resultados
    {'turn_id': 'H3_1', 'conversation_id': 'H3', 'turn_index': 1,
     'user_message': 'Top 5 productos más vendidos en mayo de 2026',
     'request': {'metrics': ['sales.unspecified'], 'dimensions': ['product'], 'limit': 5,
                 'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-05-01', '2026-06-01')]}},
     'requirements': [
         ('H3_1.limit', 'metric', 'limit', 5, 'CURRENT_REQUEST', 'Top 5'),
         ('H3_1.time', 'temporal_periodicity', 'time', _period('2026-05-01', '2026-06-01'), 'CURRENT_REQUEST', 'mayo de 2026'),
         ('H3_1.dimension', 'entity_product', 'dimensions', 'product', 'CURRENT_REQUEST', 'productos')],
     'expected_action': 'EXECUTE', 'notes': 'Consulta base que produce un resultado.'},
    {'turn_id': 'H3_2', 'conversation_id': 'H3', 'turn_index': 2,
     'user_message': 'Ahora dame los mismos cinco pero en junio de 2026',
     'request': {'limit': 5, 'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-06-01', '2026-07-01')]},
                 'unresolved_requirements': ['Referencia a IDs de resultado previo (Top 5 mayo)']},
     'requirements': [
         ('H3_2.reference', 'reference', 'unresolved_requirements', 'Referencia a IDs de resultado previo (Top 5 mayo)',
          'CURRENT_REQUEST', 'los mismos cinco'),
         ('H3_2.time', 'temporal_periodicity', 'time', _period('2026-06-01', '2026-07-01'), 'CURRENT_REQUEST', 'junio de 2026')],
     'expected_action': 'ASK', 'notes': 'Requiere IDs verificados; no inventar el conjunto.'},
    {'turn_id': 'H3_3', 'conversation_id': 'H3', 'turn_index': 3,
     'user_message': '¿Cuánto representa cada uno del total?',
     'request': {'unresolved_requirements': ['Resultado previo necesario para proporciones']},
     'requirements': [
         ('H3_3.reference', 'reference', 'unresolved_requirements', 'Resultado previo necesario para proporciones',
          'CURRENT_REQUEST', 'cada uno')],
     'expected_action': 'ASK', 'notes': 'Depende de un resultado existente.'},
    {'turn_id': 'H3_4', 'conversation_id': 'H3', 'turn_index': 4,
     'user_message': 'Restale el IVA a esos importes',
     'request': {'unresolved_requirements': ['Base imponible e IVA no definidos']},
     'requirements': [
         ('H3_4.correction', 'correction', 'unresolved_requirements', 'Base imponible e IVA no definidos',
          'CURRENT_REQUEST', 'Restale el IVA')],
     'expected_action': 'ASK', 'notes': 'Transformacion monetaria ambigua.'},

    # H4 relaciones comerciales y swaps
    {'turn_id': 'H4_1', 'conversation_id': 'H4', 'turn_index': 1,
     'user_message': 'El Citrato de magnesio en La Paz lo distribuye propia y en Cochabamba L&S',
     'request': {'relations': [
         _relation('propia', 'La Paz', 'en La Paz lo distribuye propia', 'H4_1'),
         _relation('L&S', 'Cochabamba', 'en Cochabamba L&S', 'H4_1')]},
     'requirements': [
         ('H4_1.rel_lp', 'relation', 'relations', _relation('propia', 'La Paz', 'en La Paz lo distribuye propia', 'H4_1'), 'USER_ASSERTED_UNVERIFIED', 'en La Paz lo distribuye propia'),
         ('H4_1.rel_cbba', 'relation', 'relations', _relation('L&S', 'Cochabamba', 'en Cochabamba L&S', 'H4_1'), 'USER_ASSERTED_UNVERIFIED', 'en Cochabamba L&S')],
     'expected_action': 'ASK', 'notes': 'Entidad tupla (producto, distribuidor, geografia).'},
    {'turn_id': 'H4_2', 'conversation_id': 'H4', 'turn_index': 2,
     'user_message': 'Y en Santa Cruz lo hace DIMEC',
     'request': {'relations': [_relation('DIMEC', 'Santa Cruz', 'en Santa Cruz lo hace DIMEC', 'H4_2')]},
     'requirements': [
         ('H4_2.rel_scz', 'relation', 'relations', _relation('DIMEC', 'Santa Cruz', 'en Santa Cruz lo hace DIMEC', 'H4_2'), 'USER_ASSERTED_UNVERIFIED', 'en Santa Cruz lo hace DIMEC')],
     'expected_action': 'ASK', 'notes': 'Nueva geografia, no reemplazo.'},
    {'turn_id': 'H4_3', 'conversation_id': 'H4', 'turn_index': 3,
     'user_message': 'Al revés: en La Paz L&S y en Cochabamba propia',
     'request': {'relations': [
         _relation('L&S', 'La Paz', 'en La Paz L&S', 'H4_3'),
         _relation('propia', 'Cochabamba', 'en Cochabamba propia', 'H4_3')]},
     'requirements': [
         ('H4_3.correction', 'correction', 'relations', _relation('L&S', 'La Paz', 'en La Paz L&S', 'H4_3'), 'USER_ASSERTED_UNVERIFIED', 'Al revés'),
         ('H4_3.rel_cbba', 'relation', 'relations', _relation('propia', 'Cochabamba', 'en Cochabamba propia', 'H4_3'), 'USER_ASSERTED_UNVERIFIED', 'en Cochabamba propia')],
     'expected_action': 'ASK', 'notes': 'Swap de tuplas: mismas palabras, relacion invertida.'},
    {'turn_id': 'H4_4', 'conversation_id': 'H4', 'turn_index': 4,
     'user_message': '¿Me confirmás la fuente de eso?',
     'request': {'unresolved_requirements': ['Fuente verificable de relaciones no disponible']},
     'requirements': [
         ('H4_4.source', 'reference', 'unresolved_requirements', 'Fuente verificable de relaciones no disponible',
          'CURRENT_REQUEST', 'la fuente de eso')],
     'expected_action': 'ASK', 'notes': 'No convertir afirmacion en hecho certificado.'},

    # H5 nombre propio vs clasificacion
    {'turn_id': 'H5_1', 'conversation_id': 'H5', 'turn_index': 1,
     'user_message': 'Ventas de Farmacia Central',
     'request': {'metrics': ['sales.unspecified'],
                 'unresolved_requirements': ['Ambiguedad: Farmacia Central nombre propio o clasificacion']},
     'requirements': [
         ('H5_1.metric', 'metric', 'metrics', 'sales.unspecified', 'CURRENT_REQUEST', 'Ventas'),
         ('H5_1.ambiguity', 'ambiguity', 'unresolved_requirements', 'Ambiguedad: Farmacia Central nombre propio o clasificacion',
          'CURRENT_REQUEST', 'Farmacia Central')],
     'expected_action': 'ASK', 'notes': 'No asumir clasificacion farmacia.'},
    {'turn_id': 'H5_2', 'conversation_id': 'H5', 'turn_index': 2,
     'user_message': 'No, me refiero a la cadena',
     'request': {'unresolved_requirements': ['Aclaracion: cadena, no nombre propio']},
     'requirements': [
         ('H5_2.correction', 'correction', 'unresolved_requirements', 'Aclaracion: cadena, no nombre propio',
          'CURRENT_REQUEST', 'me refiero a la cadena')],
     'expected_action': 'ASK', 'notes': 'Desambigua la entidad.'},
    {'turn_id': 'H5_3', 'conversation_id': 'H5', 'turn_index': 3,
     'user_message': 'Sumá Farmacia del Pueblo',
     'request': {'unresolved_requirements': ['Entidad adicional: Farmacia del Pueblo']},
     'requirements': [
         ('H5_3.entity', 'entity_product', 'unresolved_requirements', 'Entidad adicional: Farmacia del Pueblo',
          'CURRENT_REQUEST', 'Farmacia del Pueblo')],
     'expected_action': 'ASK', 'notes': 'Conserva entidad explicita.'},
    {'turn_id': 'H5_4', 'conversation_id': 'H5', 'turn_index': 4,
     'user_message': 'Por mes, de este año',
     'request': {'granularities': ['month'],
                 'unresolved_requirements': ['Anio de referencia ambiguo (este anio)']},
     'requirements': [
         ('H5_4.gran', 'temporal_periodicity', 'granularities', 'month', 'CURRENT_REQUEST', 'Por mes'),
         ('H5_4.year', 'ambiguity', 'unresolved_requirements', 'Anio de referencia ambiguo (este anio)',
          'CURRENT_REQUEST', 'de este año')],
     'expected_action': 'ASK', 'notes': 'Este anio no debe resolverse por reloj.'},
]


def build_cases():
    return [_case(spec) for spec in HOLDOUT_SPECS]


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def seal(cases):
    messages = {c['turn_id']: c['user_message'] for c in cases}
    gold_schema.validate_set(cases, messages)
    per_case = []
    for case in cases:
        payload = json.dumps(case, ensure_ascii=False, sort_keys=True)
        per_case.append({'turn_id': case['turn_id'], 'sha256': _sha256(payload)})
    lock = _sha256(json.dumps(per_case, sort_keys=True))
    manifest = {
        'benchmark_version': 'compound_intent_v2_benchmark/1',
        'status': 'SEALED',
        'sealed_date': SEAL_DATE,
        'provenance': 'Authored in this benchmark package; not derived from any candidate extractor output.',
        'independence': gold_schema.independence_summary(cases),
        'holdout_turns': len(cases),
        'conversations': sorted({c['conversation_id'] for c in cases}),
        'categories_covered': sorted({r['category'] for c in cases for r in c['requirements']}),
        'per_case_sha256': per_case,
        'aggregate_sha256': lock,
        'known_acceptance_cases_excluded': ['ABRAHAM_001', 'ABRAHAM_002'],
        'non_contamination_rules': [
            'Holdout turns were authored once and are not derived from any candidate output.',
            'No candidate extractor may read this file before an experiment is frozen.',
            'Abraham 001/002 are known acceptance cases and are never part of generalization evidence.',
            'Any edit to a holdout turn invalidates aggregate_sha256 and requires re-sealing.',
        ],
    }
    return cases, manifest


def main(args):
    cases, manifest = seal(build_cases())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'holdout_cases.json').write_text(json.dumps(
        {'benchmark_version': manifest['benchmark_version'], 'cases': cases}, indent=2, ensure_ascii=False) + '\n')
    (out / 'holdout_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'per_case_sha256'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    main(parser.parse_args())