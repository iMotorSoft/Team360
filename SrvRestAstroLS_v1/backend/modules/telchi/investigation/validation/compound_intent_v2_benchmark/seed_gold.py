"""Request-aware re-annotation of the operational control turns.

Covers the 8 simple turns and the 2 Abraham acceptance cases. These are KNOWN
cases used during investigation, so they are NOT holdout: they calibrate the
benchmark and remain acceptance checks. Annotation is request-aware: a turn that
the legacy gold scored only by an accepted metric also records what was asked
even when it is not executable.

The legacy accepted metrics live in
``compound_intent_v1/run.py::SIMPLE`` and the Abraham frozen outputs. This module
does not import V1; it re-annotates from the original messages.

Emit with::

    uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.seed_gold \\
      --output ../../../data/reports/telchi/compound_intent_v2_benchmark
"""

import argparse
import hashlib
import json
from pathlib import Path

from . import gold_schema
from .case_builder import make_case, period as _period, relation as _relation


def _simple_specs():
    return [
        dict(turn_id='S01_1', conversation_id='S01', turn_index=1,
             user_message='Ventas de mayo de 2026',
             request={'metrics': ['sales.net_amount'],
                      'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-05-01', '2026-06-01')]}},
             requirements=[
                 ('S01_1.metric', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'Ventas'),
                 ('S01_1.time', 'temporal_periodicity', 'time', _period('2026-05-01', '2026-06-01'), 'CURRENT_REQUEST', 'mayo de 2026')],
             expected_action='EXECUTE'),
        dict(turn_id='S02_1', conversation_id='S02', turn_index=1,
             user_message='Dame las últimas 10 ventas registradas',
             request={'metrics': ['sales.latest_documents'], 'limit': 10},
             requirements=[
                 ('S02_1.metric', 'metric', 'metrics', 'sales.latest_documents', 'CURRENT_REQUEST', 'últimas 10 ventas'),
                 ('S02_1.limit', 'metric', 'limit', 10, 'CURRENT_REQUEST', '10')],
             expected_action='EXECUTE'),
        dict(turn_id='S03_1', conversation_id='S03', turn_index=1,
             user_message='¿Cuál es el último mes con ventas registradas?',
             request={'metrics': ['sales.coverage'], 'granularities': ['month'],
                      'unresolved_requirements': ['Mes más reciente con datos disponibles']},
             requirements=[
                 ('S03_1.metric', 'metric', 'metrics', 'sales.coverage', 'CURRENT_REQUEST', 'ventas registradas'),
                 ('S03_1.gran', 'temporal_periodicity', 'granularities', 'month', 'CURRENT_REQUEST', 'último mes'),
                 ('S03_1.ref', 'reference', 'unresolved_requirements', 'Mes más reciente con datos disponibles',
                  'CURRENT_REQUEST', 'último mes')],
             expected_action='EXECUTE'),
        dict(turn_id='S04_1', conversation_id='S04', turn_index=1,
             user_message='Buscá Citrato de magnesio',
             request={'metrics': ['products.search'],
                      'unresolved_requirements': ['Producto buscado: Citrato de magnesio']},
             requirements=[
                 ('S04_1.metric', 'metric', 'metrics', 'products.search', 'CURRENT_REQUEST', 'Buscá'),
                 ('S04_1.product', 'entity_product', 'unresolved_requirements', 'Producto buscado: Citrato de magnesio',
                  'CURRENT_REQUEST', 'Citrato de magnesio')],
             expected_action='EXECUTE'),
        dict(turn_id='S05_1', conversation_id='S05', turn_index=1,
             user_message='Ventas de mayo de 2026',
             request={'metrics': ['sales.net_amount'],
                      'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-05-01', '2026-06-01')]}},
             requirements=[
                 ('S05_1.metric', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'Ventas'),
                 ('S05_1.time', 'temporal_periodicity', 'time', _period('2026-05-01', '2026-06-01'), 'CURRENT_REQUEST', 'mayo de 2026')],
             expected_action='EXECUTE'),
        dict(turn_id='S05_2', conversation_id='S05', turn_index=2,
             user_message='¿Y el mes anterior?',
             request={'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-04-01', '2026-05-01')]}},
             requirements=[
                 ('S05_2.time', 'temporal_periodicity', 'time', _period('2026-04-01', '2026-05-01'),
                  'CURRENT_REQUEST', 'el mes anterior')],
             expected_action='EXECUTE',
             notes='Desplazamiento relativo de mes; conserva la métrica del turno previo.'),
        dict(turn_id='S06_1', conversation_id='S06', turn_index=1,
             user_message='Quiero importes y cantidades',
             request={'metrics': ['sales.net_amount', 'sales.source_top_items']},
             requirements=[
                 ('S06_1.importes', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'importes'),
                 ('S06_1.cantidades', 'metric', 'metrics', 'sales.source_top_items', 'CURRENT_REQUEST', 'cantidades')],
             expected_action='ASK',
             notes='Sin período todavía; no bloquea, pide el dato faltante.'),
        dict(turn_id='S06_2', conversation_id='S06', turn_index=2,
             user_message='mayo de 2026',
             request={'metrics': ['sales.net_amount', 'sales.source_top_items'],
                      'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [_period('2026-05-01', '2026-06-01')]}},
             requirements=[
                 ('S06_2.time', 'temporal_periodicity', 'time', _period('2026-05-01', '2026-06-01'), 'CURRENT_REQUEST', 'mayo de 2026'),
                 ('S06_2.inherited', 'metric', 'metrics', 'sales.net_amount', 'INHERITED_CONTEXT', 'importes', 'PROVISIONAL', 'S06_1')],
             expected_action='EXECUTE',
             notes='Completa el período pendiente conservando importes/cantidades.'),
    ]


def _abraham_specs():
    return [
        dict(turn_id='ABRAHAM_001', conversation_id='ABRAHAM_001', turn_index=1,
             user_message='¿Cuántos clientes tenemos en horizontal, principalmente las farmacias, y cuánto se les vende por mes?',
             request={'metrics': ['customer_count', 'sales.unspecified'],
                      'filters': [[{'field': 'sales_channel_id', 'op': 'eq', 'values': ['HORIZONTAL']}]],
                      'segments': ['farmacias'], 'granularities': ['month'],
                      'unresolved_requirements': ['Población: clientes registrados vs compradores del período']},
             requirements=[
                 ('ABRAHAM_001.customers', 'metric', 'metrics', 'customer_count', 'CURRENT_REQUEST', 'Cuántos clientes'),
                 ('ABRAHAM_001.sales', 'metric', 'metrics', 'sales.unspecified', 'CURRENT_REQUEST', 'cuánto se les vende'),
                 ('ABRAHAM_001.channel', 'segment_geography', 'filters', 'HORIZONTAL', 'CURRENT_REQUEST', 'horizontal'),
                 ('ABRAHAM_001.pharmacies', 'segment_geography', 'segments', 'farmacias', 'CURRENT_REQUEST', 'farmacias'),
                 ('ABRAHAM_001.monthly', 'temporal_periodicity', 'granularities', 'month', 'CURRENT_REQUEST', 'por mes'),
                 ('ABRAHAM_001.ambiguity', 'ambiguity', 'unresolved_requirements',
                  'Población: clientes registrados vs compradores del período', 'CURRENT_REQUEST', 'Cuántos clientes')],
             expected_action='ASK',
             notes='Ambigüedad de población; el canal horizontal es explícito.'),
        dict(turn_id='ABRAHAM_002', conversation_id='ABRAHAM_002', turn_index=1,
             user_message='Venta de Citrato de magnesio en la paz y cochabamba, en la paz distribucion propia y en conchabamba lo hace L&S',
             request={'geographies': ['La Paz', 'Cochabamba'],
                      'relations': [
                          _relation('propia', 'La Paz', 'en la paz distribucion propia', 'ABRAHAM_002'),
                          _relation('L&S', 'Cochabamba', 'en conchabamba lo hace L&S', 'ABRAHAM_002')]},
             requirements=[
                 ('ABRAHAM_002.geo_lp', 'segment_geography', 'geographies', 'La Paz', 'CURRENT_REQUEST', 'la paz'),
                 ('ABRAHAM_002.geo_cbba', 'segment_geography', 'geographies', 'Cochabamba', 'CURRENT_REQUEST', 'cochabamba'),
                 ('ABRAHAM_002.rel_lp', 'relation', 'relations',
                  _relation('propia', 'La Paz', 'en la paz distribucion propia', 'ABRAHAM_002'),
                  'USER_ASSERTED_UNVERIFIED', 'en la paz distribucion propia'),
                 ('ABRAHAM_002.rel_cbba', 'relation', 'relations',
                  _relation('L&S', 'Cochabamba', 'en conchabamba lo hace L&S', 'ABRAHAM_002'),
                  'USER_ASSERTED_UNVERIFIED', 'en conchabamba lo hace L&S')],
             expected_action='ASK',
             notes='Tuplas (producto, distribuidor, geografía) afirmadas por el usuario; nunca certificadas.'),
    ]


def build_cases():
    cases = []
    for spec in _simple_specs():
        cases.append(make_case(group='simple', **{k: v for k, v in spec.items() if k != 'notes'},
                               notes=spec.get('notes', '')))
    for spec in _abraham_specs():
        cases.append(make_case(group='abraham', **{k: v for k, v in spec.items() if k != 'notes'},
                               notes=spec.get('notes', '')))
    return cases


def seal(cases):
    messages = {c['turn_id']: c['user_message'] for c in cases}
    gold_schema.validate_set(cases, messages)
    per_case = [{'turn_id': c['turn_id'],
                 'sha256': hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
                for c in cases]
    manifest = {
        'benchmark_version': 'compound_intent_v2_benchmark/1',
        'kind': 'ANNOTATED_SEED_KNOWN_CASES',
        'prepared_date': '2026-10-15',
        'provenance': 'Request-aware re-annotation of known control turns; not derived from V1/Luna output.',
        'independence': gold_schema.independence_summary(cases),
        'turns': len(cases),
        'groups': sorted({c['group'] for c in cases}),
        'per_case_sha256': per_case,
        'known_acceptance_not_holdout': ['ABRAHAM_001', 'ABRAHAM_002'],
    }
    return cases, manifest


def main(args):
    cases, manifest = seal(build_cases())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'annotated_seed.json').write_text(json.dumps(
        {'benchmark_version': manifest['benchmark_version'], 'cases': cases}, indent=2, ensure_ascii=False) + '\n')
    (out / 'annotated_seed_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(manifest['independence'], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    main(parser.parse_args())