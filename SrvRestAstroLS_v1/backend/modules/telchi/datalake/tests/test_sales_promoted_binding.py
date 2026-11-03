"""Sales adapter must accept only the nominally promoted Foundation binding."""
import pytest

from modules.telchi.datalake import sales_query as sales

PUBLISHED = 'foundation_38680850adc058b1bb11887632b7b681'
PREVIOUS = 'foundation_afd08d9eca6a725be53cdc3f9d5709c9'


def envelope(start, end, billed, credit, net):
    options = dict(date_from=start, date_to_exclusive=end, currency='BS')
    result = dict(
        capability=sales.MONETARY_OPERATION + '.v1', period=options,
        currency='BS', grain='document_header', read_only=True, sap_accessed=False,
        sql_parameters=sales.parameters(sales.MONETARY_OPERATION, options),
        source=dict(publication_id=PUBLISHED, snapshot_id=1408,
                    updated_at='2026-10-30T09:01:30.323257+00:00'),
        rows=[dict(invoice_count=1, unique_invoices=1, invoice_amount_count=1,
                   credit_count=1, unique_credits=1, credit_amount_count=1,
                   billed_amount=billed, credit_amount=credit, net_amount=net)])
    return options, result


@pytest.mark.parametrize('args', [
    ('2026-09-01', '2026-10-01', '11079079.77', '488033.53', '10591046.24'),
    ('2026-10-01', '2026-10-30', '11269116.22', '457793.30', '10811322.92'),
])
def test_nominally_promoted_binding_accepted(args):
    options, result = envelope(*args)
    assert sales.validate_result(sales.MONETARY_OPERATION, options, result) is result


@pytest.mark.parametrize('publication', [PREVIOUS, 'foundation_unapproved'])
def test_stale_or_unapproved_binding_still_rejected(publication):
    options, result = envelope('2026-09-01', '2026-10-01', '100', '10', '90')
    result['source']['publication_id'] = publication
    with pytest.raises(ValueError, match='invalid_sales_result'):
        sales.validate_result(sales.MONETARY_OPERATION, options, result)
