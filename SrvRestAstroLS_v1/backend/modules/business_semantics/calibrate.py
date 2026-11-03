"""Read-only DEV pgvector measurement; no login, seeding, grants or threshold tuning."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import httpx
import psycopg
from psycopg.rows import dict_row

from modules.automation_diagnosis.litellm_client import LiteLLMClient
from modules.console.login_cli import read_config, checked_target
from .embeddings import EmbeddingConfiguration, LiteLLMEmbeddingAdapter
from .repository import BusinessConceptRepository, rows
from .resolver import VectorCandidatePolicy


async def measure(config_path, dataset_path):
    if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
        raise PermissionError('explicit_DEV_required')
    cfg = read_config(config_path)
    config = EmbeddingConfiguration.from_env()
    adapter = LiteLLMEmbeddingAdapter(config)
    client = LiteLLMClient()
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    for split in ('calibration', 'validation_holdout'):
        if len(dataset[split]) != 16:
            raise ValueError('expected_16_cases_per_split')
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        headers = {'Authorization': 'Bearer ' + client.api_key}
        info = await http.get(client.base_url.removesuffix('/v1')+'/model/info', headers=headers)
        info.raise_for_status()
        models = [m for m in info.json()['data'] if m.get('model_name') == config.alias]
        if len(models) != 1:
            raise ValueError('embedding_alias_not_unique')
        settings = await http.get(client.base_url.removesuffix('/v1')+'/router/settings', headers=headers)
        settings.raise_for_status()
        values = settings.json()['current_values']
        fallbacks = {k: values[k] for k in ('fallbacks', 'context_window_fallbacks', 'content_policy_fallbacks')}
        if any(fallbacks.values()):
            raise ValueError('fallback_not_allowed')
    await adapter.embed('Preflight pgvector DEV: definición empresarial.')
    # Freeze the existing provisional policy BEFORE either split. Holdout never tunes it.
    policy = VectorCandidatePolicy(0.4, 0.05, 'DEV-nine-concepts-evaluation')
    report = dict(dataset_sha256=hashlib.sha256(raw).hexdigest(), configuration=config.__dict__,
                  provider_model=models[0]['litellm_params']['model'], fallbacks=fallbacks,
                  preflight=adapter.last_usage, thresholds=policy.__dict__, thresholds_modified=False,
                  holdout_used_for_parameter_tuning=False, human_sessions_used=0, database_writes=0,
                  scope='retrieval_measurement_not_RBAC_or_business_response_certification', splits={})
    repo = BusinessConceptRepository()
    async with await psycopg.AsyncConnection.connect(cfg['runtime_dsn'], row_factory=dict_row,
            connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            await checked_target(conn, cfg['target'], runtime=True)
            report['effective_role'] = (await rows(conn, 'SELECT current_user AS role'))[0]['role']
            workspace = (await rows(conn, "SELECT id::text,organization_id::text FROM core_workspaces WHERE slug='telchi_dev'"))[0]
            catalog = await repo.catalog(conn, workspace['organization_id'], workspace['id'], 'telchi')
            index = {c['concept_id']: c for c in catalog}
            report['catalog'] = [{'code': c['semantic_code'], 'version': c['version']} for c in catalog]
            if not catalog:
                raise ValueError('published_catalog_required')
            for split in ('calibration', 'validation_holdout'):
                results = []
                for case in dataset[split]:
                    started = perf_counter()
                    vector = await adapter.embed(case['query'])
                    embedded = perf_counter()
                    hits = await repo.vector_search(conn, workspace['organization_id'], workspace['id'],
                                                    'telchi', vector, config, 3)
                    if len(hits) < 2:
                        raise ValueError('at_least_two_matching_embeddings_required')
                    margin = float(hits[0]['score']) - float(hits[1]['score'])
                    results.append(dict(case, hits=[dict(code=index[h['concept_id']]['semantic_code'], score=float(h['score'])) for h in hits],
                        margin=margin, candidate_eligible=float(hits[0]['score']) >= policy.minimum_score and margin >= policy.minimum_margin,
                        embedding_ms=(embedded-started)*1000, vector_ms=(perf_counter()-embedded)*1000,
                        usage=adapter.last_usage, auto_confirmed=False))
                report['splits'][split] = results
    report['executed_with_pgvector'] = True
    report['quality_gate'] = 'NOT_CERTIFIED: holdout has constraints, not expected concept IDs or response assertions'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-config', required=True, type=Path)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = asyncio.run(measure(args.auth_config, args.dataset))
    except Exception as exc:
        print('CALIBRATION_REJECTED: '+type(exc).__name__)
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print('PGVECTOR_MEASURED: 16 calibration + 16 holdout; no thresholds changed')


if __name__ == '__main__':
    main()
