"""Reproducible cross-checks plus explicit manual business verdicts for V1.

Not an autonomous semantic evaluator. Verdicts refer to delivered answers, never
model_answer. Replays do not count as new blinded questions.
"""
import csv
import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path('../../data/reports/telchi/sales-reliability-v1')


def main():
    independent = json.loads((ROOT/'independent-sql-final.json').read_text())
    controls = {c['name']: c['rows'] for c in independent['controls']}
    loaded = {}
    def case(file, index):
        if file not in loaded:
            loaded[file] = json.loads((ROOT/file).read_text())
        return loaded[file]['cases'][index]
    def money(value):
        return format(Decimal(str(value)), ',.2f').replace(',', '_').replace('.', ',').replace('_', '.')
    comparisons = []
    def check(name, passed, **details):
        comparisons.append(dict(name=name, passed=bool(passed), **details))
        assert passed, (name, details)
    for file, index, control, key in (
        ('live-delivery-final.json', 0, 'sulfate25_ranking', 'card_code'),
        ('live-delivery-final.json', 1, 'nitric_ranking', 'card_code'),
        ('live-delivery-final.json', 7, 'soda1_heldout_ranking', 'card_code')):
        answer = case(file,index)['answer']; expected = controls[control][0]
        check(control, expected[key] in answer and money(expected['amount']) in answer,
              expected=expected, evidence=f'{file}#/cases/{index}')
    answer = case('live-delivery-final.json',2)['answer']
    expected = {r['card_code'] for r in controls['soda25_exclusion']}
    delivered = set(re.findall(r'^\d+\. card_code=([^,]+)', answer, re.M))
    check('soda25_account_difference_exact', delivered == expected,
          expected=sorted(expected), delivered=sorted(delivered),
          least_october_account=controls['soda25_exclusion'][0])
    answer = case('live-delivery-final.json',8)['answer']
    expected = controls['sulfate25_exclusion_heldout']
    delivered = set(re.findall(r'^\d+\. card_code=([^,]+)', answer, re.M))
    check('heldout_sulfate_difference_exact', delivered == {r['card_code'] for r in expected}
          and all(money(r['amount']) in answer for r in expected), expected=expected,
          delivered=sorted(delivered))
    check('sum_zero_happens_to_equal_no_purchase_in_this_fixture',
          not controls['sulfate_october_zero_amount_buyers'],
          limitation='Final Luna SQL used sum=0 instead of count=0. No zero-sum buyers observed; this equivalence is NOT generally safe.')
    answer = case('live-residual-final.json',0)['answer']
    for sku in ('L01010','L01013','L01015'):
        expected = controls['quantity_'+sku][0]
        check('quantity_'+sku, expected['card_code'] in answer and money(expected['quantity']) in answer,
              expected=expected)
    for index, month in ((1,'2026-10'),(2,'2026-09')):
        c = case('live-exclusion-final.json',index)
        expected = controls['customer_products_'+month]
        displayed = re.findall(r'^([A-Z][A-Za-z0-9_.-]+) ·', c['answer'], re.M)
        wanted = [r['item_code'] for r in expected if r['item_code'] != 'L01058'][:5]
        result = c['audit']['execution_result']
        total = sum((Decimal(r['amount']) for r in expected), Decimal(0))
        check('presentation_exclusion_'+month, displayed == wanted
              and Decimal(result['total']['amount']) == total
              and result['parameters']['filters'].get('product') is None,
              delivered=displayed, expected=wanted, unchanged_universe_total=str(total))
    c = case('live-exclusion-final.json',3)
    expected = controls['customer_products_two_months']
    shown = set(re.findall(r'^\d+\. item_code=([^,]+)',c['answer'],re.M))
    all_other = {r['item_code'] for r in expected if r['item_code']!='L01058'}
    queries = c['research_evidence']['queries']
    check('investigative_presentation_exclusion_not_data_filter', 'L01058' not in shown
          and shown <= all_other and 'L01058' not in queries[0]['sql'],
          expected_rows=len(all_other), delivered_rows=len(shown), omitted=sorted(all_other-shown),
          limitation='Channel guard still omits rows; no COMPLETE verdict.')
    (ROOT/'comparison.json').write_text(json.dumps(dict(
        foundation=independent['foundation'], comparisons=comparisons,
        status='NUMERIC_AND_SET_CONTROLS_MATCH; BUSINESS_LIMITATIONS_IN_MATRIX'),
        ensure_ascii=False,indent=2)+'\n')
    # Manual verdicts explicitly separate business completeness from runtime labels.
    rows = [
        ('P01','live-delivery-final.json',0,'COMPLETE','SI','L01772: 1 SKU, 13 cuentas; top verificado','Líder exacto del universo publicado; lista no exhaustiva declarada','AGROZA C011812 BS 32625.00; control sulfate25_ranking'),
        ('F01','live-delivery-final.json',1,'PARTIAL','SI_PARA_LIDER','6 SKU nominales acreditados; 594 cuentas en control','Líder correcto; cobertura fuente no entregada y respuesta declara pendientes','AVICOLA SOFIA BS 127411.50. Una repetición previa fue ERROR por delta set/unset incompatible; no cierre de robustez'),
        ('E01','live-delivery-final.json',2,'COMPLETE','SI','L01010; 7 cuentas octubre menos septiembre','7/7 entregadas; ausencia en septiembre verificada por anti-join','Runtime PARTIAL excesivamente cauteloso; conclusión de conjunto correcta para filas publicadas'),
        ('E02','live-delivery-final.json',3,'BLOCKED','NO','Lista anterior correcta existe, pero referencia no resuelta','No responde menor importe','Control: BATEBOL C001077 BS 380.63; Luna pide referencia. Sin cambio de routing'),
        ('Q01','live-residual-final.json',0,'COMPLETE','SI','3 SKU, 3 rankings independientes; unidades no convertidas','3/3 primeras cuentas y cantidades entregadas; no líder físico global','25kg C012227=12000; 1kg CG2A=485; 500g C011863=54. Guarda omite detalles duplicados; líderes conservados. Corridas previas parciales retenidas'),
        ('L01','live-residual-final.json',1,'PARTIAL','PARCIAL','6 SKU correctos; 311 cuentas distintas en control','SQL LIMIT 100; divulga 30; canal entrega menos; universo restante no enumerado','Ya no confunde OR con comprar cada SKU, pero no reúne/entrega lista completa; versiones previas con ALL se conservan'),
        ('R01','live-corrections.json',6,'COMPLETE','SI','4502 productos en universo comercial de octubre','Top 3 solicitado, no listado completo','Control top3: L01772 321087.74; L01010 247286.63; L00504 247228.01. Evidencia reutilizada: NEW_QUERY sin exclusiones no afectado por ajustes posteriores'),
        ('G01','live-corrections.json',7,'BLOCKED','NO','Ranking global; contrato de exclusión actual exige cliente','No ejecuta ni responde exclusión solicitada','EXECUTION_FORBIDDEN; no se amplía capability ni state schema'),
        ('G02','live-corrections.json',8,'BLOCKED','NO','Exclusión global anterior nunca confirmada','No se resuelve seguimiento','Pide referencia; bloqueo residual, no PASO correcto'),
        ('C01','live-exclusion-final.json',0,'PARTIAL','PARCIAL','C000143; 24 SKU, total BS 115819.19','Solo primer producto y resto agregado; no lista completa','Baseline rápido conservado; no declarar que mostró todos los productos'),
        ('C02','live-exclusion-final.json',1,'COMPLETE','SI','C000143 octubre; excluir L01058 solo de presentación','Página de 5 correcta; total y filtros de datos sin cambios','Exclusión sobrevivió código SAP y nombre; continuidad ofrecida, no exhaustividad global'),
        ('C03','live-exclusion-final.json',2,'COMPLETE','SI','C000143 septiembre; misma exclusión de presentación','Página de 5 correcta; total BS 55541.67 no depurado','Refinamiento mensual conserva L01058 oculto y no lo elimina del universo SQL'),
        ('C04','live-exclusion-final.json',3,'PARTIAL','PARCIAL','C000143 septiembre-octubre; 25 SKU, 24 tras ocultar L01058','Filtro cliente/período conservado; ocultación no se convierte en WHERE; guarda omite filas','Importes visibles coinciden con control; no se entrega toda la lista ni explicación precisa de omisiones'),
        ('H01','live-delivery-final.json',7,'COMPLETE','SI','1 SKU de 1kg, L01013; 111 cuentas; 25kg y 500g fuera','Líder exacto acreditado sin fusionar CONTROL TRIBUTARIO','Pregunta nueva: CG2A BS 4462.24; sin corrección específica de producto'),
        ('H02','live-delivery-final.json',8,'PARTIAL','SI_EN_DATOS_ACTUALES','L01772; 7 cuentas septiembre menos octubre','7 cuentas/importes coinciden; última SQL usa sum octubre=0, no ausencia de líneas','Primer intento reservado usó count=0 correctamente; última repetición cambia predicado. Control no encuentra compradores con suma cero, pero esa equivalencia no es garantía general'),
    ]
    header=['id','pregunta','respuesta_correcta','universo_acreditado','completitud','resultado','segundos','causa_o_limite','evidencia']
    with (ROOT/'matrix.tsv').open('w') as out:
        writer=csv.writer(out,delimiter='\t');writer.writerow(header)
        for ident,file,index,status,correct,universe,complete,cause in rows:
            c=case(file,index)
            writer.writerow([ident,c['question'],correct,universe,complete,status,c['elapsed_seconds'],cause,f'{file}#/cases/{index}'])
    print('Business matrix:', {s:sum(r[3]==s for r in rows) for s in ('COMPLETE','PARTIAL','BLOCKED')})


if __name__ == '__main__':
    main()
