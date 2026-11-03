"""Sealed DEV research projection; no new physical data or business rules."""
from dataclasses import replace

from .contracts import Catalog, Column, LogicalTable
from .foundation import CATALOG as BASE, PERMISSION, local_context
from .foundation_dev import DevBudget, DevExecutor

OPERATION_COLUMNS = (
    ('doc_entry', 'VARCHAR'), ('line_num', 'VARCHAR'), ('item_code', 'VARCHAR'),
    ('line_total', 'DECIMAL(38,6)'), ('currency', 'VARCHAR'),
    ('doc_num', 'VARCHAR'), ('doc_date', 'VARCHAR'), ('slp_code', 'VARCHAR'),
    ('series', 'VARCHAR'), ('user_sign', 'VARCHAR'), ('whs_code', 'VARCHAR'),
    ('sales_channel_code', 'VARCHAR'), ('sales_channel_semantic_status', 'VARCHAR'),
    ('raw_extraction_id', 'VARCHAR'), ('source_as_of', 'VARCHAR'))
SELLER_COLUMNS = tuple((n, 'VARCHAR') for n in (
    'slp_code', 'name', 'salesperson_category_code', 'salesperson_category_name'))

CATALOG = Catalog('telchi_foundation_adaptive_dev_v1', BASE.organization, BASE.workspace,
    BASE.publication, BASE.snapshot, BASE.tables + (
        LogicalTable('document_metadata', tuple(Column(n, 'VARCHAR', True) for n in ('doc_entry', 'user_sign')),
            PERMISSION, ('doc_entry',), 1000000, ('Scoped OINV creator, not seller or office.',)),
        LogicalTable('line_metadata', tuple(Column(n, 'VARCHAR', True) for n in ('doc_entry', 'line_num', 'whs_code')),
            PERMISSION, ('doc_entry', 'line_num'), 1000000, ('Scoped INV1 warehouse, not commercial channel.',)),
        LogicalTable('sales_operation', tuple(Column(n, t, True) for n, t in OPERATION_COLUMNS),
            PERMISSION, ('doc_entry', 'line_num'), 1000000, (
                'Same four-SKU active August invoice population. Trusted OINV/INV1 doc_entry relation.',
                'line_total is line money BS, not header money, net billing or collections.',
                'slp_code is HEADER seller; warehouse, creator and series are distinct dimensions.',
                'No office dimension or series-name master is exposed; cannot infer either from a code.')),
        LogicalTable('salesperson', tuple(Column(n, t, True) for n, t in SELLER_COLUMNS),
            PERMISSION, ('slp_code',), 1000000, (
                'Pinned reference salespersons, SAP_HANA source_native_id, sellers present in the scoped documents.',
                'Current seller category, NOT the channel of an operation or a historical category.',
                'Any proposed link requires key/coverage/cardinality and business-meaning checks.'))),
    BASE.known_relations, synthetic_only=False)


def context_for_run():
    return replace(local_context('TELCHIAI_ADAPTIVE_BUSINESS_RESEARCH_V1'), catalog=CATALOG,
                   sources=tuple(t.name for t in CATALOG.tables), effective_budget=DevBudget())


class AdaptiveExecutor(DevExecutor):
    catalog = CATALOG

    def _prepare_connection(self, db, context):
        super()._prepare_connection(db, context)
        access = self.reader.resolve_on(db)
        if (access.foundation_publication_id, str(access.ducklake_snapshot_id)) != (context.publication, context.snapshot):
            raise ValueError('foundation_binding_changed')
        docs, lines = access.sales('sales_document'), access.sales('sales_line')
        db.execute(f'''CREATE TEMP VIEW document_metadata AS
            SELECT CAST(h.doc_entry AS VARCHAR) AS doc_entry,CAST(h.user_sign AS VARCHAR) AS user_sign
            FROM {docs} h WHERE h.source_system='SAP_B1_HANA' AND h.source_table='OINV'
            AND EXISTS (SELECT 1 FROM sales_document d WHERE d.doc_entry=h.doc_entry)''')
        db.execute(f'''CREATE TEMP VIEW line_metadata AS
            SELECT CAST(r.doc_entry AS VARCHAR) AS doc_entry,CAST(r.line_num AS VARCHAR) AS line_num,
                   CAST(r.whs_code AS VARCHAR) AS whs_code
            FROM {lines} r WHERE r.source_system='SAP_B1_HANA' AND r.source_table='INV1'
            AND EXISTS (SELECT 1 FROM sales_line l WHERE l.doc_entry=r.doc_entry AND l.line_num=r.line_num)''')
        # Known document-line link only. Independent raw-key reference verifies
        # uniqueness, completeness and money without reusing this join.
        db.execute(f'''CREATE TEMP VIEW sales_operation AS
            SELECT l.doc_entry,l.line_num,l.item_code,l.line_total,l.currency,
                   d.doc_num,d.doc_date,d.slp_code,d.series,CAST(h.user_sign AS VARCHAR) AS user_sign,
                   CAST(r.whs_code AS VARCHAR) AS whs_code,d.sales_channel_code,
                   d.sales_channel_semantic_status,l.raw_extraction_id,l.source_as_of
            FROM sales_line l JOIN sales_document d ON d.doc_entry=l.doc_entry
            JOIN document_metadata h ON h.doc_entry=d.doc_entry
            JOIN line_metadata r ON r.doc_entry=l.doc_entry AND r.line_num=l.line_num ''')
        path = str(access.reference('salespersons')).replace("'", "''")
        db.execute(f'''CREATE TEMP VIEW salesperson AS
            SELECT CAST(s.source_native_id AS VARCHAR) AS slp_code,CAST(s.name AS VARCHAR) AS name,
                   CAST(s.salesperson_category_code AS VARCHAR) AS salesperson_category_code,
                   CAST(s.salesperson_category_name AS VARCHAR) AS salesperson_category_name
            FROM read_parquet('{path}') s WHERE s.source_system='SAP_HANA'
            AND EXISTS (SELECT 1 FROM sales_document d WHERE d.slp_code=CAST(s.source_native_id AS VARCHAR))''')
