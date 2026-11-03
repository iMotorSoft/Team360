"""Read-only current permission, Foundation parity and focalized inbound trace."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
BACKEND = REPO / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values
for key, value in dotenv_values(BACKEND.parent / '.env.backend-dev.local').items():
    if value is not None:
        os.environ[key] = value
os.environ['TEAM360_ENV'] = 'dev'


def dump(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + '\n')


async def postgres():
    import psycopg
    from psycopg.rows import dict_row
    from modules.db.settings import get_database_settings
    from modules.console.repositories import PermissionConsoleRepository
    from modules.telchi.datalake.sales_query import PERMISSIONS
    result = {'read_only': True}
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,
            row_factory=dict_row, options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        async def query(sql, values=()):
            return await (await conn.execute(sql, values)).fetchall()
        result['database'] = await query("SELECT current_setting('server_version') AS version, current_setting('transaction_read_only') AS readonly")
        result['permissions'] = await query('SELECT permission_code,description FROM core_permissions WHERE permission_code LIKE %s ORDER BY permission_code', ('telchi.sales.%',))
        pilots = await query("SELECT DISTINCT user_id,workspace_id FROM messaging_phone_bindings WHERE environment='dev' AND tenant_id='telchi' AND verification_status='verified' AND revoked_at_utc IS NULL")
        result['pilot_effective_grants'] = []
        for pilot in pilots:
            grants = sorted(await PermissionConsoleRepository().list_effective_permissions(conn, str(pilot['workspace_id']), str(pilot['user_id'])))
            result['pilot_effective_grants'].append(dict(permissions=grants, required_new_grants=PERMISSIONS,
                missing=sorted(set(PERMISSIONS.values()) - set(grants))))
        # Restrict to exact target phrase and day. No sender, contact or text dump.
        result['incident_events'] = await query("""
            SELECT e.id,e.thread_id,e.direction,e.status,e.transport_status,e.occurred_at_utc,
                   e.payload_jsonb->>'processing_state' AS processing_state,
                   e.payload_jsonb->'dispatch_result'->>'classification' AS classification,
                   e.payload_jsonb->'telchi_assistant_v1'->>'decision' AS handler_decision,
                   e.payload_jsonb->'telchi_assistant_v1'->>'execution_status' AS execution_status,
                   e.payload_jsonb->'telchi_assistant_v1'->'response_prepared'->>'classification' AS prepared_classification
            FROM message_events e JOIN communication_channels c ON c.id=e.channel_id
            JOIN core_workspaces w ON w.id=e.workspace_id
            WHERE w.slug='telchi_dev' AND e.direction='inbound'
              AND e.occurred_at_utc >= '2026-10-12T00:00:00Z' AND e.occurred_at_utc < '2026-10-13T00:00:00Z'
              AND lower(trim(e.payload_jsonb->>'text')) IN ('ventas de mayo 2026','ventas de mayo de 2026')
              AND NOT e.payload_jsonb ? 'dev_adapter'
            ORDER BY e.occurred_at_utc LIMIT 20
        """)
        # Same-thread bounded outbound metadata, without recipient/body/provider ID.
        for event in result['incident_events']:
            event['outbound_candidates_not_proven_correlation'] = await query("""
                SELECT id,direction,status,transport_status,event_type,occurred_at_utc
                FROM message_events WHERE thread_id=%s AND direction='outbound'
                  AND occurred_at_utc >= %s AND occurred_at_utc < %s::timestamptz + interval '5 minutes'
                ORDER BY occurred_at_utc LIMIT 10
            """, (event['thread_id'], event['occurred_at_utc'], event['occurred_at_utc']))
    dump('preflight_and_trace.json', result)


def foundation():
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader
    from modules.telchi.datalake.sales_query import execute_query, validate_result, PUBLICATION, SNAPSHOT
    connector = DuckLakeConnector()
    service = {}
    for operation, options in [('sales.latest_documents', {'limit': 10}), ('sales.coverage', {})]:
        service[operation] = validate_result(operation, options, execute_query(operation, options, connector))
    result = dict(service=service, comparisons={}, read_only=True, sap_accessed=False)
    with connector.session(read_only=True) as conn:
        conn.execute('SET threads=2')
        conn.execute("SET memory_limit='512MB'")
        conn.execute("SET max_temp_directory_size='0B'")
        access = FoundationReader(connector).resolve_on(conn)
        assert access.foundation_publication_id == PUBLICATION and access.ducklake_snapshot_id == SNAPSHOT
        result['binding'] = access.as_dict()
        documents = access.sales('sales_document')
        # Independent algorithms: window ranking instead of LIMIT; ordered distinct
        # dates + per-date counts instead of MIN/MAX aggregate.
        references = {
            'sales.latest_documents': (f'''WITH ordered AS (
                SELECT source_system,doc_entry,doc_num,doc_date,canceled,
                       ROW_NUMBER() OVER (ORDER BY doc_date DESC, CAST(doc_entry AS BIGINT) DESC,doc_entry DESC) AS position
                FROM {documents} WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL)
                SELECT source_system,doc_entry,doc_num,doc_date,canceled FROM ordered WHERE position<=? ORDER BY position''', [10]),
            'sales.coverage': (f'''SELECT doc_date,COUNT(*) AS n FROM {documents}
                WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL
                GROUP BY doc_date ORDER BY doc_date''', []),
        }
        for operation, (sql, values) in references.items():
            start = perf_counter()
            cursor = conn.execute(sql, values)
            names = [r[0] for r in cursor.description]
            rows = json.loads(json.dumps([dict(zip(names, r)) for r in cursor.fetchall()], default=str))
            reference_ms = (perf_counter() - start) * 1000
            if operation == 'sales.coverage':
                rows = [dict(first_date=rows[0]['doc_date'] if rows else None,
                    last_date=rows[-1]['doc_date'] if rows else None, documents=sum(r['n'] for r in rows),
                    latest_month_with_rows=rows[-1]['doc_date'][:7] if rows else None, complete_month_certified=False)]
            result['comparisons'][operation] = dict(sql=sql, parameters=values, rows=rows,
                elapsed_ms=reference_ms, parity=rows == service[operation]['rows'])
        # Reuse sealed prior Calenta probes verbatim, ONLY if their paths/pins
        # still match CURRENT. No new alias or fuzzy commercial join is created.
        old = json.loads((ROOT.parent / 'historical_business_query_inventory_v1/foundation_business_cases.json').read_text())
        result['calenta_evidence_reused'] = []
        for probe in old['queries']:
            if probe['probe_id'].startswith('calenta_') or probe['probe_id'] == 'may_calenta_native_lines':
                result['calenta_evidence_reused'].append(probe)
        assert all(v['parity'] for v in result['comparisons'].values())
    dump('foundation_comparison.json', result)


if __name__ == '__main__':
    asyncio.run(postgres())
    foundation()
    print('Read-only preflight/trace and two independent SQL comparisons completed')
