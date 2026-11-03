"""Evidence gap decisions; use Foundation's existing purpose/UoM rules."""
from modules.telchi.datalake.product_commercial_semantics import classify_purpose, number


def purpose_decision(evidence, *, historical_documents):
    total = evidence['sales_documents'] + historical_documents
    result = classify_purpose(
        sell_item=evidence['sap_sell_item'], business_class=evidence['business_class'],
        class_status=evidence['classification_status'], classification_basis=evidence['classification_basis'],
        sales_documents=total, production_issue_lines=evidence['production_issue_lines'],
        bom_lines=evidence['bom_lines'])
    # Positive facts from different windows demonstrate observed mixed use.
    # They cannot establish exclusive use without operational coverage.
    if result['commercial_purpose'] == 'MIXED':
        return result, 'RESOLVABLE_FROM_EXISTING_DATALAKE', 'POSITIVE_COMMERCE_AND_ACTUAL_PRODUCTION_CONSUMPTION', []
    if total and not evidence['production_issue_lines']:
        return None, 'REQUIRES_DATALAKE_INGESTION', 'MISSING_PRODUCTION_CONSUMPTION', ['Historical OIGE/IGE1 BaseType=202 consumption and OWOR coverage matching historical invoices; resolved purpose for other inventory issues']
    if evidence['production_issue_lines']:
        reason = 'ISOLATED_COMMERCIAL_EVENT_PURPOSE_UNRESOLVED' if total else 'SELL_ENABLED_INTERNAL_USE_EXCLUSIVE_INTENT_UNPROVEN'
        return None, 'TRUE_BUSINESS_UNKNOWN', reason, ['Business intent for sell-enabled internally consumed product; historical/current activity cannot establish exclusive intent']
    if evidence['bom_lines']:
        return None, 'REQUIRES_DATALAKE_INGESTION', 'MISSING_PRODUCTION_CONSUMPTION', ['Historical OIGE/IGE1 BaseType=202 consumption; BOM is context only']
    return None, 'TRUE_BUSINESS_UNKNOWN', 'NO_OBSERVED_COMMERCIAL_OR_INTERNAL_USE', ['No positive use in materialized evidence; human purpose/retirement decision may be necessary']


def supported_factor(item, source_uom, inventory_uom, evidence):
    """No factor or unit substitution; conflicts are never averaged."""
    if not item or not source_uom or not inventory_uom:
        return None, 'MISSING_SOURCE_UOM_OR_INVENTORY_UOM'
    matching = [r for r in evidence if (r['item_code'], r['source_uom'], r['inventory_uom_id']) == (item, source_uom, inventory_uom)]
    factors = {number(r['conversion_factor']) for r in matching if r.get('document_key') and r.get('file_hash')}
    factors.discard(None)
    if len(factors) > 1:
        return None, 'UOM_CONVERSION_CONFLICT'
    if len(factors) == 1 and next(iter(factors)) > 0:
        return next(iter(factors)), 'UOM_RESOLVED_SUPPORTED'
    return None, 'SOURCE_NOT_MATERIALIZED'


def unique_events(rows, fields):
    keys = [tuple(str(r[k]) for k in fields) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('evidence fanout')
    return len(rows)


def rectangular_rows(rows):
    """Include Parquet null columns in the canonical prewrite row fingerprint."""
    columns = set().union(*(r.keys() for r in rows))
    return [{k: r.get(k) for k in columns} for r in rows]
