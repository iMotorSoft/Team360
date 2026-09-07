"""CASH_EVENT atomic contract (TELCHI spec §17, §18, §50, §51).

Separation of concerns (never conflated):
  PAYMENT            -> ORCT header (incoming payment document)
  PAYMENT_APPLICATION -> RCT2 (Telchi: on-account only, DEC-009)
  RECONCILIATION     -> OITR/ITR1 (settlement authority, DEC-010)
  CASH_EVENT         -> physical cash register event

Two evidential layers:
  * SAP side (CONFIRMED): payment-derived cash events from ORCT header
    cash-sum fields; the physical cash register is NOT explicit in ORCT,
    so cash_register_id stays UNKNOWN until OJDT/JDT1/OACT evidence.
  * Legacy baseline (LEGACY_REFERENCED): the legacy cash extractor
    (srvSyncTelchi02.py::makeCashDFRange) produced per-cash-register events
    from non-SAP tables (cjtrn/cjcja/cjdpc/cjddc/vttrn/...). Grain verified
    on cash-2022-02-28.parq: 28,175 rows, 43 registers, Efectivo 89.2%,
    SaleCode>0 in 89.6% of rows. NroTransaccion is NOT globally unique
    (CJTRN and CJDPC sequences collide) -> source_table discriminator.
"""
from __future__ import annotations

from modules.telchi.investigation.atomic.contracts.event_envelope import Field, f, CONFIRMED, LEGACY_REFERENCED, CANDIDATE

# ---- SAP side (CONFIRMED via ORCT inspection / financial validation) ----------
CASH_EVENT_SAP_FIELDS: dict[str, Field] = {
    "source_document_id": f("DocEntry", "ORCT", CONFIRMED, "payment header PK"),
    "source_document_number": f("DocNum", "ORCT", CONFIRMED),
    "customer_id": f("CardCode", "ORCT", CONFIRMED),
    "business_date": f("DocDate", "ORCT", CONFIRMED),
    "amount_document": f("DocTotal", "ORCT", CONFIRMED, "payment total"),
    "currency": f("DocCurr", "ORCT", CONFIRMED, "DEC-015"),
    "canceled": f("Canceled", "ORCT", CONFIRMED, "ORCT uses 'Canceled'"),
    "transaction_id": f("TransId", "ORCT", CONFIRMED),
    # cash portion (drives CASH_EVENT; classifier reads physical names)
    "cash_sum": f("CashSum", "ORCT", CONFIRMED, "cash portion of payment"),
    "check_sum": f("CheckSum", "ORCT", CONFIRMED),
    "transfer_sum": f("TrsfrSum", "ORCT", CONFIRMED),
    "card_sum": f("CreditSum", "ORCT", CONFIRMED, "credit card portion"),
    "on_account_sum": f("NoDocSum", "ORCT", CONFIRMED),
    "boe_sum": f("BoeSum", "ORCT", CONFIRMED),
    "channel_origin": f("U_ORIGIN", "ORCT", CANDIDATE, "channel inheritance hypothesis H3"),
    "retail_one_flag": f("U_SO1_01RETAILONE", "ORCT", CANDIDATE),
}

# ---- Legacy baseline (LEGACY_REFERENCED via srvSyncTelchi02.py + parquet) -----
CASH_EVENT_LEGACY_FIELDS: dict[str, Field] = {
    "NroTransaccion": f("NroTransaccion", "cjtrn.cjtrnntra | cjdpc.cjdpcntra", LEGACY_REFERENCED,
                       "NOT globally unique: CJTRN/CJDPC sequences collide (187 dup in 2022-02)"),
    "source_table": f("source_table", "CJTRN | CJDPC", LEGACY_REFERENCED, "discriminator, part of grain"),
    "CashCode": f("CashCode", "cjtrn.cjtrnccja (0 for DC)", LEGACY_REFERENCED, "physical cash register"),
    "CashName": f("CashName", "cjcja.cjcjadcja | 'DC'", LEGACY_REFERENCED),
    "CashDate": f("CashDate", "cjtrn.cjtrnftra | cjdpc.cjdpcftra", LEGACY_REFERENCED),
    "TSCash": f("TSCash", "gblog.gblogfsys", LEGACY_REFERENCED, "system timestamp"),
    "SellerCode": f("SellerCode", "cjcja.cjcjaccjr | cjdpc.cjdpcnofn", LEGACY_REFERENCED),
    "SubsidiaryCode": f("SubsidiaryCode", "cjtrn.cjtrnNofi | cjdpc.cjdpcNofi", LEGACY_REFERENCED,
                       "branch: 6 observed (1,2,4,5,7,8,9)"),
    "CashType": f("CashType", "'Efectivo' | cjddc.cjddcabrv", LEGACY_REFERENCED,
                 "observed: Efectivo 89.2%, TARJETA DEBITO-CRED 9.1%, Dep/Tran, CHEQUE"),
    "Concepto": f("Concepto", "cjtmv.cjtmvdesc | cjddc.cjddcabrv", LEGACY_REFERENCED),
    "Moneda": f("Moneda", "gbcon.gbconabrv", LEGACY_REFERENCED, "Bs 98.7% / $us 1.3% observed"),
    "CashTotal": f("CashTotal", "cjtrn.cjtrnimpt | cjdpc.cjdpcimpt", LEGACY_REFERENCED,
                  "SIGNED amount (outflows negative; 2022-02 sum -354,989.96)"),
    "CashTotalU$s": f("CashTotalU$s", "same, moneda=2 branch", LEGACY_REFERENCED),
    "TC": f("TC", "cjtrn.cjtrntcam | cjdpc.cjdpctcam", LEGACY_REFERENCED, "exchange rate"),
    "SaleCode": f("SaleCode", "cjtrn.cjtrntorg (cjtrnmorg=6) | cjdpc.cjdpctorg (cjdpcttrn=605)",
                 LEGACY_REFERENCED, "legacy sale transaction vttrn.vttrnNtve; >0 in 89.6% rows"),
    "ClientCode": f("ClientCode", "vttrn.vttrnccli | cjdpc.cjdpcccli", LEGACY_REFERENCED,
                   ">0 in only 11.1% rows: sale-origin events"),
}


# ---- Payment lifecycle roles (never conflate) ---------------------------------
PAYMENT_LIFECYCLE_ROLES: dict[str, str] = {
    "PAYMENT": "ORCT header (incoming payment document)",
    "PAYMENT_APPLICATION": "RCT2 limited to on-account in Telchi (DEC-009); NOT settlement authority",
    "RECONCILIATION": "OITR/ITR1 is the settlement authority (DEC-010); reconciled != cash paid (DEC-011)",
    "CASH_EVENT": "cash register event; SAP side payment-derived (CashSum), legacy side per-register (cjtrn)",
}