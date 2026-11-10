"""Opt-in live-data benchmark; ALL catalog writes are in-memory overlays.

Run as a module with --output <report.json>. No SAP, service, CURRENT, physical
file or live schema mutation. The old full reader is measured once; the new
reader uses a fully validated receipt stored only in an ephemeral local catalog.
"""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from modules.telchi.datalake import ducklake, foundation_reader, sales_query
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_read_binding import make_binding
from modules.telchi.datalake.sales_succession import validate_successor, physical_metadata, mark_result


def benchmark():
    connector = ducklake.DuckLakeConnector()
    original_reader = foundation_reader.FoundationReader
    captured = []

    class FullReader(original_reader):
        def __init__(self, connector):
            super().__init__(connector, full_validation=True)

        def resolve_on(self, connection):
            access = super().resolve_on(connection)
            captured.append(access)
            return access

    operation = sales_query.MONETARY_OPERATION
    options = dict(date_from='2026-10-01', date_to_exclusive='2026-11-01', currency='BS')
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() == (True,)

        @contextmanager
        def same(): yield con

        class OverlayConnector:
            @contextmanager
            def session(self, *, read_only=False):
                assert read_only
                yield con

        overlay = OverlayConnector()
        live_store = FoundationPublicationStore(same)
        before = live_store.current_pointer()
        with patch.object(foundation_reader, 'FoundationReader', FullReader):
            started = perf_counter()
            old = sales_query.execute_query(operation, options, overlay)
            baseline_ms = (perf_counter()-started)*1000
            sales_query.validate_result(operation, options, mark_result(old))
        access = captured[-1]
        publication = live_store.get(before)
        assert access.foundation_publication_id == before
        # Finish update-only accreditation; never persist it to the live store.
        started = perf_counter()
        validate_successor(live_store, publication, access.ducklake_snapshot_id,
                           physical=True, _reader_validated=True)
        binding = make_binding(publication, access, commercial=True, physical=physical_metadata(access))
        accreditation_ms = (perf_counter()-started)*1000

        local = FoundationPublicationStore(same, catalog='')
        local.ensure_schema()
        local.create_candidate(publication)
        con.execute('INSERT INTO ops.foundation_current_v1 VALUES (1, ?, ?)', [before, publication.committed_at])
        local.accredit_read_binding(publication, binding)

        timings, sql_timings = [], []
        with patch.object(foundation_reader, 'FoundationReader',
                          lambda c: original_reader(c, metadata_catalog='')), \
             patch.object(ducklake, 'DuckLakeConnector', lambda: overlay):
            # No process-local admitted marker: validate_result takes its normal
            # parent/result_binding path against catalog metadata on every run.
            for _ in range(4):
                started = perf_counter()
                new = sales_query.execute_query(operation, options, overlay)
                sales_query.validate_result(operation, options, new)
                timings.append((perf_counter()-started)*1000)
                sql_timings.append(new['sql_duration_ms'])
                assert new['rows'] == old['rows'] and new['source'] == old['source']
        row = new['rows'][0]
        assert row['invoice_count'] == 41078 and row['credit_count'] == 280
        for key, amount in [('billed_amount', '11982896.13'), ('credit_amount', '479145.78'), ('net_amount', '11503750.35')]:
            assert Decimal(row[key]) == Decimal(amount), (key, row[key])
        assert live_store.current_pointer() == before
        return dict(publication=before, commit_snapshot_id=binding['commit_snapshot_id'], snapshot_id=binding['snapshot_id'],
            source=new['source'], rows=new['rows'], baseline_query_ms=round(baseline_ms,3),
            update_only_extra_accreditation_ms=round(accreditation_ms,3), first_query_ms=round(timings[0],3),
            repeated_query_ms=[round(t,3) for t in timings[1:]], sql_ms=[round(t,3) for t in sql_timings],
            result_equality='PASS', live_current_unchanged=True, live_catalog_writes=0,
            measurement_scope='same-session read-only live Parquet SQL plus metadata resolution and result validation; receipt in ephemeral in-memory catalog; excludes attach/process startup',
            threads=2, memory_limit='512MB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str)+'\n')
    print(json.dumps(result, default=str))
