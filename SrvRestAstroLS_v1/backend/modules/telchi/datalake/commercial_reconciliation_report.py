"""Generate candidate-only reconciliation evidence. Never publish or access SAP.

Run from backend: python -m modules.telchi.datalake.commercial_reconciliation_report
"""
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .commercial_purpose_reader import CommercialPurposeViews, DATASETS
from .commercial_purpose_candidate import validate_pinned_candidate
from .ducklake import DuckLakeConnector
from .foundation_manifest import validate_manifest
from .foundation_publication import FoundationPublicationStore

CANDIDATE = 'foundation_4b9d6ddca5c9dd17c09038b00e52e0c9'
OUTPUT = Path(__file__).resolve().parents[5] / 'data/reports/telchi/commercial-reconciliation-v1'


def records(cursor):
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def main():
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        @contextmanager
        def same():
            yield con
        store = FoundationPublicationStore(same)
        current = store.current_publication()
        candidate = store.get(CANDIDATE)
        if current is None or candidate is None:
            raise ValueError('EXACT_PUBLICATION_NOT_FOUND')
        before = current.manifest
        components = candidate.manifest['components']
        datasets = components['commercial_purpose']['datasets']
        physical = {}
        for name in DATASETS:
            entry = datasets[name]
            if len(entry['file_references']) != len(entry['file_hashes']):
                raise ValueError('FILE_HASH_COUNT_MISMATCH')
            for path, expected in zip(entry['file_references'], entry['file_hashes']):
                file = Path(path)
                actual = hashlib.sha256(file.read_bytes()).hexdigest()
                if actual != expected:
                    raise ValueError('CAPTURE_BYTES_CHANGED: ' + name)
                physical[str(file)] = actual
        errors = {}
        for name, check in [('canonical_manifest', lambda: validate_manifest(store, candidate)),
                            ('candidate_harness', lambda: validate_pinned_candidate(store, CANDIDATE))]:
            try:
                check()
            except ValueError as exc:
                errors[name] = str(exc)
            except RuntimeError as exc:
                errors[name] = str(exc)
        missing = sorted(set(before['components']) - set(components))
        changed = sorted(k for k in before['components'] if k in components
                         and before['components'][k] != components[k])
        cutoffs = {}
        for name in DATASETS:
            complete = Path(datasets[name]['file_references'][0]).parents[3] / 'complete.json'
            payload = json.loads(complete.read_text())
            cutoffs[name] = {k: payload[k] for k in ('source_before', 'source_after', 'observation')}
        reader = CommercialPurposeViews(datasets=datasets)
        try:
            c = reader.con
            categories = records(reader.conversion_category_counts())
            products = records(reader.top_products_unconverted())
            clients = records(reader.clients_for_top_products())
            outside = records(c.execute('''SELECT i."DocEntry",i."LineNum",i."BaseType",i."BaseEntry",i."BaseLine",
                i."ItemCode",i."LineTotal" FROM invoices_from_quotations i
                WHERE NOT EXISTS (SELECT 1 FROM quotation_document_links l JOIN qut1_october_2026 q
                    ON q."DocEntry"=l.qdoc AND q."LineNum"=l.qline
                    WHERE l.obj=13 AND l.doc=i."DocEntry" AND l.line=i."LineNum")
                ORDER BY i."DocEntry",i."LineNum"'''))
            multi = records(c.execute('''SELECT l.qdoc,l.qline,count(*) InvoiceLines,
                list(struct_pack(doc:=l.doc,line:=l.line)) InvoiceKeys
                FROM quotation_document_links l JOIN qut1_october_2026 q
                  ON q."DocEntry"=l.qdoc AND q."LineNum"=l.qline
                WHERE obj=13 GROUP BY l.qdoc,l.qline HAVING count(*)>1'''))
            report = dict(candidate=CANDIDATE, generated_at=datetime.now(timezone.utc).isoformat(),
                publication='BLOCKED_FUNCTIONAL_GATE', current=current.foundation_publication_id,
                canonical_validation_errors=errors, missing_inherited_components=missing,
                changed_inherited_components=changed,
                catalog_base_component_count=5, current_logical_component_count=len(before['components']),
                candidate_logical_component_count=len(components), required_logical_component_count=len(before['components'])+1,
                reconciliation=reader.reconciliation, categories=categories,
                multi_invoice_quotations=multi, outside_scope_invoices=outside,
                original_report=dict(category_lines=13801, category_budgeted='9449080.51',
                    converted_category_budgeted='3809982.47', invoiced='3811629.97',
                    invoiced_minus_category_budgeted='1647.50'),
                correction=dict(extra_quote_count=1, repeated_quote_budget='204.00',
                    correct_converted_quote_budget='3809778.47',
                    invoiced_minus_correct_converted_quote_budget='1851.50'),
                amount_basis='BS local net LineTotal; no header totals, tax or credit-memo netting',
                pending_basis='SUM(max(quotation line net amount - distinct linked invoice line net amounts,0)); excess shown separately',
                caveats=['Quantity-full monetary gaps are pricing differences, not pending demand.',
                         'Closed unbilled quotations are not proven lost sales.',
                         '6 captured invoice lines have no captured quotation-line key; not attributed.',
                         'Source line-date and header-date extraction scopes differ; completeness unproven.',
                         'Capture observations are separate statement windows, not a common SAP snapshot.',
                         'Candidate source_as_of is preparation time, not the source observation cutoff.'],
                source_observation_windows=cutoffs, physical_file_hashes=physical,
                top20_products=products, top20_customer_state_rows=len(clients),
                CURRENT_MODIFIED=False, SAP_QUERIES=0, SAP_WRITES=0, MILVUS_ACCESSES=0)
        finally:
            reader.close()
        after = store.current_publication()
        if after is None or after.foundation_publication_id != current.foundation_publication_id or after.manifest != before:
            raise ValueError('CONCURRENT_CURRENT_CHANGE_REQUIRES_RECONCILIATION')
        report['CURRENT_MANIFEST_UNCHANGED'] = True
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str)+'\n')
    for name, rows in [('top20-products.csv', products), ('top20-product-client-state.csv', clients)]:
        with (OUTPUT/name).open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(dict(report=str(OUTPUT/'report.json'), publication=report['publication'],
                          reconciliation=report['reconciliation'], errors=errors), default=str))


if __name__ == '__main__':
    main()
