"""Open-question DEV catalog, pinned to the existing authorized publication.

No period, product, brand, channel or business question is prescribed here.
Only trusted composition touches physical references. Never a channel adapter.
"""
from dataclasses import replace

from .adaptive_sources import CATALOG as PREVIOUS, AdaptiveExecutor
from .contracts import Catalog, Column, LogicalTable
from .foundation import PERMISSION, local_context
from .foundation_dev import DevBudget

PRODUCT_COLUMNS = ('item_code', 'item_name', 'inventory_uom_id')
CATALOG = Catalog('telchi_foundation_direct_ask_dev_v1', PREVIOUS.organization,
    PREVIOUS.workspace, PREVIOUS.publication, PREVIOUS.snapshot,
    tuple(replace(t, columns=t.columns + (
        (Column('user_sign', 'VARCHAR', True),) if t.name == 'sales_document' else
        (Column('whs_code', 'VARCHAR', True),) if t.name == 'sales_line' else ()), semantic_constraints=(
        'Pinned published active SAP OINV/INV1 population; no prescribed product or period.',
        'doc_date is normalized to ISO calendar DATE (YYYY-MM-DD), not timestamp text; source_as_of remains raw provenance.',
        'Current classification, not historical or certified complete calendar coverage.',
        'Line money before credit memos/global adjustments; not net billing or collections.',
        'Seller category, warehouse, series and creator are not operation channel.'
    )) for t in PREVIOUS.tables) + (
        LogicalTable('product', tuple(Column(n, 'VARCHAR', True) for n in PRODUCT_COLUMNS),
            PERMISSION, ('item_code',), 1000000, (
                'Published SAP product reference. Names are discovery evidence, not accredited brand membership.',
                'Inventory UoM identifier does not establish physical conversion factors.')),
    ), PREVIOUS.known_relations, synthetic_only=False)


def context_for_run():
    return replace(local_context('TELCHIAI_DIRECT_ASK_V1'), catalog=CATALOG,
        sources=tuple(t.name for t in CATALOG.tables), effective_budget=DevBudget())


class AskExecutor(AdaptiveExecutor):
    catalog = CATALOG

    def _prepare_connection(self, db, context):
        # Replace only the historical product/date seal. Reuse the trusted
        # documentary-dimension composition, without calling its sealed parent.
        if db.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise ValueError('foundation_not_readonly')
        access = self.reader.resolve_on(db)
        if (access.foundation_publication_id, str(access.ducklake_snapshot_id)) != (context.publication, context.snapshot):
            raise ValueError('foundation_binding_changed')
        docs, lines = access.sales('sales_document'), access.sales('sales_line')
        keys = getattr(self, 'reference_document_keys', None)
        items = getattr(self, 'reference_item_codes', None)
        if keys is not None:
            if not 0 < len(keys) <= context.effective_budget.result_rows:
                raise ValueError('reference_key_budget')
            db.execute('CREATE TEMP TABLE ask_reference_keys(doc_entry VARCHAR)')
            db.executemany('INSERT INTO ask_reference_keys VALUES (?)', [(k,) for k in sorted(keys)])
        if items:
            db.execute('CREATE TEMP TABLE ask_reference_items(item_code VARCHAR)')
            db.executemany('INSERT INTO ask_reference_items VALUES (?)', [(k,) for k in sorted(items)])
        for name, physical, alias, predicate in (
            ('sales_document', docs, 'd', "d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND d.canceled='N'"),
            ('sales_line', lines, 'l', "l.source_system='SAP_B1_HANA' AND l.source_table='INV1' AND EXISTS (SELECT 1 FROM sales_document d WHERE d.doc_entry=CAST(l.doc_entry AS VARCHAR))")):
            if keys is not None and name == 'sales_document':
                predicate += ' AND CAST(d.doc_entry AS VARCHAR) IN (SELECT doc_entry FROM ask_reference_keys)'
            if items and name == 'sales_line':
                predicate += ' AND CAST(l.item_code AS VARCHAR) IN (SELECT item_code FROM ask_reference_items)'
            table = next(t for t in CATALOG.tables if t.name == name)
            projection = ','.join(
                f'CAST(TRY_CAST({alias}.doc_date AS DATE) AS VARCHAR) AS doc_date' if c.name == 'doc_date' else
                f'TRY_CAST({alias}.{c.name} AS {c.sql_type}) AS {c.name}' for c in table.columns)
            db.execute(f'CREATE TEMP VIEW {name} AS SELECT {projection} FROM {physical} {alias} WHERE {predicate}')
        db.execute("SET schema='main'")
        self._prepare_dimensions(db, access, docs, lines)

    @staticmethod
    def _prepare_dimensions(db, access, docs, lines):
        db.execute(f"""CREATE TEMP VIEW document_metadata AS
            SELECT CAST(h.doc_entry AS VARCHAR) AS doc_entry,CAST(h.user_sign AS VARCHAR) AS user_sign
            FROM {docs} h WHERE h.source_system='SAP_B1_HANA' AND h.source_table='OINV'
            AND EXISTS (SELECT 1 FROM sales_document d WHERE d.doc_entry=CAST(h.doc_entry AS VARCHAR))""")
        db.execute(f"""CREATE TEMP VIEW line_metadata AS
            SELECT CAST(r.doc_entry AS VARCHAR) AS doc_entry,CAST(r.line_num AS VARCHAR) AS line_num,
            CAST(r.whs_code AS VARCHAR) AS whs_code FROM {lines} r
            WHERE r.source_system='SAP_B1_HANA' AND r.source_table='INV1'
            AND EXISTS (SELECT 1 FROM sales_line l WHERE l.doc_entry=CAST(r.doc_entry AS VARCHAR)
                AND l.line_num=CAST(r.line_num AS VARCHAR))""")
        db.execute('''CREATE TEMP VIEW sales_operation AS
            SELECT l.doc_entry,l.line_num,l.item_code,l.line_total,l.currency,
                d.doc_num,d.doc_date,d.slp_code,d.series,h.user_sign,r.whs_code,
                d.sales_channel_code,d.sales_channel_semantic_status,l.raw_extraction_id,l.source_as_of
            FROM sales_line l JOIN sales_document d ON d.doc_entry=l.doc_entry
            JOIN document_metadata h ON h.doc_entry=d.doc_entry
            JOIN line_metadata r ON r.doc_entry=l.doc_entry AND r.line_num=l.line_num''')
        for name, dataset, fields in (
            ('product', 'products', PRODUCT_COLUMNS),
            ('salesperson', 'salespersons', ('source_native_id', 'name', 'salesperson_category_code', 'salesperson_category_name'))):
            path = str(access.reference(dataset)).replace("'", "''")
            projection = ','.join(f'CAST({"coalesce(sap_item_name,product_name,canonical_name)" if field == "item_name" else field} AS VARCHAR) AS {"slp_code" if field == "source_native_id" else field}' for field in fields)
            source = 'SAP_HANA'
            db.execute(f"CREATE TEMP VIEW {name} AS SELECT {projection} FROM read_parquet('{path}') WHERE source_system='{source}'")
