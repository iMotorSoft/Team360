"""DEV deterministic Telchi capability adapter; no SQL or analytics here."""
from __future__ import annotations

from decimal import Decimal

ERROR_TEXT = 'No pude consultar los datos de Telchi en este momento.'


def is_telchi_trigger(text):
    return text.strip().lower() == 'hola'


def format_sales(result):
    lines = ['Telchi — Top 5 por cantidad fuente', '01/01/2026–15/09/2026', '']
    if not result['rows']:
        lines.append('Sin resultados para este período.')
    for index, row in enumerate(result['rows'][:5], 1):
        # Do not reinterpret source Quantity as a normalized inventory UoM.
        amount = format(Decimal(row['quantity']), ',.10f').rstrip('0').rstrip('.')
        amount = amount.replace(',', '_').replace('.', ',').replace('_', '.')
        code = str(row['item_code'] or '(sin código)').replace('\n', ' ').replace('\r', ' ')[:80]
        lines.append(f'{index}. {code} — {amount}')
    lines += ['', 'Cantidad registrada; no netea devoluciones ni convierte UoM.',
              'Fuente: Telchi Data Lake']
    return '\n'.join(lines)


class TelchiSqlAdapter:
    def __init__(self, query=None, *, timeout_seconds=30):
        from modules.telchi.datalake.messaging_sales_query import CAPABILITY, QUERY_HASH, query_fixed_sales
        self.capability, self.query_hash = CAPABILITY, QUERY_HASH
        self.query = query or query_fixed_sales
        self.timeout_seconds = timeout_seconds

    async def execute(self):
        from modules.telchi.datalake.messaging_sales_query import TelchiQueryError
        try:
            result = await self.query(timeout_seconds=self.timeout_seconds)
            text = format_sales(result)
            # Top 10 small canonical result, no raw transport payload or secrets.
            return text, {'status': 'succeeded', 'result': result}
        except TelchiQueryError as exc:
            return ERROR_TEXT, {'status': 'failed', 'error_code': exc.code}
        except Exception:
            return ERROR_TEXT, {'status': 'failed', 'error_code': 'datalake_unexpected_error'}
