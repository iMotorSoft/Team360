"""Offline review of verified sales captures against the canonical pinned reader.

No HANA constructor, publication writes, or claims of period completeness.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation

from . import sales_incremental as inc
from . import sales_controlled_block as block

LINEAGE = {'source_as_of','raw_extraction_id','reference_version','reference_manifest_hash',
           'transformation_version','schema_version'}


NUMERIC = {'quantity','price','doc_total','doc_total_system','doc_total_foreign',
           'line_total','line_total_system','line_total_foreign'}


def canonical(value, *, numeric=False):
    if value is None:
        return None
    text = value.isoformat() if hasattr(value,'isoformat') else str(value)
    if numeric:
        try:
            number = Decimal(text)
            if number.is_finite():
                return str(number.normalize())
        except InvalidOperation:
            pass
    return text


def compare_tables(incoming, previous, *, lines=False):
    def key(r):
        return (str(r['doc_entry']),str(r['line_num'])) if lines else str(r['doc_entry'])
    old, new = {key(r):r for r in previous}, {key(r):r for r in incoming}
    if len(old)!=len(previous) or len(new)!=len(incoming):
        raise ValueError('duplicate canonical keys')
    stats=Counter(new=0,modified=0,identical=0,removed=0)
    differences=Counter()
    for identity,row in new.items():
        if identity not in old:
            stats['new']+=1
            continue
        changes=[k for k in row if k not in LINEAGE and canonical(row[k],numeric=k in NUMERIC)!=canonical(old[identity].get(k),numeric=k in NUMERIC)]
        stats['modified' if changes else 'identical']+=1
        differences.update(changes)
    captured_documents={str(r['doc_entry']) for r in incoming}
    stats['removed']=sum(key not in new and str(r['doc_entry']) in captured_documents for key,r in old.items())
    return dict(counts=dict(stats),changed_fields=dict(differences))


def captured_rows(pilot_root, block_root):
    with inc.locked(pilot_root):
        inc.recover(pilot_root,inc.read_json(pilot_root/'plan.json'))
        pilot={d:inc.read_json(pilot_root/f'{d}.source.json') for d in inc.DOMAINS}
    units=block.recover(block_root)
    second={d:[] for d in inc.DOMAINS}
    for unit in units:
        second[unit['domain']].extend(r for page in unit['pages'] for r in inc.read_json(block_root/page))
    all_rows={d:pilot[d]+second[d] for d in inc.DOMAINS}
    for d,rows in all_rows.items():
        inc.validate_rows(d,rows,limit=100)
    return all_rows,second


def reconcile_on(connection, access, rows_by_domain):
    """Bounded native-document reads at one resolved Foundation snapshot."""
    report={}
    for domain,rows in rows_by_domain.items():
        candidate=inc.transform_capture(domain,rows,dict(extraction_id='offline-verified-sales',source_as_of=inc.now()))
        domain_report={}
        for table,incoming in candidate.tables.items():
            entries=sorted({str(r['doc_entry']) for r in incoming})
            if not entries:
                continue
            cursor=connection.execute(f'SELECT * FROM {access.relation(domain,table)} WHERE source_system=? AND doc_entry IN ({",".join("?" for _ in entries)})', ['SAP_B1_HANA',*entries])
            columns=[c[0] for c in cursor.description]
            previous=[dict(zip(columns,r)) for r in cursor.fetchall()]
            domain_report[table]=compare_tables(incoming,previous,lines=table.endswith('_line'))
        headers={int(r['DocEntry']):r for r in rows}
        currencies=sorted({r['DocCur'] for r in headers.values()})
        sample={}
        for currency in currencies:
            selected=[r for r in headers.values() if r['DocCur']==currency and str(r['DocDate']).startswith('2026-10')]
            sample[currency]=dict(documents=len(selected),header_total=str(sum((Decimal(str(r['DocTotal'])) for r in selected),Decimal(0))),
                header_tax=str(sum((Decimal(str(r['HeaderVatSum'])) for r in selected),Decimal(0))),
                cancellation_states=dict(Counter(r['CANCELED'] for r in selected)))
        domain_report.update(captured_documents=len(headers),captured_lines=len(rows),
            observed_doc_dates=[min(str(r['DocDate']) for r in rows),max(str(r['DocDate']) for r in rows)],
            october_sample_only=sample,monetary_reconciliation='Raw header total, VAT and discount retained exactly; canonical published business fields compared; header vs line-tax reconstruction NOT_ACCREDITED',
            limitations=['No full-period proof','No source transaction snapshot','Credit line discount/tax projection incomplete','Not net sales or collections'])
        # Resolve explicit source identities only, never infer product/client names.
        for dataset,source_key,ref_key in [('customers','CardCode','code'),('products','ItemCode','item_code')]:
            codes=sorted({str(r[source_key]) for r in rows if r.get(source_key)})
            cursor=connection.execute(f'SELECT DISTINCT {ref_key} FROM read_parquet(?) WHERE source_system=? AND {ref_key} IN ({",".join("?" for _ in codes)})',[str(access.reference(dataset)),'SAP_HANA',*codes])
            resolved={str(r[0]) for r in cursor.fetchall()}
            domain_report[dataset+'_resolution']=dict(captured=len(codes),resolved=len(resolved),missing_count=len(set(codes)-resolved))
        report[domain]=domain_report
    return report


def business_checks(publication, cutoff):
    questions=['Facturación de octubre','Ventas diarias','Principales clientes facturados',
               'Principales productos','Notas de crédito','Comparación con septiembre','Venta neta']
    return [dict(question=q,answer='Octubre aún no tiene cobertura publicada; la captura es una muestra parcial no publicada.',
                 period='2026-10-01/2026-10-31',cutoff=cutoff,currency='BS observed; no currency conversion',
                 publication=publication,candidate=None,coverage='PARTIAL_SAMPLE_ONLY',
                 status='BLOCKED_FOR_GENERAL_PERIOD_ANSWER',limitations='No monthly totals, rankings, net sales or September comparison from this sample.') for q in questions]
