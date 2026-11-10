"""Offline proposal evidence; never loads private config, PG, identities or grants.

Run from repository root with backend/.venv/bin/python. Only Parquet footer/schema
metadata is read (24 reference datasets); no population scan or live CURRENT claim.
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[7]
MODULE = ROOT / 'SrvRestAstroLS_v1/backend/modules/telchi'
OUT = ROOT / 'data/reports/telchi/presidencia-sourcepolicy-v1'
REFERENCE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/reference/_versions/v2_sales_448ae93a960bf7342564a2d0')

# Explicit proposal, not default grants or a capability-derived discover allowlist.
# One owner permission per physical/logical dataset, reused across many sources.
GROUPS = [
    ('products.search', 'CLIENTES_PRODUCTOS', 'reference',
     'ref_products ref_brand ref_product_business_type ref_units_of_measure ref_portfolio_family ref_entity_alias'),
    ('sales.commercial_line_amount_by', 'VENTAS_TRAZABILIDAD', 'reference',
     'ref_customers ref_branches ref_business_locations ref_customer_business_type ref_currencies ref_document_types ref_payment_terms ref_sales_channel ref_salespersons ref_business_unit ref_operating_domain ref_operating_model ref_party ref_users'),
    ('sales.commercial_line_amount_by', 'VENTAS', 'sales', 'sales_document sales_line'),
    ('sales.commercial_line_amount_by', 'VENTAS', 'credit_memo', 'credit_memo_document credit_memo_line'),
    ('inventory.stock_by_warehouse', 'STOCK_E_INVENTARIOS', 'reference',
     'ref_warehouses ref_warehouse_roles ref_production_site'),
    ('inventory.stock_by_warehouse', 'STOCK_E_INVENTARIOS', 'oitw', 'inventory_balance'),
    ('inventory.stock_by_warehouse', 'STOCK_E_INVENTARIOS', 'oinm', 'inventory_movement'),
    ('purchasing.ordered_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'reference', 'ref_suppliers'),
    ('purchasing.ordered_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'purchasing',
     'purchase_order purchase_order_line purchasing_document_lineage'),
    ('purchasing.received_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'purchasing',
     'purchase_receipt purchase_receipt_line purchase_inventory_receipt'),
    ('purchasing.invoiced_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'purchasing', 'ap_invoice ap_invoice_line'),
    ('collections.unallocated', 'CREDITO_Y_DEUDORES', 'receivables_collections',
     'receivable_settlement_status commercial_term_classification'),
    ('collections.received_amount', 'COBRANZAS', 'receivables_collections', 'collection_method_fact'),
    ('material_supply.consumption', 'REPOSICION', 'material_supply',
     'material_actual_consumption material_equivalent_demand material_lead_time_profile material_supply_status open_purchase_pipeline'),
    ('sales.commercial_line_amount_by', 'VENTAS_PROPOSITO_COMERCIAL', 'commercial_purpose',
     'deliveries_from_quotations invoices_from_quotations oqut_october_2026 orders_from_quotations qut1_october_2026'),
    ('purchasing.ordered_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'operational_observations',
     'observed_purchase_order observed_purchase_order_line'),
    ('purchasing.received_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'operational_observations',
     'observed_purchase_receipt observed_purchase_receipt_line'),
    ('purchasing.invoiced_amount', 'COMPRAS_Y_ABASTECIMIENTO', 'operational_observations',
     'observed_ap_invoice observed_ap_invoice_line'),
    ('collections.unallocated', 'CREDITO_Y_DEUDORES', 'operational_observations',
     'observed_receivable_document observed_collection_allocation observed_payment_term'),
    ('collections.received_amount', 'COBRANZAS', 'operational_observations',
     'observed_collection_payment observed_payment_method_component observed_reconciliation_event observed_reconciliation_participant'),
    ('production.bom', 'PRODUCCION', 'operational_observations', 'observed_bom_header observed_bom_line'),
    ('production.orders', 'PRODUCCION', 'operational_observations', 'observed_production_order'),
    ('production.consumption', 'PRODUCCION', 'operational_observations', 'observed_production_issue'),
    ('inventory.stock_by_warehouse', 'STOCK_E_INVENTARIOS', 'operational_observations', 'observed_inventory_movement'),
    ('material_supply.consumption', 'REPOSICION', 'operational_observations', 'observed_observed_material_actual_consumption'),
]

A = set('sales_document sales_line credit_memo_document ref_products ref_customers inventory_balance observed_purchase_order observed_purchase_receipt observed_ap_invoice observed_collection_payment observed_production_issue observed_production_order observed_bom_line observed_observed_material_actual_consumption'.split())
C = set('ref_users ref_suppliers ref_party ref_entity_alias ref_business_unit ref_operating_domain ref_operating_model credit_memo_line purchasing_document_lineage inventory_movement deliveries_from_quotations invoices_from_quotations oqut_october_2026 orders_from_quotations qut1_october_2026'.split())
LIMITS = {
    'reference': 'R: referencia actual/no necesariamente historica; UNKNOWN y relaciones no acreditadas no se completan por inferencia',
    'sales': 'S: cobertura por ventana; separar moneda/cancelacion; line_total antes de NC; no ingreso contable',
    'credit_memo': 'NC: documento/linea distintos; reconciliar signos, base y cancelacion antes de netear',
    'oitw': 'ST: stock observado al corte; unidades nativas; no saldo historico ni suma heterogenea',
    'oinm': 'M: FROZEN_NATIVE_KEY_PREFIX_ONLY; no continuidad completa ni derivacion de stock',
    'receivables_collections': 'RC: corte/snapshot propio; clasificacion no prueba pago ni aging completo; preservar no aplicado',
    'purchasing': 'P: etapas separadas; no neto tras devoluciones; lineage es resolucion, no hecho adicional',
    'material_supply': 'MS: unidades/cortes propios; demanda equivalente y lead time derivados; UNKNOWN no es cero',
    'commercial_purpose': 'CP: candidato historico; procedencia CURRENT contradictoria en evidencia; octubre 2026 no generalizable',
    'operational_observations': 'O: BOUNDED_OBSERVATION; absence_is_zero=False; no sustituye historia/saldo certificado',
}
NATIVE = {
    'sales': 'SAP OINV/INV1; FoundationReader.relation(sales, dataset), facts sellados',
    'credit_memo': 'SAP ORIN/RIN1; FoundationReader.relation(credit_memo, dataset)',
    'oinm': 'SAP OINM; FoundationReader.relation(oinm, inventory_movement)',
    'oitw': 'SAP OITW; FoundationReader.relation(oitw, inventory_balance), contrato de sucesion stock',
    'receivables_collections': 'SAP facturas/pagos/reconciliacion; FoundationReader.relation o published_file_relation; snapshot CxC seleccionado',
    'purchasing': 'SAP OPOR/POR1, OPDN/PDN1, OPCH/PCH1 e inventario; datasets/hash de componente purchasing',
    'material_supply': 'derivados SAP consumo/compras/recetas; datasets/hash de componente material_supply',
    'commercial_purpose': 'SAP OQUT/QUT1 y trazas pedido/entrega/factura; solo datasets/hash del manifiesto seleccionado, nunca candidata por path',
    'operational_observations': 'SAP capturado; CAPTURED_OPERATIONAL_OBSERVATIONS_V1; FoundationReader.operational_observation + GROUPS',
}


def main():
    import duckdb
    OUT.mkdir(parents=True, exist_ok=True)
    old = (MODULE / 'PRESIDENCIA_ACCREDITATION_V1.md').read_text()
    inventory = old.split('### 2.2 Inventario')[1].split('### 2.3')[0]
    expected = set(re.findall(r'`([a-z_0-9]+)`\(\d+\)', inventory))
    rows = []
    for permission, domain, component, names in GROUPS:
        for name in names.split():
            limitation = LIMITS[component]
            if name == 'ref_users':
                limitation += '; maestro OUSR identificatorio, no credenciales ni grant SAP/Console'
            if name in {'ref_suppliers', 'ref_customers', 'ref_party', 'ref_entity_alias', 'ref_salespersons'}:
                limitation += '; identificadores empresariales/personales: uso interno Presidencia, no difusion externa'
            if name in {'ref_brand','ref_business_unit','ref_operating_domain','ref_operating_model','ref_product_business_type'}:
                limitation += '; taxonomia incompleta/UNKNOWN no es prohibicion'
            if name == 'ref_entity_alias':
                limitation += '; AMBIGUOUS no autoriza fusion automatica de identidades'
            if name == 'observed_inventory_movement':
                limitation += '; ' + LIMITS['oinm']
            if name in {'observed_bom_header','observed_bom_line','observed_production_issue'}:
                limitation += '; receta actual no acredita vigencia historica'
            if name == 'observed_observed_material_actual_consumption':
                limitation += '; doble prefijo del catalogo, no duplicar dato'
            rows.append(dict(dataset=name, domain=domain, component=component,
                contract_provenance=('FoundationAccess.reference(' + name[4:] + '); SAP/legacy/curacion, segun lineage publicado' if component == 'reference' else NATIVE[component]),
                existing_permission='telchi.' + permission + '.read.v1',
                previous_tier='A' if name in A else 'C' if name in C else 'B',
                accreditation='READ_CONSUMER_EVIDENCE_V1' if name in A else 'BUSINESS_SCOPE_EXTENSION_PROPOSED',
                sourcepolicy='COMPATIBLE_UNIQUE_OWNER; whole_dataset=True; columns=None; exact_org_workspace',
                publication_evidence='CONFLICT_REVALIDATE_SELECTED_MANIFEST' if component == 'commercial_purpose' else 'INVENTORY_V1_REUSED_NOT_LIVE_CURRENT',
                limitations=limitation, security_exception='NONE_DEMONSTRATED', eligible='YES_PROPOSED_NOT_GRANTED'))
    assert len(expected) == len(rows) == 70
    assert {r['dataset'] for r in rows} == expected
    assert len({r['dataset'] for r in rows}) == 70
    assert Counter(r['previous_tier'] for r in rows) == {'A':14,'B':41,'C':15}
    assert len({r['existing_permission'] for r in rows}) == 12
    assert all(re.fullmatch(r'telchi\.[a-z_.]+\.read\.v1', r['existing_permission']) for r in rows)
    # All proposed anchors have a source-code declaration, not an invented permission.
    code = (MODULE/'datalake/operational_query.py').read_text()
    for metric in {p for p, _, _, _ in GROUPS} - {'products.search','sales.commercial_line_amount_by'}:
        assert "'" + metric + "'" in code
    for path, permission in [('datalake/product_sales_query.py','telchi.products.search.read.v1'),
                             ('datalake/commercial_line_amount_by_query.py','telchi.sales.commercial_line_amount_by.read.v1')]:
        assert permission in (MODULE/path).read_text()
    # Local metadata only. Retain column names/types and footer row counts, no values.
    schemas = {}
    with duckdb.connect(config={'threads':1, 'memory_limit':'128MB'}) as db:
        for r in rows:
            if r['component'] != 'reference':
                continue
            paths = sorted((REFERENCE/r['dataset'][4:]).glob('*.parquet'))
            assert paths
            schema = db.execute('DESCRIBE SELECT * FROM read_parquet(?)', [[str(p) for p in paths]]).fetchall()
            footer = db.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)', [[str(p) for p in paths]]).fetchone()[0]
            schemas[r['dataset']] = {'columns': [{'name':c[0], 'type':c[1]} for c in schema], 'footer_rows':footer}
            r['reference_footer_rows'] = footer
            r['reference_empty'] = footer == 0
    forbidden = re.compile(r'password|passwd|secret|token|credential|private_key', re.I)
    assert not any(forbidden.search(c['name']) for s in schemas.values() for c in s['columns'])
    rows.sort(key=lambda r:r['dataset'])
    fields = list(rows[0]) + ['reference_footer_rows','reference_empty']
    fields = list(dict.fromkeys(fields))
    with (OUT/'matrix.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    evidence = dict(validation='PASS_OFFLINE_PROPOSAL_NOT_AUTHORIZATION',
        foundation_sources=70, eligible_proposed=70, proven_exclusions=0,
        data_quality_limitations=70, existing_permission_anchors=12,
        existing_consumer_evidence=14, proposed_contract_extensions=56,
        sourcepolicy_mapping_gaps=0, publication_provenance_conflicts=5,
        reference_version=REFERENCE.name, reference_schemas=schemas,
        reference_empty_datasets=[k for k,v in schemas.items() if v['footer_rows']==0],
        permissions=sorted({r['existing_permission'] for r in rows}),
        permission_registration_evidence='PRESIDENCIA_ACCREDITATION_V1.md prior DEV read; not re-queried',
        current_resolved_live=False, postgres_connections=0, grants_written=0,
        policies_published=0, new_roles=0, new_services=0,
        matrix_sha256=hashlib.sha256((OUT/'matrix.csv').read_bytes()).hexdigest())
    (OUT/'validation.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k not in {'reference_schemas','permissions'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
