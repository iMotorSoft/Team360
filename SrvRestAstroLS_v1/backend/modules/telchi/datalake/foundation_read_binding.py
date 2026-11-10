"""Publisher accreditation stored on the existing Foundation publication row.

The catalog writer is the trust boundary, not a worker/result-supplied receipt.
Hashes here bind metadata; physical hashing belongs exclusively to publication.
"""
import hashlib
import json

from .foundation_publication import FoundationReaderError, utc_now

CONTRACT = 'foundation-read-binding-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def make_binding(publication, access, *, commercial=False, physical=None):
    """Called only after the publisher's full physical and business gates."""
    result = dict(contract=CONTRACT, foundation_publication_id=publication.foundation_publication_id,
        commit_snapshot_id=access.commit_snapshot_id, snapshot_id=access.ducklake_snapshot_id,
        manifest_sha256=digest(publication.manifest),
        components=publication.manifest['components'], coverage=publication.manifest.get('sales_coverage', []),
        source_as_of=publication.source_as_of, reference_version=publication.reference_version,
        validated_at=utc_now(),
        component_cutoffs={k:v.get('source_as_of') for k,v in publication.manifest['components'].items()},
        catalog_component_cutoffs={k:v.source_as_of for k,v in publication.components.items()},
        commercial=commercial, physical=physical)
    result['receipt_sha256'] = digest(result)
    validate_binding(publication, result)
    return result


def validate_binding(publication, binding):
    """Constant metadata work; no ancestry traversal, file I/O or scan."""
    def invalid():
        raise FoundationReaderError('FOUNDATION_READ_BINDING_INVALID')
    if not isinstance(binding, dict):
        invalid()
    unsigned = {k:v for k,v in binding.items() if k != 'receipt_sha256'}
    if (binding.get('contract') != CONTRACT
            or binding.get('receipt_sha256') != digest(unsigned)
            or binding.get('foundation_publication_id') != publication.foundation_publication_id
            or binding.get('manifest_sha256') != digest(publication.manifest)
            or binding.get('components') != publication.manifest.get('components')
            or binding.get('coverage') != publication.manifest.get('sales_coverage', [])
            or binding.get('reference_version') != publication.reference_version
            or binding.get('source_as_of') != publication.source_as_of
            or binding.get('component_cutoffs') != {k:v.get('source_as_of') for k,v in publication.manifest.get('components', {}).items()}
            or binding.get('catalog_component_cutoffs') != {k:v.source_as_of for k,v in publication.components.items()}
            or not binding.get('validated_at')
            or type(binding.get('commercial')) is not bool):
        invalid()
    for key in ('commit_snapshot_id', 'snapshot_id'):
        if type(binding.get(key)) is not int or binding[key] < 0:
            invalid()
    data_snapshot = publication.manifest.get('facts_base_snapshot_id',
        publication.manifest.get('reference_data_snapshot_id', binding['commit_snapshot_id']))
    if binding['snapshot_id'] != data_snapshot or binding['snapshot_id'] > binding['commit_snapshot_id']:
        invalid()
    activation = binding.get('activation')
    if activation is not None:
        if (not isinstance(activation, dict)
                or set(activation) != {'protocol', 'prepared_snapshot_id'}
                or activation['protocol'] != 'atomic-current-receipt-v1'
                or type(activation['prepared_snapshot_id']) is not int
                or activation['prepared_snapshot_id'] != binding['commit_snapshot_id']):
            invalid()
    physical = binding.get('physical')
    if physical is not None:
        if (not binding['commercial'] or not isinstance(physical, dict)
                or set(physical) != {'reference', 'products_sha256', 'crosswalk_sha256'}
                or physical['reference'] != publication.reference_version):
            invalid()
        for key in ('products_sha256', 'crosswalk_sha256'):
            value = physical[key]
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                invalid()
    return binding
