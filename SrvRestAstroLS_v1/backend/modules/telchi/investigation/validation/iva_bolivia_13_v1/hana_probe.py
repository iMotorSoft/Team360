"""Small SELECT-only source probes; no data changes, credentials or customer exports."""
import json
import socket
from pathlib import Path
from datetime import datetime, timezone
from modules.telchi.datalake.source import hana_config, HanaReadOnlySource
from hdbcli import dbapi

OUTPUT = Path('../../data/reports/telchi/iva-bolivia-13-v1/hana-probe.json')


def main():
    cfg = hana_config()
    ev = dict(at=datetime.now(timezone.utc).isoformat(), sap_write_count=0, queries=[])
    def factory():
        con = dbapi.connect(address=cfg['host'], port=int(cfg['port']), user=cfg['user'],
                            password=cfg['password'], currentSchema=cfg['schema'],
                            encrypt='false', connectTimeout=8000, communicationTimeout=15000)
        return con, con.cursor()
    source = HanaReadOnlySource(connect_factory=factory)
    try:
        with socket.create_connection((cfg['host'], int(cfg['port'])), timeout=5):
            pass
        ev['tcp_preflight'] = 'PASS'
        for name, sql in [
            ('company_currency', 'SELECT TOP 2 "MainCurncy","SysCurrncy","SumDec","PriceDec","PercentDec" FROM "OADM"'),
            ('currency_codes', 'SELECT "CurrCode","CurrName","DocCurrCod","Decimals" FROM "OCRN" WHERE "CurrCode" IN (\'BS\',\'USD\')'),
            ('invoice_example', 'SELECT "DocEntry","DocNum","DocCur","DocTotal","DocTotalFC","DocTotalSy","VatSum","VatSumFC","VatSumSy","DiscPrcnt","DiscSum","TotalExpns","RoundDif" FROM "OINV" WHERE "DocNum"=260192728'),
        ]:
            try:
                rows = source.query_read_only(name, sql)
                ev['queries'].append(dict(name=name, sql=sql, rows=rows))
            except Exception as exc:
                ev['queries'].append(dict(name=name, sql=sql, error_type=type(exc).__name__, error_code=exc.args[0] if exc.args and isinstance(exc.args[0], int) else None))
    except Exception as exc:
        ev['preflight_error_type'] = type(exc).__name__
    ev['query_log'] = source.query_log
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('x') as f:
        json.dump(ev, f, indent=2, default=str)
    print(json.dumps(ev, indent=2, default=str))

if __name__ == '__main__':
    main()
