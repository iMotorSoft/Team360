"""Download public official documentation only; no enterprise data or secrets."""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('data/reports/telchi/iva-bolivia-13-v1/sources')
SAP = 'https://help.sap.com/doc/089315d8d0f8475a9fc84fb919b501a3/10.0/en-US/SDKHelp/'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    urls = {'sin_compendio': 'https://www.impuestos.gob.bo/index.php/wp-json/wp/v2/pages/22625'}
    for name, obj, prop in [
        ('sap_line_total', 'Document_Lines', 'LineTotal'),
        ('sap_line_fc', 'Document_Lines', 'RowTotalFC'),
        ('sap_line_sc', 'Document_Lines', 'RowTotalSC'),
        ('sap_currency', 'Document_Lines', 'Currency'),
        ('sap_discount', 'Document_Lines', 'DiscountPercent'),
        ('sap_doc_total', 'Documents', 'DocTotal'),
        ('sap_local_currency', 'CompanyService', 'GetAdminInfo'),
        ('sap_admin_currency', 'AdminInfo', 'LocalCurrency'),
    ]:
        urls[name] = SAP + f'SAPbobsCOM~{obj}~{prop}.html'
    urls['sin_ley843'] = 'https://www.impuestos.gob.bo/wp-content/uploads/2026/10/1.-LEY-N%C2%B0-843-09-26.pdf'
    index = []
    for name, url in urls.items():
        entry = dict(name=name, url=url, retrieved_at=datetime.now(timezone.utc).isoformat())
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                data = response.read(30_000_000)
                entry['content_type'] = response.headers.get('Content-Type')
            suffix = '.pdf' if data.startswith(b'%PDF') else '.html'
            path = ROOT / (name + suffix)
            with path.open('xb') as f:
                f.write(data)
            entry.update(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            if suffix != '.pdf':
                text = re.sub(r'<script\b[^>]*>.*?</script>', '', data.decode(), flags=re.S | re.I)
                text = re.sub('<[^>]+>', ' ', text)
                (ROOT / (name + '.txt')).write_text(text)
        except Exception as exc:
            entry['error_type'] = type(exc).__name__
        index.append(entry)
    (ROOT / 'index.json').write_text(json.dumps(index, indent=2))


if __name__ == '__main__':
    main()
