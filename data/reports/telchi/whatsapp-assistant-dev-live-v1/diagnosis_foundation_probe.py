"""One bounded documentary Foundation probe; abort on binding drift, no SAP."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.state_engine import EMPTY, process
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.messaging_sales_query import execute_fixed_query, PERIOD_FROM, PERIOD_TO_EXCLUSIVE

EXPECTED = 'foundation_afd08d9eca6a725be53cdc3f9d5709c9'
OUT = Path(__file__).resolve().parent / 'diagnosis-foundation-probe.json'

class PinnedConnector:
    def __init__(self):
        self.connector = DuckLakeConnector()
    @contextmanager
    def session(self, *, read_only):
        if read_only is not True:
            raise ValueError('read_only_required')
        with self.connector.session(read_only=True) as conn:
            conn.execute("SET threads=2")
            conn.execute("SET memory_limit='512MB'")
            conn.execute("SET max_temp_directory_size='0B'")
            access = FoundationReader(self.connector).resolve_on(conn)
            if access.foundation_publication_id != EXPECTED or access.ducklake_snapshot_id != 1408:
                raise ValueError('binding_drift_no_query')
            yield conn

async def main():
    calls = []
    async def query(**kwargs):
        result = execute_fixed_query(PinnedConnector())
        calls.append(result)
        return result
    proposal = dict(intent='NEW_QUERY', action='EXECUTE', clarification=None,
        state_delta={'set': {'/schema_version': 2, '/metric': 'sales.source_top_items', '/requested_metrics': ['sales.source_top_items'], '/period': {'start': PERIOD_FROM, 'end_exclusive': PERIOD_TO_EXCLUSIVE}}, 'unset': []})
    try:
        processed = process(EMPTY, proposal, {}, 'foundation-probe')
        if processed['committed'] is not True:
            raise ValueError('not_committed')
        state = processed['state_after']
        caps = SalesCapabilities(query=query)
        result = await caps.execute(state)
        evidence = dict(status='PASS', committed=True, source=result['source'], capability=result['capability'],
            row_count=len(result['rows']), result_hash=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest(),
            raw_result_hash=calls[0]['result_hash'], query_hash=calls[0]['query_hash'],
            read_only=calls[0]['read_only'], sap_accessed=calls[0]['sap_accessed'],
            boundary='Real Foundation + state engine + catalog; not WhatsApp, no PG conversation writes')
    except Exception as exc:
        evidence = dict(status='BLOCKED', exception_class=type(exc).__name__, query_calls=len(calls))
    OUT.write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence))

if __name__ == '__main__':
    asyncio.run(main())
