"""Semántica de diferencia: magnitud, signo, variación y participación.

El contrato local `MONETARY_COMPARISON` debe distinguir cuatro operaciones que
no son intercambiables: diferencia con signo (`difference`), diferencia
absoluta (`absolute_difference`), variación porcentual (`percent`) y
participación porcentual (`ratio_percent`). Una pregunta por «diferencia
absoluta» nunca se responde con un importe negativo, y toda respuesta separa
la magnitud del cambio de su dirección.
"""
from copy import deepcopy
from decimal import Decimal

import pytest

from modules.telchi.assistant import monetary_comparison as mc
from modules.telchi.datalake.sales_query import MONETARY_OPERATION as OP, MONETARY_PERMISSION as GRANT

from .test_commercial_scope_closure import AUGUST, SEPTEMBER, executed_breakdown

OWNER = ['dev', 'telchi', 'workspace', 'channel', 'user']
DEFINITION = 'net documentary sales'
PUBLICATION = dict(publication_id='foundation_fixture', snapshot_id='1408',
                   updated_at='2026-11-04T13:55:47.173006+00:00')


def operand(result_id, amount, period, **overrides):
    window = dict(date_from=period['start'], date_to_exclusive=period['end_exclusive'])
    return dict(
        result_id=result_id, owner=deepcopy(OWNER), capability=OP + '.v1',
        required_permission=GRANT, metric='net_amount', measure_label='venta neta documental',
        currency='BS', definition=DEFINITION, source=deepcopy(PUBLICATION),
        period=window, amount=amount, partial=False, **overrides)


def comparison(target_id, baseline_id, mode):
    return dict(intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
                comparison=dict(target_id=target_id, baseline_id=baseline_id, mode=mode))


def operands(august='1000000.000000', september='971975.720000'):
    return [operand('turn-1#' + AUGUST['start'], august, AUGUST),
            operand('turn-1#' + SEPTEMBER['start'], september, SEPTEMBER)]


def test_absolute_difference_reports_the_positive_magnitude():
    results = operands()
    record, text = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                           'turn-1#' + AUGUST['start'], 'absolute_difference'),
                                results, OWNER)
    assert record['value'] == '28024.280000'
    assert record['reported'] == 'absolute'
    # La magnitud es positiva aunque la resta matemática sea negativa.
    assert record['difference'] == '-28024.280000'
    assert record['absolute_difference'] == '28024.280000'
    assert record['direction'] == 'baseline_higher'
    assert 'Diferencia absoluta' in text
    assert 'BS 28.024,28' in text
    assert 'BS -28.024,28' not in text
    assert 'es menor que' in text  # dirección explícita


def test_signed_difference_keeps_the_sign_and_also_declares_direction():
    record, text = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                           'turn-1#' + AUGUST['start'], 'difference'),
                                operands(), OWNER)
    assert record['value'] == '-28024.280000'
    assert record['reported'] == 'signed'
    assert record['difference'] == '-28024.280000'
    assert record['absolute_difference'] == '28024.280000'
    assert 'BS -28.024,28' in text
    assert 'magnitud: BS 28.024,28' in text
    assert 'es menor que' in text


def test_target_higher_than_baseline_declares_the_opposite_direction():
    record, text = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                           'turn-1#' + AUGUST['start'], 'absolute_difference'),
                                operands(august='100.000000', september='250.500000'), OWNER)
    assert record['direction'] == 'target_higher'
    assert record['value'] == '150.500000'
    assert 'es mayor que' in text


def test_equal_operands_have_zero_absolute_difference_and_no_direction():
    record, text = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                           'turn-1#' + AUGUST['start'], 'absolute_difference'),
                                operands(august='1234.560000', september='1234.560000'), OWNER)
    assert record['direction'] == 'equal'
    assert record['value'] == '0.000000'
    assert record['absolute_difference'] == '0.000000'
    assert 'ambos valores son iguales' in text


def test_percent_is_variation_and_never_labelled_as_a_difference():
    record, text = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                           'turn-1#' + AUGUST['start'], 'percent'),
                                operands(), OWNER)
    assert record['value'] == record['percent']
    assert record['reported'] == 'signed'
    assert 'Variación porcentual' in text
    assert 'Diferencia' not in text


def test_participation_of_components_is_not_period_variation():
    shared = dict(components=dict(billed_amount='1000.000000',
                                  credit_amount='0.000000', net_amount='1000.000000'))
    results = [operand('turn-1', '1000.000000', AUGUST,
                       components=dict(shared['components'], credit_amount='250.000000'))]
    share, share_text = mc.calculate(dict(
        intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
        comparison=dict(target_id='turn-1', baseline_id='turn-1', target_field='credit_amount',
                        baseline_field='billed_amount', mode='ratio_percent')), results, OWNER)
    assert share['formula'] == 'target / baseline * 100'
    assert 'sobre facturación: 25,00 %' in share_text
    assert 'Variación' not in share_text


def test_components_absolute_difference_is_a_magnitude():
    results = [operand('turn-1', '1000.000000', AUGUST,
                       components=dict(billed_amount='1000.000000',
                                       credit_amount='1250.500000', net_amount='-250.500000'))]
    record, text = mc.calculate(dict(
        intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
        comparison=dict(target_id='turn-1', baseline_id='turn-1', target_field='net_amount',
                        baseline_field='billed_amount', mode='absolute_difference')),
        results, OWNER)
    assert record['difference'] == '-1250.500000'
    assert record['absolute_difference'] == '1250.500000'
    assert record['value'] == '1250.500000'
    assert 'Diferencia absoluta entre neto documental y facturación: BS 1.250,50' in text


def test_every_mode_preserves_currency_and_exact_decimal_precision():
    results = operands(august='1000000.100000', september='999999.900000')
    for mode, expected in (('difference', '-0.200000'),
                           ('absolute_difference', '0.200000'),
                           ('percent', None)):
        record, _ = mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                            'turn-1#' + AUGUST['start'], mode), results, OWNER)
        assert record['target']['currency'] == 'BS'
        assert record['difference'] == '-0.200000'
        assert record['absolute_difference'] == '0.200000'
        if expected is not None:
            assert Decimal(record['value']) == Decimal(expected)


def test_unknown_mode_is_rejected_instead_of_silently_signed():
    for mode in ('magnitude', 'abs', ''):
        with pytest.raises(ValueError, match='ambiguous_comparison'):
            mc.calculate(comparison('turn-1#' + SEPTEMBER['start'],
                                    'turn-1#' + AUGUST['start'], mode), operands(), OWNER)


def test_followup_over_persisted_operands_reports_absolute_difference():
    """El seguimiento real reutiliza los dos períodos persistidos, sin consulta."""
    from modules.telchi.assistant.monetary_comparison import accredited_results
    audit = executed_breakdown()
    results = accredited_results(audit, 'turn-1', audit['owner'])
    august, september = (r['result_id'] for r in results)
    record, text = mc.calculate(comparison(september, august, 'absolute_difference'),
                                results, audit['owner'])
    assert record['absolute_difference'] == '28024.280000'
    assert record['difference'] == '-28024.280000'
    assert record['direction'] == 'baseline_higher'
    assert 'BS 28.024,28' in text and 'septiembre de 2026' in text