"""BIZ01 continuity evaluator.

Reads the persisted runtime HTTP evidence of one conversation and judges it
turn by turn: what was inherited, what was interpreted, what was executed,
what was reconciled, what was answered and what risk was reported. The quality
of an answer is judged on the accredited data it carries, not on a literal
match with an expected sentence.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

JULY = dict(start='2026-07-01', end_exclusive='2026-08-01')
AUGUST = dict(start='2026-08-01', end_exclusive='2026-09-01')
WINDOW = dict(start='2026-07-01', end_exclusive='2026-09-01')

# What each turn must demonstrate. ``figures`` are the accredited amounts the
# answer has to carry; they are read from the execution result, not guessed.
EXPECTATIONS = {
    1: dict(capability='sales.period_billed_amount.v1', kind='monthly_billing',
            figures=[], scope=dict(period={'start': '2026-09-01', 'end_exclusive': '2026-10-01'})),
    2: dict(capability='sales.category_line_amount.v1', kind='category_lines',
            figures=[], scope=dict(category='LAB_FINISHED_PRODUCT'),
            forbidden=['es el total de ventas', 'igual a la facturación']),
    3: dict(capability='sales.product_line_amount_ranking.v1', kind='ranking',
            figures=[], scope=dict(category='LAB_FINISHED_PRODUCT', limit=5)),
    4: dict(capability='sales.product_line_amount_ranking.v1', kind='historical_position',
            figures=['271255.49', '314971.57'], scope=dict(product='L03281')),
    5: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_ranking',
            figures=['115044.44'], scope=dict(product='L03281', group_by='card_code',
                                               periods=[JULY, AUGUST], focus_customer='C000061')),
    6: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_months',
            figures=['72383.99', '42660.45'], scope=dict(product='L03281', customer='C000061',
                                                          focus_customer='C000061', group_by='card_code',
                                                          periods=[JULY, AUGUST])),
    7: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_products',
            figures=[], scope=dict(customer='C000061', focus_customer='C000061',
                                    group_by='sap_product', periods=[JULY, AUGUST])),
    8: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_share',
            figures=['115044.44', '586227.06'], scope=dict(product='L03281', customer='C000061',
                                                           focus_customer='C000061', group_by='card_code',
                                                           periods=[JULY, AUGUST])),
    9: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_ranking',
            figures=['115044.44'], scope=dict(product='L03281', group_by='card_code',
                                               periods=[JULY, AUGUST])),
    10: dict(capability='sales.commercial_line_amount_by.v1', kind='customer_months',
              figures=['72383.99', '42660.45'], scope=dict(product='L03281', group_by='card_code',
                                                            periods=[JULY, AUGUST])),
}


def _decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _scope_of(state):
    focus = state.get('focus') or {}
    return dict(category=state.get('business_category'), product=state.get('product_target'),
                customer=state.get('customer_target'), group_by=state.get('group_by'),
                periods=[dict(p) for p in (state.get('periods') or [])],
                period_mode=state.get('period_mode'), breakdown=state.get('breakdown_by'),
                focus_product=focus.get('product'), focus_customer=focus.get('customer'))


def _result_amounts(result):
    """Every amount the executed result carries, by label."""
    amounts = {}
    if not isinstance(result, dict):
        return amounts
    for row in result.get('rows') or []:
        if isinstance(row, dict):
            amounts.setdefault(str(row.get('key')), []).append(str(row.get('amount')))
            for part in row.get('periods') or []:
                amounts.setdefault(f"{row.get('key')}@{part.get('period', {}).get('start')}",
                                   []).append(str(part.get('amount')))
    total = result.get('total') or {}
    if total.get('amount') is not None:
        amounts['__total__'] = [str(total['amount'])]
    universe = result.get('universe_total') or {}
    if universe.get('amount') is not None:
        amounts['__universe__'] = [str(universe['amount'])]
    return amounts


def _figure_present(figure, amounts, text):
    wanted = _decimal(figure)
    if wanted is None:
        return False
    for values in amounts.values():
        for value in values:
            if _decimal(value) == wanted:
                return True
    # The answer must also carry the figure in its own words.
    formatted = f'{wanted:,.2f}'.translate(str.maketrans({',': '.', '.': ','}))
    return formatted in text


def evaluate_turn(index, turn):
    audit = turn.get('audit') or {}
    state = audit.get('confirmed_state') or {}
    scope = _scope_of(state)
    result = audit.get('execution_result') or {}
    text = turn.get('response_text') or ''
    expectation = EXPECTATIONS.get(index, {})
    amounts = _result_amounts(result)
    findings, failures = [], []

    classification = turn.get('classification')
    executed = audit.get('execution_status') == 'executed'
    capability = result.get('capability')

    if expectation.get('capability') and capability != expectation['capability']:
        failures.append(f"operación esperada {expectation['capability']}, ejecutada {capability!r}")
    if not executed:
        failures.append(f"no se ejecutó ninguna operación ({classification})")
    for figure in expectation.get('figures', []):
        if not _figure_present(figure, amounts, text):
            failures.append(f"importe acreditado {figure} ausente del resultado y de la respuesta")
    for forbidden in expectation.get('forbidden', []):
        if forbidden in text.lower():
            failures.append(f"la respuesta afirma {forbidden!r}")

    wanted = expectation.get('scope', {})
    if wanted.get('category') and scope['category'] != wanted['category']:
        failures.append(f"categoría {scope['category']!r} en vez de {wanted['category']!r}")
    if wanted.get('product') and scope['focus_product'] != wanted['product']:
        failures.append(f"producto en foco {scope['focus_product']!r} en vez de {wanted['product']!r}")
    if wanted.get('customer') and scope['customer'] != wanted['customer']:
        failures.append(f"cliente {scope['customer']!r} en vez de {wanted['customer']!r}")
    if wanted.get('focus_customer') and scope['focus_customer'] != wanted['focus_customer']:
        failures.append(f"cliente en foco {scope['focus_customer']!r} en vez de {wanted['focus_customer']!r}")
    if wanted.get('group_by') and scope['group_by'] != wanted['group_by']:
        failures.append(f"dimensión {scope['group_by']!r} en vez de {wanted['group_by']!r}")
    if wanted.get('periods') and scope['periods'] != [dict(p) for p in wanted['periods']]:
        failures.append(f"períodos {scope['periods']!r} en vez de {wanted['periods']!r}")
    if wanted.get('limit') and state.get('limit') != wanted['limit']:
        failures.append(f"límite {state.get('limit')!r} en vez de {wanted['limit']!r}")
    if wanted.get('period') and state.get('period') != wanted['period']:
        failures.append(f"período {state.get('period')!r} en vez de {wanted['period']!r}")

    # A turn that lost the product, the customer or the periods is a context loss.
    if index >= 5 and scope['focus_product'] != 'L03281':
        failures.append(f"producto en foco perdido: {scope['focus_product']!r}")
    if index >= 5 and scope['periods'] != [dict(JULY), dict(AUGUST)]:
        failures.append(f"conjunto de períodos perdido: {scope['periods']!r}")

    # The reconciliation of a commercial breakdown is tolerance zero.
    if capability == 'sales.commercial_line_amount_by.v1':
        reconciliation = result.get('reconciliation') or {}
        if _decimal(reconciliation.get('difference')) != 0:
            failures.append(f"reconciliación con diferencia {reconciliation.get('difference')!r}")

    # The authorization is per capability and re-validated by the service.
    if executed:
        if audit.get('business_rbac_verified') is not True:
            failures.append('la autorización comercial no quedó verificada')
        if not audit.get('required_permission'):
            failures.append('la operación no tiene permiso registrado')

    # The business answer first: a risk or a definition must be stated.
    if executed and capability == 'sales.commercial_line_amount_by.v1':
        if 'facturado en SAP' not in text:
            failures.append('la respuesta no define «cliente facturado en SAP»')
        if 'no está acreditada' not in text and 'acreditada' not in text:
            failures.append('la respuesta no advierte la limitación de la taxonomía de cliente')

    if not failures:
        findings.append(f"{expectation.get('kind')} ejecutado y acreditado")
    return dict(turn=index, question=turn.get('user_text'), classification=classification,
                executed=executed, capability=capability, scope=scope,
                reconciliation=(result.get('reconciliation') or {}).get('difference'),
                required_permission=audit.get('required_permission'),
                business_rbac_verified=audit.get('business_rbac_verified'),
                pass_=not failures, failures=failures, findings=findings,
                response=text)


def evaluate(results_path, scenario_id='BIZ01'):
    evidence = json.loads(Path(results_path).read_text())
    scenarios = [s for s in evidence.get('scenarios', []) if s.get('id') == scenario_id]
    if not scenarios:
        return dict(scenario=scenario_id, error='scenario_not_found', pass_=False)
    scenario = scenarios[0]
    turns = [evaluate_turn(index, turn) for index, turn in enumerate(scenario['turns'], 1)]
    correct = sum(1 for t in turns if t['pass_'])
    unjustified = sum(1 for t in turns if not t['executed'] and t['classification'] == 'DIRECT_UNAVAILABLE')
    context_loss = sum(1 for t in turns if any('perdido' in f for f in t['failures']))
    reconciliation = [t['reconciliation'] for t in turns if t['reconciliation'] is not None]
    authorization = all(t['business_rbac_verified'] for t in turns if t['executed'])
    return dict(
        run_id=evidence.get('run_id'), scenario=scenario_id, conversation=scenario.get('conversation'),
        turns=turns, turns_total=len(turns), turns_correct=correct,
        unjustified_unavailability=unjustified, context_loss=context_loss,
        monetary_reconciliation='PASS' if all(_decimal(v) == 0 for v in reconciliation) else 'FAIL',
        monetary_reconciliation_values=reconciliation,
        authorization='PASS' if authorization else 'FAIL',
        conversation_pass=bool(len(turns) == 10 and correct == 10 and context_loss == 0 and authorization
                               and all(_decimal(v) == 0 for v in reconciliation)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True)
    parser.add_argument('--scenario', default='BIZ01')
    parser.add_argument('--output', default=None)
    args = parser.parse_args()
    report = evaluate(args.results, args.scenario)
    payload = json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n'
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload)
    print(payload)


if __name__ == '__main__':
    main()
