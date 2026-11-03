"""Read-only pgvector counterexample probe; never impersonates a Console user."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import httpx

from modules.automation_diagnosis.litellm_client import LiteLLMClient
from .runtime_connection import RestrictedSemanticsConnection
from .repository import BusinessConceptRepository, rows
from .embeddings import EmbeddingConfiguration, LiteLLMEmbeddingAdapter
from .resolver import candidate_scope, VectorCandidatePolicy


async def run(args):
    baseline = json.loads(args.baseline.read_text())
    frozen_hash = hashlib.sha256(args.frozen_corpus.read_bytes()).hexdigest()
    if frozen_hash != baseline['dataset_sha256']:
        raise ValueError('frozen_corpus_changed')
    config = EmbeddingConfiguration(**baseline['configuration'])
    policy = VectorCandidatePolicy(**baseline['thresholds'])
    adapter = LiteLLMEmbeddingAdapter(config)
    client = LiteLLMClient()
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        headers = {'Authorization': 'Bearer '+client.api_key}
        response = await http.get(client.base_url.removesuffix('/v1')+'/model/info', headers=headers)
        response.raise_for_status()
        models = [m for m in response.json()['data'] if m.get('model_name') == config.alias]
        if len(models) != 1 or models[0]['litellm_params']['model'] != baseline['provider_model']:
            raise ValueError('upstream_changed')
        response = await http.get(client.base_url.removesuffix('/v1')+'/router/settings', headers=headers)
        response.raise_for_status()
        settings = response.json()['current_values']
        fallbacks = {k: settings[k] for k in ('fallbacks', 'context_window_fallbacks', 'content_policy_fallbacks')}
        if any(fallbacks.values()):
            raise ValueError('fallback_not_allowed')
    await adapter.embed('Preflight de compatibilidad de entidad y relación empresarial.')
    repo = BusinessConceptRepository()
    report = dict(configuration=config.__dict__, provider_model=baseline['provider_model'], fallbacks=fallbacks,
                  thresholds=policy.__dict__, thresholds_modified=False, frozen_corpus_sha256=frozen_hash,
                  independent_dataset_sha256=hashlib.sha256(args.independent.read_bytes()).hexdigest(),
                  database_writes=0, human_sessions_used=0, scope='retrieval_scope_not_authenticated_response_or_WhatsApp',
                  baseline_replay=[], independent=[])
    async with RestrictedSemanticsConnection(args.auth_config)() as conn:
        await conn.execute('SET TRANSACTION READ ONLY')
        report['effective_role'] = (await rows(conn, 'SELECT current_user AS role'))[0]['role']
        workspace = (await rows(conn, "SELECT id::text,organization_id::text FROM core_workspaces WHERE slug='telchi_dev'"))[0]
        catalog = await repo.catalog(conn, workspace['organization_id'], workspace['id'], 'telchi')
        by_id = {c['concept_id']: c for c in catalog}
        by_code = {c['semantic_code']: c for c in catalog}
        if sorted((c['semantic_code'], c['version']) for c in catalog) != sorted((c['code'], c['version']) for c in baseline['catalog']):
            raise ValueError('catalog_changed_requires_new_baseline')
        for split, cases in baseline['splits'].items():
            for case in cases:
                top = case['hits'][0]
                assessment = candidate_scope(by_code[top['code']], case['query'])
                report['baseline_replay'].append(dict(split=split, query=case['query'], top=top,
                    previously_eligible=case['candidate_eligible'], assessment=assessment,
                    eligible_after=case['candidate_eligible'] and assessment['decision'] == 'compatible'))
        for case in json.loads(args.independent.read_text())['cases']:
            vector = await adapter.embed(case['query'])
            hits = await repo.vector_search(conn, workspace['organization_id'], workspace['id'], 'telchi', vector, config, 3)
            text_hits = await repo.text_search(conn, workspace['organization_id'], workspace['id'], 'telchi', case['query'], 3)
            assessment = candidate_scope(by_code[case['code']], case['query'])
            numeric_eligible = len(hits) >= 2 and hits[0]['score'] >= policy.minimum_score and hits[0]['score']-hits[1]['score'] >= policy.minimum_margin
            actual_top = candidate_scope(by_id[hits[0]['concept_id']], case['query']) if hits else None
            eligible_after = bool(numeric_eligible and actual_top['decision'] == 'compatible')
            report['independent'].append(dict(case, target_assessment=assessment,
                assertion_passed=((assessment['decision'] == 'compatible') == case['compatible']
                                  and (case['compatible'] or not eligible_after)),
                hits=[dict(code=by_id[h['concept_id']]['semantic_code'], score=float(h['score']),
                           assessment=candidate_scope(by_id[h['concept_id']], case['query'])) for h in hits],
                text_hits=[dict(code=by_id[h['concept_id']]['semantic_code'], assessment=candidate_scope(by_id[h['concept_id']], case['query'])) for h in text_hits],
                numeric_eligible=bool(numeric_eligible), eligible_after=eligible_after))
        report['human_prerequisites'] = (await rows(conn, '''SELECT count(*) AS activated_password_credentials
            FROM console_password_credentials WHERE NOT disabled'''))[0]
    report['status'] = 'PASS' if all(r['assertion_passed'] for r in report['independent']) else 'FAIL'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('auth-config', 'baseline', 'frozen-corpus', 'independent', 'output'):
        p.add_argument('--'+name, required=True, type=Path)
    args = p.parse_args()
    try:
        report = asyncio.run(run(args))
    except Exception as exc:
        print('BOUNDARY_PROBE_REJECTED: '+type(exc).__name__)
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print('BOUNDARY_PROBE='+report['status'])
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
