"""Independent acceptance control, never imported by the runtime investigator.

Checks customer set difference using purchase-row counts, not model monetary
HAVING clauses, grouping customers across all matching 25kg presentations.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool

from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
from modules.telchi.console_http import AccreditedReader
from modules.telchi.exploratory_sql.authorized_foundation import (
    EffectiveScope, SourcePolicy, AuthorizedFoundationExecutor, open_binding)
from modules.telchi.exploratory_sql.console_repository import ResearchConsoleRepository
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.exploratory_sql.foundation_dev import proposal
from .prepare import ORG, WORKSPACE, write_new


def delivered_customers(report, column):
    # A verified different cell in the same row is not proof of customer delivery.
    verified = {(c['claim']['result_id'], c['claim']['row_id'], c['claim']['column_id'])
                for c in report['claim_verifications'] if c['match']}
    delivered = set()
    for turn in report['turns']:
        observation = turn.get('model_observation', {})
        manifest = observation.get('evidence_manifest')
        if not manifest:
            continue
        names = [c['name'] for c in turn['result']['schema']]
        if column not in names:
            continue
        index = names.index(column)
        column_id = manifest['columns'][index]['column_id']
        delivered.update(row[index] for row_id, row in zip(manifest['row_ids'], observation['rows'])
                         if (manifest['result_id'], row_id, column_id) in verified)
    return delivered


def compare_customers(report, rows):
    # Independent counts define presence, never model monetary HAVING clauses.
    september = {r[0] for r in rows if str(r[2]).startswith('2026-09') and int(r[3]) > 0}
    october = {r[0] for r in rows if str(r[2]).startswith('2026-10') and int(r[3]) > 0}
    expected = october - september
    codes = delivered_customers(report, 'card_code')
    if codes:
        return expected, codes, 'card_code'
    by_name = {}
    for code, name, _, _ in rows:
        by_name.setdefault(name, set()).add(code)
    names = delivered_customers(report, 'customer_name')
    # Names must be unambiguous across the entire independently read population.
    if any(len(by_name.get(name, set())) != 1 for name in names):
        return expected, set(), 'ambiguous_or_unknown_customer_name'
    return expected, {next(iter(by_name[name])) for name in names}, 'customer_name_unique_mapping'


async def verify(candidate, evidence):
    config = json.loads(candidate.read_text())
    report = json.loads(evidence.read_text())
    assert config['state'] == 'READY_NOT_ACTIVE'
    assert (config['organization'], config['workspace']) == (ORG, WORKSPACE)
    assert host_read_preflight()['safe'], 'RESOURCE_BLOCKED'
    started = time.monotonic()
    async with AsyncConnectionPool(get_database_settings().dsn, min_size=1, max_size=2,
                                   open=False, kwargs={'connect_timeout': 5}) as pool:
        await pool.wait(timeout=10)
        identities, permissions = ResearchConsoleRepository(), PermissionConsoleRepository()

        async def resolve():
            async with pool.connection() as conn:
                async with conn.transaction():
                    row = await identities.identity(conn, config['user_id'])
                    assert row and (row['organization'], row['workspace']) == (ORG, WORKSPACE)
                    effective = await permissions.list_effective_permissions(conn, WORKSPACE, config['user_id'])
                    enabled = await identities.enabled_permissions(conn, WORKSPACE)
                    return EffectiveScope(config['user_id'], ORG, WORKSPACE, frozenset(effective) & enabled)

        loop = asyncio.get_running_loop()

        def control():
            def fresh_scope():
                return asyncio.run_coroutine_threadsafe(resolve(), loop).result(timeout=10)
            reader = AccreditedReader(config['foundation_publication_id'])
            binding, _ = open_binding(reader=reader, resolve_scope=fresh_scope,
                policies=tuple(SourcePolicy(**p) for p in config['policies']), investigation_id=str(uuid4()))
            try:
                assert binding.context.publication == report['publication']
                assert binding.context.snapshot == report['snapshot']
                audit = []
                with AuthorizedFoundationExecutor(binding.context, reader=reader, authorized=True) as executor:
                    def query(sql, source):
                        decision, result = executor.execute(proposal(sql, source), binding.context)
                        assert decision.decision.value == 'ALLOW' and result.status == 'COMPLETED'
                        assert not result.truncated
                        audit.append(dict(sql=sql, returned_rows=result.returned_count,
                                          publication=result.publication, snapshot=result.snapshot))
                        return result.rows
                    products = query("SELECT item_code AS item_code, canonical_name AS name FROM ref_products "
                        "WHERE contains(lower(canonical_name),'soda caustica') AND "
                        "contains(lower(canonical_name),'25kg') GROUP BY item_code, canonical_name", 'ref_products')
                    codes = sorted({r[0] for r in products})
                    assert codes and all(code.isalnum() for code in codes)
                    predicate = ' OR '.join("item_code='"+code+"'" for code in codes)
                    rows = query("SELECT card_code AS customer, customer_name AS customer_name, doc_month AS month, count(*) AS purchase_lines "
                        "FROM sales_line WHERE source_table='INV1' AND canceled='N' AND currency='BS' "
                        "AND doc_date>='2026-09-01' AND doc_date<'2026-11-01' AND ("+predicate+") "
                        "GROUP BY card_code, customer_name, doc_month", 'sales_line')
                    expected, delivered, identity_mapping = compare_customers(report, rows)
                    binding.present(None, binding.context)
                    return dict(result_verification='PASS' if expected == delivered else 'FAIL',
                        expected_customers=sorted(expected), delivered_customers=sorted(delivered),
                        product_codes=codes, controls=audit, identity_mapping=identity_mapping,
                        limitation='Published rows only; calendar completeness not certified.')
            finally:
                binding.close()
        result = await asyncio.to_thread(control)
    result['elapsed_seconds'] = time.monotonic()-started
    write_new(evidence.parent / ('independent-verification-' + uuid4().hex + '.json'), result)
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(verify(args.candidate, args.evidence))
    if result['result_verification'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
