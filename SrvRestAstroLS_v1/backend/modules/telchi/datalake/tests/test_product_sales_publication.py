"""Products and sales-by-products admit CURRENT through canonical succession.

The regression of 08/11/2026 was a literal hash pin: the capability kept
``foundation_38680850…`` while CURRENT was a legitimately accredited successor.
A publication must be admitted by ancestry, never by a hardcoded equality.
"""
import os
from decimal import Decimal

import pytest

from modules.telchi.datalake import product_sales_query as products
from modules.telchi.datalake.sales_succession import ROOT_SNAPSHOT, SALES_ROOT

LIVE = os.environ.get('TELCHI_LIVE_PRODUCT_SALES') == '1'


def current_source(publication='foundation_c0b08df908d3485c8668788933826f7c', snapshot=1408):
    return dict(publication_id=publication, snapshot_id=snapshot,
                updated_at='2026-11-04T00:25:42.973000',
                reference_version='v2_sales_448ae93a960bf7342564a2d0')


def search_result(source, rows=None):
    return dict(capability='products.search.v1', parameters={'text': 'soda caustica', 'limit': 20},
                rows=rows or [], source=source, read_only=True, sap_accessed=False,
                truncated=False, product_summary=[], grain='catalog_product', limitations='x')


def test_legacy_accreditation_root_still_replays_sealed_results():
    assert (products.PUBLICATION, products.SNAPSHOT) == (SALES_ROOT, ROOT_SNAPSHOT)
    products.validate_result('products.search', {'text': 'soda caustica', 'limit': 20},
                             search_result(dict(publication_id=SALES_ROOT, snapshot_id=ROOT_SNAPSHOT)))


def test_a_wrong_snapshot_is_never_accepted():
    with pytest.raises(ValueError):
        products.validate_result('products.search', {'text': 'soda caustica', 'limit': 20},
                                 search_result(dict(publication_id=SALES_ROOT, snapshot_id=999)))


def test_result_contract_is_structural_for_application_owned_context():
    # Persisted product_context is validated without catalog I/O; execution is
    # where canonical admission is proved.
    products.validate_result('products.search', {'text': 'soda caustica', 'limit': 20},
                             search_result(current_source()), accredit=False)


@pytest.mark.skipif(not LIVE, reason='set TELCHI_LIVE_PRODUCT_SALES=1 for CURRENT read-only')
def test_live_publication_compatibility_and_both_operations():
    compatibility = products.publication_compatibility()
    assert compatibility['compatible'] is True
    assert compatibility['operations'] == ['products.search', 'sales.by_products']
    source = compatibility['source']
    assert source['publication_id'].startswith('foundation_')
    assert source['snapshot_id'] == ROOT_SNAPSHOT

    catalog = products.execute_query('products.search', {'text': 'L01010', 'limit': 20})
    assert catalog['source'] == source
    assert [r['item_code'] for r in catalog['rows']][:1] == ['L01010']

    lines = products.execute_query('sales.by_products', {
        'namespace': 'SAP_HANA', 'item_codes': ['L01010'],
        'date_from': '2026-10-01', 'date_to_exclusive': '2026-11-01', 'limit': 50})
    assert lines['source'] == source
    assert lines['product_summary'][0]['item_code'] == 'L01010'
    assert lines['product_summary'][0]['line_count'] == len(lines['rows']) > 0
    assert all(r['item_code'] == 'L01010' for r in lines['rows'])
    assert all(Decimal(r['quantity']).is_finite() for r in lines['rows'])