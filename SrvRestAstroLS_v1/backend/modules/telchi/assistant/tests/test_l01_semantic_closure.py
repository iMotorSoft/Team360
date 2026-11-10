"""Offline semantic closure of L01; no SQL, models, services or 15-case rerun."""
import json
from pathlib import Path

import pytest

from modules.telchi.exploratory_sql.ask_verifier import presentation_semantics
from .verify_l01_population import semantic_closure


def accredited_reconciliation():
    root = Path(__file__).resolve().parents[6]
    return json.loads((root / 'data/reports/telchi/l01-population-closure-v1/reconciliation.json').read_text())


def test_accredited_311_union_is_complete_not_business_or_calendar_certified():
    evidence = accredited_reconciliation()
    result = semantic_closure(evidence)
    assert result['SEMANTIC_OR'] == 'PASS'
    assert result['POPULATION_COVERAGE'] == 'COMPLETE'
    assert result['TEMPORAL_COVERAGE'] == 'NOT_CERTIFIED'
    assert result['BUSINESS_INTERPRETATION'] == 'NOT_INDEPENDENTLY_CERTIFIED'
    assert result['BLOCKER'] is None
    evidence['question_coverage'] = 'PARTIAL'
    evidence['model_answer'] = 'Cada cliente compró las seis presentaciones.'
    assert semantic_closure(evidence) == result
    evidence['BLOCKER'] = 'continuation_failed'
    assert semantic_closure(evidence)['BLOCKER'] == 'continuation_failed'


@pytest.mark.parametrize('field,value', [
    ('RECOVERED_ACCOUNTS', 100), ('DURABLE_RECORDS', 310), ('DUPLICATES', 1),
    ('RECONCILED_WITH_INDEPENDENT_SQL', False), ('DURABLE_RESULT', 'FAIL'),
    ('ACREDITED_ACCOUNTS', None),
])
def test_incomplete_or_unaccredited_accounting_cannot_be_complete(field, value):
    evidence = accredited_reconciliation()
    evidence[field] = value
    assert semantic_closure(evidence)['POPULATION_COVERAGE'] == 'NOT_CERTIFIED'


@pytest.mark.parametrize('question,expected', [
    ('ácido nítrico en todas sus presentaciones', 'SKU_UNION_OR'),
    ('Cada cliente que compró ácido nítrico en todas sus presentaciones', 'SKU_UNION_OR'),
    ('Clientes que compraron cada una de las presentaciones', 'PER_ACCOUNT_UNIVERSAL_REQUIRES_EVIDENCE'),
    ('Clientes que compraron todas y cada una de las presentaciones', 'PER_ACCOUNT_UNIVERSAL_REQUIRES_EVIDENCE'),
])
def test_family_union_is_not_universal_purchase(question, expected):
    assert presentation_semantics(question) == expected
