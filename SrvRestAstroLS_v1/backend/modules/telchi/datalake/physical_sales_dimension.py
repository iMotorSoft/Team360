"""Physical dimension for the existing commercial-line query, not a sales engine.

No inferred classifications, header allocation, currency conversion or historical
validity. Enrich only a previously guarded line universe using canonical identity.
"""
from decimal import Decimal, localcontext

from .messaging_sales_query import TelchiQueryError

LABELS = {'LIQUID': 'Líquido', 'SEMISOLID': 'Semisólido', 'SOLID': 'Sólido',
          'UNCLASSIFIED': 'Ninguna (código 0)', 'MISSING': 'Sin valor observado',
          'MEDICINE': 'Medicamento (no es estado físico)', 'NOT_APPLICABLE': 'No corresponde',
          'UNKNOWN': 'Código desconocido', 'IDENTITY_MISSING': 'Identidad no resuelta'}
EXPLICIT = {'LIQUID', 'SEMISOLID', 'SOLID'}
OBSERVATION_WARNING = ('Clasificación física observada en octubre de 2026, no necesariamente vigente '
                       'en la fecha de cada factura. Códigos 4 y 5 no son estados físicos.')


def enrich(con, cte, args, products, crosswalk):
    """Preserve each line, including missing identities and unobserved products."""
    p = f"(SELECT * FROM {products} WHERE source_system='SAP_HANA')"
    x = f"(SELECT * FROM {crosswalk} WHERE source_system='SAP_HANA')"
    bad = con.execute(f'''SELECT
        (SELECT count(*) FROM (SELECT source_native_id FROM {x} GROUP BY ALL HAVING count(*)<>1)),
        (SELECT count(*) FROM {x} WHERE source_native_id IS NULL OR canonical_id IS NULL),
        (SELECT count(*) FROM (SELECT canonical_product_id FROM {p} GROUP BY ALL HAVING count(*)<>1)),
        (SELECT count(*) FROM {p} WHERE canonical_product_id IS NULL)''').fetchone()
    if any(bad):
        raise TelchiQueryError('physical_identity_integrity_failed')
    # Original joins and guards remain upstream, and monetary membership does
    # not depend on whether a physical value exists. No inner join can lose it.
    head, tail = cte.rsplit('joined AS (', 1)
    return head + 'commercial_joined AS (' + tail + f''', joined AS (
      SELECT j.*,x.canonical_id physical_canonical_id,
        p.sap_forma_farmac_code physical_code,p.physical_classification_observed_at physical_observed_at,
        CASE WHEN x.canonical_id IS NULL OR p.canonical_product_id IS NULL THEN 'IDENTITY_MISSING'
             WHEN p.sap_forma_farmac_code='1' THEN 'LIQUID'
             WHEN p.sap_forma_farmac_code='2' THEN 'SEMISOLID'
             WHEN p.sap_forma_farmac_code='3' THEN 'SOLID'
             WHEN p.sap_forma_farmac_code='0' THEN 'UNCLASSIFIED'
             WHEN p.sap_forma_farmac_code='4' THEN 'MEDICINE'
             WHEN p.sap_forma_farmac_code='5' THEN 'NOT_APPLICABLE'
             WHEN p.sap_forma_farmac_code IS NULL OR trim(p.sap_forma_farmac_code)='' THEN 'MISSING'
             ELSE 'UNKNOWN' END physical_key
      FROM commercial_joined j LEFT JOIN {x} x ON x.source_native_id=j.item_code
      LEFT JOIN {p} p ON p.canonical_product_id=x.canonical_id)''', args


def validate_profile(value, full, total):
    """The worker cannot invent coverage, a daily series or product rankings."""
    def fail():
        raise ValueError('invalid_physical_profile')
    with localcontext() as ctx:
        ctx.prec = 50
        sums = {r['key']: Decimal(r['amount']) for r in full}
        audit = value.get('audit', [])
        if any(r.get('key') not in LABELS or not Decimal(r['amount']).is_finite()
               or any(type(r.get(k)) is not int or r[k] < 0 for k in ('line_count', 'product_count'))
               for r in audit):
            fail()
        if len({(r['key'], r['original_code']) for r in audit}) != len(audit):
            fail()
        for key, amount in sums.items():
            if sum((Decimal(r['amount']) for r in audit if r['key'] == key), Decimal(0)) != amount:
                fail()
        if set(r['key'] for r in audit) != set(sums):
            fail()
        for table, grain in (('daily', 'date'), ('products', 'item_code')):
            rows = value.get(table, [])
            if (any(r.get('key') not in sums or not Decimal(r['amount']).is_finite() for r in rows)
                    or len({(r['key'], r[grain]) for r in rows}) != len(rows)):
                fail()
            if any(sum((Decimal(r['amount']) for r in rows if r['key'] == k), Decimal(0)) != a
                   for k,a in sums.items()):
                fail()
        classified = sum((a for k,a in sums.items() if k in EXPLICIT), Decimal(0))
        counts = dict(line_count=sum(r['line_count'] for r in audit),
                      product_count=sum(r['product_count'] for r in audit),
                      classified_line_count=sum(r['line_count'] for r in audit if r['key'] in EXPLICIT),
                      classified_product_count=sum(r['product_count'] for r in audit if r['key'] in EXPLICIT))
        if (any(value.get(k) != v for k,v in counts.items())
                or counts['line_count'] != total['line_count'] or counts['product_count'] != total['product_count']
                or Decimal(value['classified_amount']) != classified
                or Decimal(value['without_explicit_amount']) != Decimal(total['amount'])-classified):
            fail()
        percent = lambda a,b: str(Decimal(a)*100/Decimal(b)) if Decimal(b) else None
        expected = dict(amount=percent(classified,total['amount']),
                        lines=percent(counts['classified_line_count'],counts['line_count']),
                        products=percent(counts['classified_product_count'],counts['product_count']))
        if value.get('coverage_percent') != expected:
            fail()
    return value


def profile(con, cte, args, *, category=None):
    """Exact coverage and auditable daily/product breakdown of the same universe."""
    scope = ' WHERE category=?' if category is not None else ''
    args = list(args) + ([category] if category is not None else [])
    rows = con.execute(cte + f''' SELECT physical_key,physical_code,
        SUM(CAST(line_total AS DECIMAL(38,6))),count(*),count(DISTINCT item_code),
        min(physical_observed_at),max(physical_observed_at)
        FROM joined{scope} GROUP BY 1,2 ORDER BY 1,2''', args).fetchall()
    audit = [dict(key=k, original_code=code, amount=str(a), line_count=n, product_count=p,
                  observed_from=first, observed_to=last) for k,code,a,n,p,first,last in rows]
    with localcontext() as ctx:
        ctx.prec = 50
        total = sum((Decimal(r['amount']) for r in audit), Decimal(0))
        classified = sum((Decimal(r['amount']) for r in audit if r['key'] in EXPLICIT), Decimal(0))
        lines = sum(r['line_count'] for r in audit)
        explicit_lines = sum(r['line_count'] for r in audit if r['key'] in EXPLICIT)
        products = sum(r['product_count'] for r in audit)
        explicit_products = sum(r['product_count'] for r in audit if r['key'] in EXPLICIT)
        percent = lambda a,b: str(a * Decimal(100) / b) if b else None
        coverage = dict(amount=percent(classified,total), lines=percent(Decimal(explicit_lines),Decimal(lines)),
                        products=percent(Decimal(explicit_products),Decimal(products)))
    daily = con.execute(cte + f''' SELECT doc_date,physical_key,SUM(CAST(line_total AS DECIMAL(38,6)))
        FROM joined{scope} GROUP BY 1,2 ORDER BY 1,2''', args).fetchall()
    ranking = con.execute(cte + f''' SELECT physical_key,item_code,SUM(CAST(line_total AS DECIMAL(38,6))) amount
        FROM joined{scope} GROUP BY 1,2 ORDER BY 1,3 DESC,2''', args).fetchall()
    return dict(audit=audit, classified_amount=str(classified), without_explicit_amount=str(total-classified),
                product_count=products, classified_product_count=explicit_products,
                line_count=lines, classified_line_count=explicit_lines, coverage_percent=coverage,
                observation_warning=OBSERVATION_WARNING,
                daily=[dict(date=d,key=k,amount=str(a)) for d,k,a in daily],
                products=[dict(key=k,item_code=i,amount=str(a)) for k,i,a in ranking])
