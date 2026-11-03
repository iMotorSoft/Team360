"""Bounded, durable master closure for the accredited sales continuity capture.

No sales extraction, pointer writes, physical classification or activation.
Existing Reference rows/crosswalks retain all values; unrelated files retain bytes.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
import shutil

from . import sales_incremental as inc
from .reference_update import (ENTITY_CONFIG, _find, merge_entity, read_parquet_rows,
                               write_parquet, validate_identity, digest, version_content, version_fingerprint, _normal)
from .source import HanaReadOnlySource, HanaTransportLimits

FIELDS = {
    'customer': ('OCRD', 'CardCode', ('CardCode', 'CardName', 'CardType', 'GroupCode',
                 'GroupNum', 'validFor', 'frozenFor', 'LicTradNum', 'CreditLine', 'UpdateDate')),
    'product': ('OITM', 'ItemCode', ('ItemCode', 'ItemName', 'validFor', 'frozenFor',
                'InvntItem', 'SellItem', 'PrchseItem', 'ItmsGrpCod', 'InvntryUom',
                'SalUnitMsr', 'BuyUnitMsr', 'UpdateDate')),
}


def _projected_rows(rows, columns, types):
    """Exact typed row multiset; no per-row JSON/SHA work or lost duplicates.

    Callers first verify identical column order and types. This is an ephemeral
    comparison only: published content fingerprints keep their original digest.
    """
    @lru_cache(maxsize=8192, typed=True)
    def decimal_value(value):
        value = _normal(value)
        return None if value is None else str(Decimal(value).normalize())

    @lru_cache(maxsize=8192, typed=True)
    def timestamp_value(value):
        value = _normal(value)
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed).isoformat()

    from operator import itemgetter
    conversions = [(i, decimal_value if typ.startswith(('DECIMAL', 'DOUBLE', 'FLOAT'))
                    else timestamp_value) for i, typ in enumerate(types)
                   if typ.startswith(('DECIMAL', 'DOUBLE', 'FLOAT', 'TIMESTAMP'))]
    getter = itemgetter(*columns) if len(columns) > 1 else None
    def projected(row):
        try:
            values = getter(row) if getter else tuple(row.get(c) for c in columns)
        except KeyError:
            values = tuple(row.get(c) for c in columns)
        # Parquet VARCHAR reads are already normalized. Preserve the generic
        # typed contract too, without millions of redundant _normal/get calls.
        values = [v if v is None or isinstance(v, str) else _normal(v) for v in values]
        for index, convert in conversions:
            values[index] = convert(values[index])
        return tuple(values)
    return Counter(projected(row) for row in rows)


def _same_identity_rows(expected, actual, columns, types):
    """Exact typed equality with a fast path for unchanged decoded rows.

    Both sides have the same schema and source-scoped unique identities. Dict
    equality is a sufficient (not necessary) equality proof; only differing
    encodings need Decimal/timestamp normalization. No row is sampled or skipped.
    """
    def index(rows):
        result = {}
        for row in rows:
            key = (row.get('source_system'), row.get('source_native_id'))
            if not all(key) or key in result:
                raise ValueError('duplicate or missing Reference identity')
            result[key] = row
        return result
    before, after = index(expected), index(actual)
    if before.keys() != after.keys():
        return False
    different = [key for key in before if before[key] != after[key]]
    return (_projected_rows([before[k] for k in different], columns, types) ==
            _projected_rows([after[k] for k in different], columns, types))


def batches(keys):
    if len(keys) != len(set(keys)) or any(not isinstance(k, str) or not k.strip() for k in keys):
        raise ValueError('explicit distinct nonblank codes required')
    return [keys[n:n+25] for n in range(0, len(keys), 25)]


def query(entity, keys):
    table, key, fields = FIELDS[entity]
    if len(batches(keys)) != 1:
        raise ValueError('one to 25 exact keys required')
    return ('SELECT ' + ', '.join('"'+f+'"' for f in fields)
            + f' FROM "TELCHI"."{table}" WHERE "{key}" IN ('
            + ','.join('?' for _ in keys) + f') ORDER BY "{key}"')


def validate_response(entity, keys, rows):
    _, key, fields = FIELDS[entity]
    seen = set()
    for row in rows:
        code = row.get(key)
        if code not in keys or code in seen or set(row) != set(fields):
            raise ValueError('duplicate, unexpected key or incomplete master projection')
        if not row.get('CardName' if entity == 'customer' else 'ItemName'):
            raise ValueError('unaccredited empty master name')
        if entity == 'customer' and row['CardType'] != 'C':
            raise ValueError('billed customer has contradictory SAP entity type')
        seen.add(code)
    return sorted(set(keys)-seen)


def capture_missing(root, missing, source=None, *, resume_only=False):
    """Write intent BEFORE issuing SELECT; uncertain operations never retry."""
    source = source or HanaReadOnlySource(limits=HanaTransportLimits(max_rows=25))
    if len(missing['customer']) > 45 or len(missing['product']) > 38:
        raise ValueError('master authorization budget exceeded')
    root.mkdir(parents=True, exist_ok=True)
    plan = {'contract': 'sales-reference-release-v1', 'keys': missing,
            'max_selects': 8, 'batch_size': 25, 'concurrency': 1, 'retries': 0}
    if (root/'plan.json').exists():
        if inc.read_json(root/'plan.json') != plan:
            raise ValueError('immutable plan mismatch')
    else:
        inc.seal(root/'plan.json', plan)
    results, logs = {}, []
    for entity in FIELDS:
        results[entity] = []
        for number, keys in enumerate(batches(missing[entity])):
            prefix = root/f'{entity}-{number:02}'
            intent = {'entity': entity, 'keys': keys, 'sql': query(entity, keys),
                      'plan_sha256': inc.file_hash(root/'plan.json')}
            ip, rp, cp = (prefix.with_suffix(s) for s in ('.intent.json', '.response.json', '.receipt.json'))
            if ip.exists():
                if inc.read_json(ip) != intent or not cp.exists():
                    raise RuntimeError('UNCERTAIN_REQUEST_NO_AUTOMATIC_RETRY')
                receipt = inc.read_json(cp)
                if receipt['intent_sha256'] != inc.file_hash(ip) or receipt['response_sha256'] != inc.file_hash(rp):
                    raise ValueError('master checkpoint hash mismatch')
                rows = inc.read_json(rp)
            else:
                if resume_only:
                    raise RuntimeError('MASTER_CHECKPOINT_MISSING_NO_EXTRACTION_ALLOWED')
                if len(list(root.glob('*.intent.json'))) >= 8:
                    raise RuntimeError('SELECT_BUDGET_EXHAUSTED')
                inc.seal(ip, intent)
                rows = source.query_read_only('sales_reference_'+entity, intent['sql'], tuple(keys))
                pending = validate_response(entity, keys, rows)
                inc.seal(rp, rows)
                receipt = {'intent_sha256': inc.file_hash(ip), 'response_sha256': inc.file_hash(rp),
                           'observed_at': datetime.now(timezone.utc).isoformat(),
                           'pending': pending, 'audit': source.query_log[-1]}
                inc.seal(cp, receipt)
            if receipt['pending'] != validate_response(entity, keys, rows):
                raise ValueError('master receipt missing-key reconciliation mismatch')
            results[entity].extend({**row, '_source_extracted_at': receipt['observed_at']} for row in rows)
            logs.append(receipt)
    return results, logs


def merge_accredited(entity, observations, old, columns, oldcw, cw_columns, reference_root):
    """Reuse identity producer; never invent dangling secondary foreign keys.

    Native master attributes remain in the immutable source checkpoint. Missing
    secondary relationships are nullable pending enrichment, not fabricated IDs.
    """
    merged, mapped, stats = merge_entity(entity, observations, old, columns, oldcw, cw_columns)
    source_key = ENTITY_CONFIG[entity]['key']
    new_keys = {r[source_key] for r in observations}
    terms = {}
    term_path = Path(reference_root)/'payment_terms/part-00000.parquet'
    if entity in {'customer', 'supplier'} and term_path.is_file():
        for r in read_parquet_rows(term_path)[2]:
            if r.get('source_system')=='SAP_HANA':
                terms[r.get('source_native_id')] = r.get('payment_term_id')
    sources = {r[source_key]:r for r in observations}
    for row in merged:
        if row.get('source_system')!='SAP_HANA' or row.get('source_native_id') not in new_keys:
            continue
        if entity in {'customer', 'supplier'} and 'payment_term_id' in columns:
            group = sources[row['source_native_id']].get('GroupNum')
            row['payment_term_id'] = terms.get(str(group)) if group is not None else None
        if entity=='product':
            # The closure's units_of_measure registry uses canonical_uom_code,
            # not the historical producer's hashed inventory_uom_id namespace.
            for field in ('inventory_uom_id','sales_uom_id','purchase_uom_id'):
                if field in columns:
                    row[field] = None
    return merged, mapped, stats


def prepare(previous_reference, previous_crosswalk, observations, destination):
    """Add only missing accredited identities using the existing identity producer."""
    if destination.exists():
        raise FileExistsError('immutable preparation destination already exists')
    destination.mkdir(parents=True)
    ref, cw = destination/'reference', destination/'crosswalk'
    shutil.copytree(previous_reference, ref)
    shutil.copytree(previous_crosswalk, cw)
    summary = {}
    for entity, cfg in ((e, ENTITY_CONFIG[e]) for e in observations):
        columns, types, old = read_parquet_rows(_find(previous_reference, cfg['ref']))
        cc, ct, oldcw = read_parquet_rows(_find(previous_crosswalk, cfg['crosswalk']))
        existing = {r['source_native_id'] for r in old if r['source_system'] == 'SAP_HANA'}
        requested = [r[cfg['key']] for r in observations[entity]]
        if existing.intersection(requested) or len(set(requested)) != len(requested):
            raise ValueError('append-only closure cannot alter existing identities')
        merged, mapped, stats = merge_accredited(entity, observations[entity], old, columns, oldcw, cc, previous_reference)
        validate_identity(entity, merged, mapped, old, oldcw)
        # Preserve every old attribute, including lineage. No master refresh.
        old_by_key = {(r['source_system'], r['source_native_id']): r for r in old}
        if any(old_by_key[(r['source_system'], r['source_native_id'])] != r for r in merged
               if (r['source_system'], r['source_native_id']) in old_by_key):
            raise ValueError('historical master attributes modified')
        write_parquet(ref/_find(previous_reference, cfg['ref']).relative_to(previous_reference), columns, types, merged)
        write_parquet(cw/_find(previous_crosswalk, cfg['crosswalk']).relative_to(previous_crosswalk), cc, ct, mapped)
        summary[entity] = {'new': stats['new'], 'historical_rows_preserved': len(old),
                           'resolved_codes': sorted(requested),
                           'secondary_relationships': 'NULL_WHEN_NO_EXISTING_REFERENCE_TARGET; native values retained in master checkpoints'}
    fingerprint = digest(version_content(ref, cw))
    result = {'status': 'REFERENCE_PREPARED_NOT_FOUNDATION_VALIDATED',
              'reference_version': 'v2_sales_'+fingerprint[:24],
              'reference_path': str(ref), 'crosswalk_path': str(cw),
              'fingerprint': fingerprint, 'identities': summary,
              'activated': False, 'physical_reference_integrated': False}
    inc.seal(destination/'result.json', result)
    return result


def append_proof(previous_reference, candidate_reference, capture_root):
    """Recompute an exact append-only contract from sealed master checkpoints.

    Only two Reference datasets and their crosswalks may gain rows. Every prior
    row/column and all other files stay unchanged. New rows must equal the
    existing producer applied to the exact accredited OCRD/OITM observations.
    """
    previous_reference, candidate_reference = map(Path, (previous_reference, candidate_reference))
    capture_root = Path(capture_root)
    from .full_refresh_capture import CONTRACT as FULL_CAPTURE
    full_capture = capture_root.resolve().parent == (inc.DATA_ROOT/'raw/sap'/FULL_CAPTURE).resolve()
    if full_capture:
        from .full_refresh_reference import missing_observations
        observations, receipts = missing_observations(previous_reference, capture_root)
        plan = {'keys': {e: [r[ENTITY_CONFIG[e]['key']] for r in observations[e]] for e in observations}}
        plan_path = capture_root/'cycle-plan.json'
    else:
        if capture_root.resolve().parent != (inc.DATA_ROOT/'raw/sap/sales-reference-release-v1').resolve():
            raise ValueError('master evidence outside authorized root')
        plan_path = capture_root/'plan.json'
        plan = inc.read_json(plan_path)
        observations, receipts = capture_missing(capture_root, plan['keys'], resume_only=True)
    if any(r['pending'] for r in receipts):
        raise ValueError('incomplete masters cannot certify Reference')
    previous_cw = previous_reference.parents[2]/'crosswalk/_versions'/previous_reference.name
    candidate_cw = candidate_reference.parents[2]/'crosswalk/_versions'/candidate_reference.name
    evidence = {}
    for family, oldroot, newroot in (('reference',previous_reference,candidate_reference),
                                     ('crosswalk',previous_cw,candidate_cw)):
        oldfiles = {p.relative_to(oldroot):p for p in oldroot.rglob('*') if p.is_file()}
        newfiles = {p.relative_to(newroot):p for p in newroot.rglob('*') if p.is_file()}
        if set(oldfiles) != set(newfiles) or not oldfiles:
            raise ValueError('append-only Reference dataset registry mismatch')
        affected = {Path(ENTITY_CONFIG[e]['ref' if family=='reference' else 'crosswalk'])/'part-00000.parquet' for e in observations}
        for rel, oldpath in oldfiles.items():
            newpath = newfiles[rel]
            if oldpath.is_symlink() or newpath.is_symlink():
                raise ValueError('symlink in immutable Reference')
            if rel not in affected and inc.file_hash(oldpath) != inc.file_hash(newpath):
                raise ValueError('independent Reference dataset changed: '+str(rel))
            evidence[family+'/'+str(rel)] = inc.file_hash(newpath)
    for entity,cfg in ((e,ENTITY_CONFIG[e]) for e in observations):
        cols,types,old = read_parquet_rows(_find(previous_reference,cfg['ref']))
        cc,ct,oldcw = read_parquet_rows(_find(previous_cw,cfg['crosswalk']))
        nc,nt,new = read_parquet_rows(_find(candidate_reference,cfg['ref']))
        ncc,nct,newcw = read_parquet_rows(_find(candidate_cw,cfg['crosswalk']))
        if (cols,types,cc,ct) != (nc,nt,ncc,nct):
            raise ValueError('append-only Reference schema changed')
        existing = {r['source_native_id'] for r in old if r['source_system']=='SAP_HANA'}
        if existing.intersection(plan['keys'][entity]):
            raise ValueError('append-only evidence includes preexisting identity')
        expected,expectedcw,_ = merge_accredited(entity,observations[entity],old,cols,oldcw,cc,previous_reference)
        if (not _same_identity_rows(expected,new,cols,types)
                or not _same_identity_rows(expectedcw,newcw,cc,ct)):
            raise ValueError('Reference append does not match accredited master producer')
        validate_identity(entity,new,newcw,old,oldcw)
    fingerprint = version_fingerprint(candidate_reference,candidate_cw)
    if candidate_reference.name != 'v2_sales_'+fingerprint[:24]:
        raise ValueError('Reference content identity mismatch')
    return {**({'capture_receipts': receipts, 'capture_contract': FULL_CAPTURE} if full_capture else {}),
            'contract_version':'1.0.0','previous_reference_path':str(previous_reference),
            'reference_path':str(candidate_reference),'master_capture_root':str(capture_root),
            'plan_sha256':inc.file_hash(plan_path),
            'files':evidence,'fingerprint':fingerprint,
            'new_identities':{e:len(plan['keys'][e]) for e in observations},
            'source_as_of':max(r['observed_at'] for r in receipts),
            'sealed_dependents':'EXACT_HISTORICAL_ROWS_AND_SCHEMAS_PRESERVED'}
