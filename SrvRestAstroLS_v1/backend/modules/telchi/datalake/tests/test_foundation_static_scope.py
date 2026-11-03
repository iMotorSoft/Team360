"""The negative-fixture exception must never exempt its executor or siblings."""
from modules.telchi.datalake.foundation_reader_scan import scan_direct_reads


def test_exploratory_exception_is_one_negative_fixture_only(tmp_path):
    root = tmp_path / 'exploratory_sql'
    root.mkdir()
    for name in ('test_foundation.py', 'foundation.py', 'other.py'):
        (root / name).write_text("query = 'SELECT * FROM telchi.atomic.sales_document'\n")
    scan = scan_direct_reads(tmp_path)
    assert scan['UNCLASSIFIED_DIRECT_READS'] == 2
    findings = {row['path']: row for row in scan['findings']}
    assert findings['exploratory_sql/test_foundation.py']['classification'] == 'TEST_ONLY'
    assert findings['exploratory_sql/test_foundation.py']['allowlisted'] is True
    assert findings['exploratory_sql/foundation.py']['allowlisted'] is False
    assert findings['exploratory_sql/other.py']['allowlisted'] is False
