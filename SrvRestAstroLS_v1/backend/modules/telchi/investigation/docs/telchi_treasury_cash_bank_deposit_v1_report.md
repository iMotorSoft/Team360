# TELCHI — TREASURY / CASH / BANK / DEPOSIT V1

**Gate:** `TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1_PASS`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**Evidencia:** 2026-09-09T17:56:50.587240+00:00

## A. VEREDICTO EJECUTIVO

SAP separa documentalmente cobro/pago, instrumento, depósito y asiento. ORCT y OVPM llegan a OJDT por TransId; ODPS llega por TransAbs. Un depósito no se cuenta como nuevo cobro y las transferencias internas se mantienen fuera del flujo económico. La cadena contable está demostrada; la relación cash→deposit no tiene FK documental para efectivo y se publica como matching agregado explícito.

Resultado: **PASS**. Posición publicada: `SAP_ACCOUNTING_TREASURY_POSITION`, nunca `AVAILABLE_CASH`.

## B. CONFIGURACIÓN DE TESORERÍA

ODSC/DSC1 fueron descubiertas y mapeadas a GL cuando `GLAccount` existe. El detalle de configuración está en `bank_configuration.house_accounts`; números bancarios se preservan en JSON técnico y se omiten de esta síntesis ejecutiva.

## C. CUENTAS DE CAJA

Se identificaron 38 cuentas clasificadas CASH/PETTY_CASH por uso en ORCT/ODPS, jerarquía OACT y semántica del nombre. El saldo es `OACT.CurrTotal`, validado contra Σ(JDT1.Debit-Credit) cuando existe movimiento. La marca OACT.CashBox no se usa como única prueba.

| Cuenta | Nombre | Moneda | Saldo GL | Movimientos | Evidencia |
|---|---|---|---:|---:|---|
| 1110101 | Caja General Tesoreria MN | BS | 142855.14 | 64180 | PROVEN |
| 1110102 | Caja Recaudaciones Terbol | ## | 0.0 | 3562 | PROVEN |
| 1110201 | Cajas Casa Matriz MN | BS | 26067.17 | 599250 | PROVEN |
| 1110202 | Cajas 2do. Anillo MN | BS | 19016.62 | 340657 | PROVEN |
| 1110203 | Cajas Villa MN | BS | 5246.93 | 177386 | PROVEN |
| 1110204 | Cajas Urubo MN | BS | 0.0 | 1575 | PROVEN |
| 1110205 | Cajas Corporativa 2do. Anillo MN | BS | 97821.08 | 31982 | PROVEN |
| 1110206 | Cajas Roca Coronado MN | BS | 6290.21 | 113776 | PROVEN |
| 1110207 | Cajas Corporativa 2do. Anillo MN - Ventas Especiales | ## | 1119.4 | 2115 | PROVEN |
| 1110301 | Caja Corporativa Laboratorio MN | BS | 2147.0 | 31938 | PROVEN |
| 1110302 | Caja Corporativa La Paz MN | BS | 11683.7 | 7001 | PROVEN |
| 1110303 | Caja Cobranzas MN | BS | 0.0 | 265 | PROVEN |
| 1110304 | Caja Distribuidor Placa 47***02-GIP MN | BS | 0.0 | 22076 | PROVEN |
| 1110305 | Caja Distribuidor Placa 47***02-GKT MN | BS | 10210.29 | 23388 | PROVEN |
| 1110306 | Caja Distribuidor Placa 52***60-PSF MN | BS | 0.0 | 18084 | PROVEN |
| 1110307 | Caja Distribuidor Placa 29***04-ILA MN | BS | 9237.0 | 9030 | PROVEN |
| 1110308 | Caja Distribuidor Placa 38***72-XRI MN | BS | 47213.74 | 8611 | PROVEN |
| 1110309 | Caja Distribuidor Placa 12***45-XLN MN | BS | 12171.1 | 8587 | PROVEN |
| 1110310 | Caja Distribuidor Placa 27***25-PRC MN | BS | 11442.37 | 17518 | PROVEN |
| 1110311 | Caja Distribuidor Placa 44***74-CDE MN | BS | 0.0 | 138 | PROVEN |
| 1110312 | Caja Distribuidor Placa 56***87-SPE MN | BS | 0.0 | 7119 | PROVEN |
| 1110313 | Caja Distribuidor Provincias MN | BS | 0.0 | 752 | PROVEN |
| 1110314 | Caja Distribuidor 11 MN LPZ | BS | 1921.09 | 17616 | PROVEN |
| 1110315 | Caja Distribuidor Placa 52***60 IHY MN | BS | 5782.58 | 7826 | PROVEN |
| 1110316 | Caja Distribuidor Externo 1 | BS | 0.0 | 1214 | PROVEN |
| 1110317 | Caja Distribuidor Placa 60***00-KCI LPZ | BS | 6386.83 | 4748 | PROVEN |
| 1110401 | Caja General Tesoreria ME | USD | 423174.4 | 1320 | PROVEN |
| 1110501 | Cajas Casa Matriz ME | USD | 0.0 | 89 | PROVEN |
| 1110502 | Cajas 2do. Anillo ME | USD | 0.0 | 123 | PROVEN |
| 1110503 | Cajas Villa ME | USD | 0.0 | 36 | PROVEN |
| 1110504 | Cajas Urubo ME | USD | 0.0 | 6 | PROVEN |
| 1110505 | Cajas Corporativa 2do. Anillo ME | USD | 0.0 | 95 | PROVEN |
| 1110601 | Caja Corporativa Laboratorio ME | USD | 0.0 | 48 | PROVEN |
| 1110701 | Caja chica Casa Matriz MN | BS | 7000.0 | 1506 | PROVEN |
| 1110702 | Caja chica 2do. Anillo MN | BS | 15000.01 | 924 | PROVEN |
| 1110703 | Caja Chica Laboratorio MN | BS | 15482.61 | 3056 | PROVEN |
| 1110704 | Caja chica Saavedra MN | BS | 1855.0 | 793 | STRONG |
| 1110705 | Caja chica La Paz MN | BS | 2000.0 | 546 | PROVEN |

## D. CUENTAS BANCARIAS

Se identificaron 20 cuentas BANK por DSC1/DSC1.GLAccount y uso real en transferencias/depósitos. Son saldos contables SAP, no saldos externos conciliados.

| Cuenta | Nombre | Moneda | Saldo GL | Último movimiento | Estado |
|---|---|---|---:|---|---|
| 1111001 | BMSC Cta.Cte. 40***78 MN | BS | 995148.46 | 2026-09-09T00:00:00 | ACTIVE |
| 1111002 | BMSC Cta. Cte. 40***98 MN | BS | -74587.74 | 2026-09-05T00:00:00 | ACTIVE |
| 1111003 | Prodem Cja. Ah. 61***13-2-1-11***11-4 MN | BS | 0.0 | 2022-03-31T00:00:00 | ACTIVE |
| 1111004 | Fassil Cta. Cte.  98***10 MN | BS | 0.0 | 2025-12-31T00:00:00 | ACTIVE |
| 1111005 | BANCO UNION CTA. CTE. 1-19***95 M/N | BS | 204596.67 | 2026-09-08T00:00:00 | ACTIVE |
| 1111006 | BANCO FIE Cta.Cte. 60-0-00***00-62***28-1 MN | BS | 431706.24 | 2026-09-08T00:00:00 | ACTIVE |
| 1111007 | BCO.MSC SAFI CRECER Nº.10***21-1 MN | BS | 1314.88 | 2026-08-31T00:00:00 | ACTIVE |
| 1111008 | BANCO DE LA COMUNIDAD Cja. Ah.-72***20 MN | BS | 0.0 | 2026-05-08T00:00:00 | ACTIVE |
| 1111009 | BANCO FIE CTA. CTE. M/N 40***61-3 | BS | 1701.88 | 2026-01-01T00:00:00 | ACTIVE |
| 1111010 | BANCO FIE Cta.Cte. 60***69-6 MN | BS | 107134.05 | 2026-09-07T00:00:00 | ACTIVE |
| 1111011 | BANCO BNB Cta.Cte. 20***00-01***92 MN | BS | 13418.83 | 2026-08-01T00:00:00 | ACTIVE |
| 1111012 | BANCO UNION Cta.Cte. 1-33***59 MN | BS | -10856.46 | 2026-09-04T00:00:00 | ACTIVE |
| 1111013 | BANCO UNION Cta.Cte. 1-33***32 MN | BS | 0.0 | 2026-03-16T00:00:00 | ACTIVE |
| 1111014 | TARJETA DE CREDITO 44***28 FASSIL | BS | 0.0 | 2023-10-18T00:00:00 | ACTIVE |
| 1111015 | BANCO GANADERO Cta. Cte. 13***31 MN | ## | 467482.67 | 2026-09-09T00:00:00 | ACTIVE |
| 1111016 | BANK OF AMERICA - TELCHI INC. | ## | 196424.08 | 2026-01-01T00:00:00 | ACTIVE |
| 1111017 | HELM BANK USA-BUSINESS CHECKING  NRO. 11***68 | ## | 2405667.82 | 2026-01-09T00:00:00 | ACTIVE |
| 1111018 | TARJETA DE CRÉDITO 53***02 53***05 00***00 26***96 - Banco Mercantil Santa Cruz | ## | 0.0 | 2026-08-10T00:00:00 | ACTIVE |
| 1111201 | BCO.MSC SAFI FONDO MUTUO M/E Nº.10***21-1 ME | USD | 69769.29 | 2026-08-31T00:00:00 | ACTIVE |
| 1111301 | Compra y Venta de Divisas | ## | 0.0 | 2026-08-27T00:00:00 | ACTIVE |

## E. COBROS ORCT

El universo, cancelaciones, monedas y medios está en `orct`. Cada método se calcula desde CashSum/CheckSum/TrsfrSum/CreditSum/NoDocSum/BoeSum; no se interpreta ORCT como banco por defecto.

## F. COBRO → GL

`ORCT.TransId → OJDT.TransId → JDT1` es la trazabilidad primaria. La cuenta del medio se valida por identidad de cuenta y importe del componente, no por posición de línea.

## G. DEPÓSITOS ODPS

`ODPS.TransAbs → OJDT.TransId` cubre el universo. `DeposType` se conserva: C=CASH, K=CHECK, V=CREDIT_CARD; `BanckAcct` representa el destino bancario contable y `AllocAcct` la fuente cuando está poblada.

## H. COBRO → DEPÓSITO → BANCO

Los cheques tienen cadena documental `ORCT.RCT1.CheckAbs → OCHH.CheckKey → OCHH.DpstAbs → ODPS → JDT1`; para efectivo no hay FK ORCT→ODPS. Matching agregado: {'active_cash_deposits_with_candidate': 349, 'unique_strong_matches': 171, 'lag_buckets': {'16_30_DAYS': 41, '1_DAY': 12, '2_DAYS': 16, '3_DAYS': 7, '4_7_DAYS': 55, '8_15_DAYS': 36, 'SAME_DAY': 4}, 'direct_document_link': False, 'evidence': 'STRONG_MATCH only for unique aggregate daily match; otherwise HEURISTIC_MATCH/NO_LINK_AVAILABLE'}. No se llama depósito a nuevo ingreso.

## I. PAGOS OVPM

OVPM se analiza por método y moneda, separado del settlement AP ya cerrado. Transferencias se siguen por TrsfrAcct y TransId; efectivo/cheque se siguen por CashAcct/CheckAcct y VPM1.

## I BIS. CONTRASTE SAP_OTHER_COMPENSATION_REVIEW

Se preserva sin reabrir el universo AP cerrado de 154 casos por Bs 380,679.38. El contraste de tesorería consulta únicamente enlaces OVPM y contrapartidas OITR/ITR1; encontró 2 casos AP con contraparte de pago SrcObjTyp=46 sin VPM2, conservados como contraste de tesorería. No convierte SrcObjTyp ni similitud de importe en retención.

## J. PAGO → BANCO/CAJA

Los casos representativos están en `cases`; los importes y asientos se conservan sin mezclar monedas. Pagos cancelados quedan fuera de posición vigente.

## K. CHEQUES

OCHH permite separar cheques recibidos en cartera/depositados; OCHO/VPM1 cubren cheques emitidos. `CLEARED` bancario solo se usa si existe evidencia, no por la mera existencia del cheque.

## L. TARJETAS / CLEARING

RCT3 y CreditAcct se inspeccionan. La posición de tarjeta/clearing permanece separada de caja y banco si la cuenta no tiene semántica bancaria demostrada.

## M. TRANSFERENCIAS INTERNAS

Se reportan candidatos por journals con más de una cuenta de tesorería y TransType -2/-3/JE. No se suman como ingreso ni egreso económico.

## N. ASIENTOS MANUALES DE TESORERÍA

Se miden OJDT.TransType=30, DataSource manual, usuarios, cuentas, memo y una clasificación conservadora de comisión, interés, transferencia, FX o UNKNOWN.

## O. POSICIÓN DE CAJA

La posición es contable por cuenta y moneda. No representa arqueo físico.

## P. POSICIÓN DE BANCOS

La posición es contable por cuenta y moneda. No representa saldo bancario externo.

## Q. VALORES / DINERO EN TRÁNSITO

Cheques recibidos, tarjetas y cuentas puente se presentan separados; no se suman automáticamente a efectivo disponible.

## R. CASH→DEPOSIT LAG

Buckets del matching agregado único: `{'16_30_DAYS': 41, '1_DAY': 12, '2_DAYS': 16, '3_DAYS': 7, '4_7_DAYS': 55, '8_15_DAYS': 36, 'SAME_DAY': 4}`. Este cálculo no sustituye una conciliación diaria ni prueba existencia física.

## S. SALDOS PERSISTENTES / REVIEW

`account_profiles.monthly` permite revisar persistencia >30/60/90/180/365 días. Una antigüedad no se etiqueta irregularidad sin semántica y evidencia operacional.

## T. CONCILIACIÓN BANCARIA

OBNK existe y contiene 17420 filas; líneas con fecha=17420, importes no cero=17420, conciliadas=0, matching=16600. La evidencia observada no permite construir saldo externo conciliado: `BANK_RECONCILIATION_NOT_AVAILABLE_OR_UNUSED` para este gate.

## U. CASOS REALES

Se conservan casos A–J en JSON: efectivo→caja, efectivo→depósito→banco cuando el matching existe, transferencia directa, cheque depositado si existe, pago OVPM, cheque/efectivo, depósito cancelado, JE manual, saldo persistente y movimiento no clasificado.

## V. LIMITACIONES

- SAP registra saldos GL; no se afirma dinero físicamente disponible.
- No existe enlace documental directo ORCT cash→ODPS; el matching por cuenta/moneda/fecha/importe es agregado y etiquetado.
- OBNK no aporta cobertura suficiente de extracto conciliado en la evidencia observada.
- Saldos en `BS`, `USD` y `##` no se suman nominalmente.
- Sucursal/origen solo se conservan si vienen de BPLId/UDF/documento; no se inventan por usuario.

## W. IMPLICACIONES PARA CONTROL INTERNO

SAP permite reproducir caja esperada contable antes del depósito como: saldo inicial de cuenta + cobros cash + otros débitos de tesorería − depósitos/egresos/ajustes acreditados, por cuenta y moneda. SAP no demuestra que ese resultado existiera físicamente sin arqueo externo.

## X. PRÓXIMO GATE

La evidencia favorece `TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1` para integrar AR+AP+SAP_ACCOUNTING_TREASURY_POSITION. Si se requiere control operativo de depósitos, el siguiente gate específico es `TELCHI_CASH_DEPOSIT_CONTROL_V1`; la conciliación bancaria externa queda separada.

## INVARIANTES

| Invariante | Resultado |
|---|---|
| TR01_orct_transid_exists_in_ojdt | PASS — {'orphans': 0, 'pass': True} |
| TR02_ovpm_transid_exists_in_ojdt | PASS — {'orphans': 0, 'pass': True} |
| TR03_odps_transabs_exists_in_ojdt | PASS — {'orphans': 0, 'pass': True} |
| TR04_treasury_journals_balance | PASS — {'pass': True, 'accounts_checked': 111} |
| TR05_classified_accounts_exist_in_oact | PASS — {'pass': True, 'bank_accounts': 20, 'cash_accounts': 38} |
| TR06_canceled_collections_separate | PASS — {'pass': True, 'basis': "ORCT.Canceled is grouped separately and active analyses filter Canceled='N'."} |
| TR07_canceled_supplier_payments_separate | PASS — {'pass': True, 'basis': "OVPM.Canceled is grouped separately and active analyses filter Canceled='N'."} |
| TR08_canceled_deposits_separate | PASS — {'pass': True, 'basis': "ODPS.Canceled is grouped separately and active deposits filter Canceled='N'."} |
| TR09_internal_transfers_not_economic_flow | PASS — {'pass': True, 'basis': 'TransType -2/-3 and multi-treasury journal candidates are reported separately.'} |
| TR10_currency_not_mixed | PASS — {'pass': True, 'basis': 'ORCT/OVPM/ODPS and OACT positions retain currency fields.'} |
| TR11_cash_deposit_evidence_explicit | PASS — {'pass': True, 'basis': 'STRONG_MATCH only for unique aggregate daily match; otherwise HEURISTIC_MATCH/NO_LINK_AVAILABLE'} |
| TR12_sap_write_count | PASS — {'value': 0, 'pass': True} |
| TR13_bank_reconciliation_not_overstated | PASS — {'pass': True, 'basis': 'OBNK is reported as source coverage only; no external bank balance is inferred.'} |

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/treasury_cash_bank_deposit/treasury_cash_bank_deposit_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/treasury_cash_bank_deposit/treasury_cash_bank_deposit_v1.py`
- HANA/SAP: SELECT-only; `SAP_WRITE_COUNT=0`.
