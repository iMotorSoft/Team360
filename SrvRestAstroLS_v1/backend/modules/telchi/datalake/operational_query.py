"""Closed operational analytics over canonical CURRENT; no source extraction or grants.

SQL belongs here, not in Luna or the conversational handler. Source observations
and historical business metrics are deliberately separate. A partial observation
never proves a zero, a historical balance or a finished-goods receipt.
"""
import asyncio
from datetime import date
from decimal import Decimal
import json
import re
import sys
from time import perf_counter

from .messaging_sales_query import TelchiQueryError
from .query_profile import measured

# metric -> domain, dataset, business label. Each operation needs its own grant.
OPERATIONS = {
    'inventory.stock_by_warehouse': ('inventory', 'inventory_balance', 'Stock observado por depósito'),
    'production.consumption': ('production', 'production_issue', 'Consumo registrado para producción'),
    'production.orders': ('production', 'production_order', 'Órdenes de producción observadas'),
    'production.bom': ('production', 'bom_line', 'Componentes de receta observada'),
    'purchasing.invoiced_amount': ('purchasing', 'ap_invoice', 'Facturado por proveedores'),
    'purchasing.ordered_amount': ('purchasing', 'purchase_order', 'Órdenes de compra observadas'),
    'purchasing.received_amount': ('purchasing', 'purchase_receipt', 'Recepciones de compra observadas'),
    'collections.received_amount': ('collections', 'collection_payment', 'Cobros registrados'),
    'collections.unallocated': ('collections', 'collection_payment', 'Pagos sin aplicación registrada'),
    'material_supply.consumption': ('material_supply', 'observed_material_actual_consumption', 'Consumo elegible de Material Supply'),
}
PERMISSIONS = {metric: 'telchi.' + metric + '.read.v1' for metric in OPERATIONS}
SNAPSHOT_METRICS = {'inventory.stock_by_warehouse', 'production.bom'}
CONTRACT = 'TELCHI_OPERATIONAL_ANALYTICS_V1'


def parameters(metric, options):
    if (metric not in OPERATIONS or not isinstance(options, dict)
            or not set(options) <= {'date_from', 'date_to_exclusive', 'item_code', 'limit'}):
        raise ValueError('invalid_operational_parameters')
    limit = options.get('limit', 10)
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('invalid_operational_limit')
    item = options.get('item_code')
    if item is not None:
        if not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}',item):
            raise ValueError('invalid_operational_item')
    if metric.startswith(('purchasing.', 'collections.')) and item is not None:
        raise ValueError('unsupported_operational_filter')
    if metric in SNAPSHOT_METRICS:
        if 'date_from' in options or 'date_to_exclusive' in options:
            raise ValueError('snapshot_is_not_historical')
        if not item:
            raise ValueError('item_code_required')
    else:
        try:
            start, end = date.fromisoformat(options['date_from']), date.fromisoformat(options['date_to_exclusive'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('operational_period_required') from None
        if start >= end or (end-start).days > 366:
            raise ValueError('invalid_operational_period')
    return dict(options, limit=limit)


def _rows(con, sql, args=()):
    cursor = measured('operational_sql_execute',con.execute,sql,args)
    return [dict(zip([c[0] for c in cursor.description], row)) for row in measured('operational_sql_fetch',cursor.fetchall)]


def _json(value):
    return json.loads(json.dumps(value, default=str))


class EvidenceConnection:
    """Record successful SQL and bound inputs without changing cursor semantics."""
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def execute(self, statement, args=()):
        cursor = self.connection.execute(statement, args)
        self.statements.append(dict(sql=statement, parameters=_json(args)))
        return cursor

    def executemany(self, statement, args):
        args = list(args)
        cursor = self.connection.executemany(statement, args)
        self.statements.append(dict(sql=statement, parameters=_json(args), batch=True))
        return cursor


def execute_on(con, access, metric, options):
    """One already resolved, verified publication; also used by bounded batch probes."""
    options = parameters(metric, options)
    con = EvidenceConnection(con)
    sql_evidence = con.statements
    domain, dataset, label = OPERATIONS[metric]
    started = perf_counter()
    from pathlib import Path
    from . import sales_incremental as durable
    stable = access.manifest['operational_observations']
    proof = durable.read_json(Path(stable['reconciliation_path']))
    if durable.digest(proof) != stable['reconciliation_sha256']:
        raise TelchiQueryError('operational_reconciliation_changed')
    capture_name = 'stock' if domain == 'inventory' else ('production_issue' if domain == 'material_supply' else dataset)
    capture = proof['captures']['captured_datasets'][capture_name]
    used = {}
    def observation(group, name):
        rel = access.operational_observation(group, name)
        used[name] = access.manifest['operational_observations']['datasets'][name]['sha256']
        return rel
    def view(name, rel):
        con.execute('CREATE OR REPLACE TEMP VIEW ' + name + ' AS SELECT * FROM ' + rel)
    limitations = []
    coverage = dict(kind='BOUNDED_OBSERVATION', complete_business_history=False,
                    absence_is_zero=False, observation_started_at=capture['source_before']['utc'],
                    observation_finished_at=capture['source_after']['utc'], source_scope=capture['scope'], requested_period={k: options[k] for k in ('date_from','date_to_exclusive') if k in options})
    controls = {}
    summary = None
    item_args = [options['item_code']] if options.get('item_code') else []
    if metric == 'inventory.stock_by_warehouse':
        view('op_stock', access.stock_availability())
        used['inventory_balance'] = access.foundation.oitw_publication_id
        rows = _rows(con, '''SELECT item_code,warehouse,inventory_uom_id AS unit,
            on_hand_qty,committed_qty,available_qty,stock_as_of
            FROM op_stock WHERE item_code=? ORDER BY warehouse''', item_args)
        # Do not aggregate unknown UoM, incompatible units, or different cuts.
        coverage.update(kind='STOCK_SNAPSHOT', source_as_of=access.foundation.oitw_source_as_of)
        controls['unknown_unit_positions'] = sum(not r['unit'] or r['unit']=='UNKNOWN' for r in rows)
        limitations += ['Depósitos no son sucursales. Disponible = existencia menos comprometido; pedidos de compra no incluidos.',
            'Unidades desconocidas no se infieren ni se suman. Posiciones ausentes no acreditan stock cero.']
    else:
        view('op_source', observation(domain if domain != 'material_supply' else 'production',
                                    dataset if domain != 'material_supply' else 'production_issue'))
        if metric == 'production.bom':
            rows = _rows(con, '''SELECT "Father" AS product,"Code" AS component,"Type" AS native_type,
                "Quantity" AS quantity,"Uom" AS unit,"ChildNum" AS line_number
                FROM op_source WHERE "Father"=? ORDER BY "ChildNum"''', item_args)
            coverage['kind'] = 'CURRENT_BOM_OBSERVATION'
            limitations += ['Receta observada actual; no acredita vigencia histórica ni recepción de producto terminado. Cantidades nativas, sin conversión.']
        else:
            date_field = 'payment_date' if domain == 'collections' else ('PostDate' if metric == 'production.orders' else 'DocDate')
            bounds = _rows(con, f'SELECT min("{date_field}") AS first_observed_date,max("{date_field}") AS last_observed_date,count(*) AS dataset_rows FROM op_source')[0]
            coverage.update(bounds)
            # Dates of rows describe observations, not a ledger of completeness.
            declared, end = capture['scope']['start'], capture['scope']['end_exclusive']
            coverage.update(declared_start=declared, declared_end_exclusive=end)
            coverage['requested_outside_capture'] = (options['date_from'] < declared or options['date_to_exclusive'] > end)
            con.execute(f'CREATE OR REPLACE TEMP TABLE op_period AS SELECT * FROM op_source WHERE "{date_field}">=? AND "{date_field}"<?',
                        [options['date_from'],options['date_to_exclusive']])
            if domain == 'purchasing':
                # DocTotal is the source local amount, NOT native USD just because
                # DocCur says USD. Foreign totals were not captured here.
                rows = _rows(con, '''SELECT "DocStatus" AS document_status,'BS' AS currency,
                    count(*) AS documents,count(DISTINCT "CardCode") AS suppliers,
                    sum(cast("DocTotal" AS DECIMAL(38,12))) AS amount
                    FROM op_period WHERE "CANCELED"='N' AND "DocCur"='BS' GROUP BY ALL ORDER BY document_status''')
                summary = dict(currency='BS',amount=str(sum((r['amount'] for r in rows),Decimal(0))),
                               documents=sum(r['documents'] for r in rows)) if rows else None
                controls.update(_rows(con, '''SELECT count(*) FILTER(WHERE "CANCELED"<>'N' OR "CANCELED" IS NULL) AS excluded_nonactive_documents,
                    count(*) FILTER(WHERE "CANCELED"='N' AND ("DocCur"<>'BS' OR "DocCur" IS NULL)) AS excluded_other_currency_documents FROM op_period''')[0])
                limitations += ['Importes de cabeceras activas en BS, separados por estado. No se suman órdenes, recepciones y facturas.',
                    'Moneda extranjera excluida: DocTotal no acredita su importe nativo. Solicitudes y devoluciones no capturadas; no es compra neta después de devoluciones.',
                    f"Las {proof['purchasing']['missing_previous_line_keys']} diferencias de líneas en {len(proof['purchasing']['documents'])} OC no acreditan su causa histórica SAP."]
            elif domain == 'collections':
                if metric == 'collections.unallocated':
                    view('op_allocations', observation('collections','collection_allocation'))
                    rows = _rows(con, '''SELECT source_doc_entry AS payment,source_doc_num AS payment_number,
                        customer_code,payment_date,currency,payment_total AS local_amount,cancelled
                        FROM op_period P WHERE NOT EXISTS(SELECT 1 FROM op_allocations A WHERE A.payment_doc_entry=P.source_doc_entry)
                        ORDER BY payment_date,payment''')
                    limitations += ['Sin aplicación registrada en RCT2 no significa necesariamente pendiente de imputación. Incluye estados de cancelación explícitos. local_amount es importe fuente local, no moneda extranjera.']
                else:
                    rows = _rows(con, '''SELECT 'BS' AS currency,count(*) AS payments,
                        count(DISTINCT customer_code) AS customers,
                        sum(cast(payment_total AS DECIMAL(38,12))) AS amount
                        FROM op_period WHERE cancelled='N' AND currency='BS' HAVING count(*)>0''')
                    controls.update(_rows(con, '''SELECT count(*) FILTER(WHERE cancelled<>'N' OR cancelled IS NULL) AS excluded_nonactive_payments,
                        count(*) FILTER(WHERE cancelled='N' AND (currency<>'BS' OR currency IS NULL)) AS excluded_other_currency_payments FROM op_period''')[0])
                limitations += ['Eventos de pagos publicados, no saldo histórico ni aging global. Pagos y aplicaciones son grains distintos y nunca se suman como ingresos independientes.']
            elif metric == 'production.orders':
                rows = _rows(con, '''SELECT "DocEntry" AS production_order,"ItemCode" AS item_code,"Status" AS native_status,
                    "PlannedQty" AS planned_quantity,"CmpltQty" AS source_completed_field,"PostDate" AS posting_date
                    FROM op_period ''' + ('WHERE "ItemCode"=? ' if item_args else '') + 'ORDER BY "DocEntry"', item_args)
                limitations += ['Estado SAP: P planificada, R liberada, L cerrada, C cancelada. Campo de orden no acredita recepción efectiva; no hay receipts de producto terminado. Cantidad planificada no acredita unidad física comparable.']
            else:
                # Production exposes ALL active 202 issue identities, including
                # unknown/resource identities, never relabelled as raw materials.
                view('op_eligible_groups', observation('material_supply','observed_material_actual_consumption'))
                view('op_orders', observation('production','production_order'))
                if metric == 'material_supply.consumption':
                    eligibility = '''AND EXISTS(SELECT 1 FROM op_orders O WHERE O."DocEntry"=I."BaseEntry")
                        AND EXISTS(SELECT 1 FROM op_eligible_groups E WHERE E.item_code=I."ItemCode"
                        AND E.native_unit_msr IS NOT DISTINCT FROM I."unitMsr"
                        AND E.native_uom_code IS NOT DISTINCT FROM I."UomCode"
                        AND E.native_num_per_msr IS NOT DISTINCT FROM I."NumPerMsr")'''
                    limitations += ['Subconjunto elegible del derivado publicado, filtrado por fecha de emisión. Identidad de material no equivale a clasificación de materia prima.',
                        'Los cinco datasets históricos de Material Supply no se actualizan. No acredita faltantes, reposición ni cobertura de demanda.']
                else:
                    eligibility = ''
                    limitations += ['Emisiones activas BaseType 202; identidad no equivale a materia prima clasificada. Incluye identidades de recursos/desconocidas separadas, sin inferir su naturaleza.',
                        f"{len(proof['production']['unknown_lines'])} líneas fuente desconocidas se conservan; no hay recepción de producto terminado ni vigencia histórica de BOM."]
                con.execute('''CREATE OR REPLACE TEMP TABLE op_consumption AS SELECT I.* FROM op_period I
                    WHERE I."CANCELED"='N' AND cast(I."BaseType" AS DECIMAL(18,6))=202 ''' + eligibility
                    + (' AND I."ItemCode"=?' if item_args else ''), item_args)
                rows = _rows(con, '''SELECT "ItemCode" AS item_code,"unitMsr" AS unit,"UomCode" AS uom_code,
                    "NumPerMsr" AS native_factor,count(*) AS issue_lines,
                    sum(cast("Quantity" AS DECIMAL(38,12))) AS quantity
                    FROM op_consumption GROUP BY ALL ORDER BY unit NULLS LAST,uom_code NULLS LAST,native_factor NULLS LAST,quantity DESC,item_code''')
                controls.update(_rows(con, '''SELECT (SELECT count(*) FROM op_period) AS period_source_lines,
                    count(*) AS included_issue_lines FROM op_consumption''')[0])
                # These native-key unknowns are part of the verified publication
                # proof. Keep their exact affected count, not only a global note.
                unknown = proof['production']['unknown_lines']
                con.execute('CREATE OR REPLACE TEMP TABLE op_unknown(doc_entry BIGINT,line_num BIGINT)')
                if unknown:
                    con.executemany('INSERT INTO op_unknown VALUES (?,?)',[(r['DocEntry'],r['LineNum']) for r in unknown])
                controls['unknown_native_identity_lines_affected'] = con.execute('''SELECT count(*) FROM op_consumption I
                    JOIN op_unknown U ON I."DocEntry"=U.doc_entry AND I."LineNum"=U.line_num''').fetchone()[0]
                limitations += ['Cantidades separadas por producto, unidad nativa y factor; factor mostrado, no aplicado. Sin suma ni ranking global entre unidades incompatibles.']
    total = len(rows)
    rows = rows[:options['limit']]
    serializing = perf_counter()
    result = _json(dict(contract=CONTRACT, capability=metric+'.v1', metric=metric, label=label, summary=summary,
        parameters=options, rows=rows, total_rows=total, omitted_rows=total-len(rows), controls=controls,
        coverage=coverage, limitations=limitations, read_only=True, sap_accessed=False,
        sql_evidence=sql_evidence,
        source=dict(publication_id=access.foundation_publication_id,snapshot_id=access.ducklake_snapshot_id,
                    reference_version=access.foundation.reference_version,updated_at=access.foundation_data_as_of,
                    datasets=used), timings=dict(foundation_resolution_ms=access.foundation_resolution_ms,
                                                planning_and_sql_ms=(serializing-started)*1000)))
    result['timings']['serialization_ms'] = (perf_counter()-serializing)*1000
    return result


def validate_result(metric, options, result):
    options = parameters(metric, options)
    if (not isinstance(result, dict) or result.get('contract') != CONTRACT
            or result.get('capability') != metric+'.v1' or result.get('metric') != metric
            or result.get('parameters') != options or result.get('read_only') is not True
            or result.get('sap_accessed') is not False or not result.get('source',{}).get('publication_id')
            or not result.get('source',{}).get('reference_version')
            or not isinstance(result.get('rows'),list) or len(result['rows'])>options['limit']
            or type(result.get('total_rows')) is not int or result['total_rows'] < len(result['rows'])
            or result.get('omitted_rows') != result['total_rows']-len(result['rows'])
            or result.get('coverage',{}).get('absence_is_zero') is not False
            or not result.get('limitations') or not result.get('source',{}).get('datasets')):
        raise ValueError('invalid_operational_result')
    for row in result['rows']:
        for key in ('quantity','amount','on_hand_qty','committed_qty','available_qty'):
            if key in row and (not isinstance(row[key],str) or not Decimal(row[key]).is_finite()):
                raise ValueError('invalid_operational_number')
    return result


def execute_query(metric, options, connector=None):
    parameters(metric, options)
    from .ducklake import DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = connector or DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise TelchiQueryError('datalake_not_read_only')
        access = FoundationReader(connector).resolve_on(con)
        return validate_result(metric, options, execute_on(con, access, metric, options))


_LOCK = asyncio.Lock()


async def query_operational(metric, options, *, timeout_seconds=60):
    parameters(metric, options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable,'-m',__name__,metric,json.dumps(options),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            output,_ = await asyncio.wait_for(process.communicate(),timeout_seconds)
            if process.returncode:
                raise TelchiQueryError('operational_worker_error')
            return validate_result(metric,options,json.loads(output)['result'])
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


if __name__ == '__main__':
    try:
        print(json.dumps({'result':execute_query(sys.argv[1],json.loads(sys.argv[2]))}))
    except Exception:
        print(json.dumps({'error':'operational_query_unavailable'}))
        sys.exit(1)
