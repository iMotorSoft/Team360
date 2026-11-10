"""Opt-in real sales reliability follow-up; no suppliers, transport or restarts.

Reuses the durable authenticated acceptance harness, not its old case battery.
Every output requires independent business review.
"""
import argparse
import asyncio
from pathlib import Path
from . import live_investigative_completeness as live

CASES = {
    'presentation': ['¿Qué cuenta SAP fue primera por importe comercial de sulfato de cobre de 25 kg en septiembre de 2026? No agrupes cuentas diferentes por nombre.'],
    'family': ['¿Cuál es el cliente con mayor importe comercial de líneas de ácido nítrico, incluyendo todas sus presentaciones, de agosto a octubre de 2026?'],
    'exclusion': ['¿Qué clientes compraron soda cáustica de 25 kg en octubre de 2026 pero no en septiembre?',
                  '¿Cuál de esos clientes tuvo el menor importe en octubre?'],
    'quantity': ['¿Qué cuenta SAP compró más soda cáustica por cantidad documental en octubre de 2026? Separá las presentaciones si sus unidades no son comparables.'],
    'list': ['¿Qué clientes compraron ácido nítrico en todas sus presentaciones en octubre de 2026?'],
    'display': ['Dame los 3 productos con mayor importe vendido en octubre de 2026',
                'No muestres el primero, mostrame otros productos del mismo período',
                'Y en septiembre de 2026, con la misma exclusión'],
    'display_customer': ['¿Qué productos compró la cuenta SAP C000143 en octubre de 2026, por importe comercial?',
                         '¿Qué otros productos compró ese cliente en ese mismo mes?',
                         'Y en septiembre de 2026, conservá la exclusión de presentación',
                         'Y en los últimos dos meses completos, mantené la exclusión de presentación y mostrame los otros productos de esa misma cuenta con importe comercial.'],
    # Reserved until fixes are frozen; not used to choose code or prompt changes.
    'heldout_presentation': ['¿Quién fue la cuenta SAP con mayor importe de líneas comerciales de soda cáustica de 1 kg en agosto de 2026? Incluí todos los SKU acreditados de esa presentación, no los de 25 kg ni 500 g.'],
    'heldout_exclusion': ['Listá las cuentas SAP que compraron sulfato de cobre de 25 kg en septiembre de 2026 pero no en octubre de 2026, con su importe de septiembre.'],
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=list(CASES))
    parser.add_argument('--verify-pages', action='store_true', help='Append local continuation checks to existing list cases')
    args = parser.parse_args()
    if args.verify_pages:
        for name in ('list', 'display_customer'):
            CASES[name] = [*CASES[name], 'Mostrame los siguientes registros del resultado conservado.']
    live.CASES = CASES
    asyncio.run(live.main(args))
