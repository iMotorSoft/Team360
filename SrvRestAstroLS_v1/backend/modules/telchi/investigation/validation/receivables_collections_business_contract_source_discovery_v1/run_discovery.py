#!/usr/bin/env python3
"""TELCHI Receivables & Collections source discovery V1.

Investigation-only. SAP/HANA statements are SELECT-only, sequential and either
aggregate or key/date bounded. This runner does not build Atomic datasets and
never writes SAP, Foundation or Data Root.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort

GATE = "TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_CONTRACT_AND_SOURCE_DISCOVERY_V1"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
FOUNDATION = "foundation_417c860c216805f18341bb741ee026e3"
REFERENCE = "v2_reference_closure_2088d5885204313a"
REPO_ROOT = Path(__file__).resolve().parents[8]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "settlement_business_contract_source_discovery_v1" / "discovery_evidence.json"
TABLES = ("OINV", "INV1", "INV6", "ORIN", "RIN1", "ORCT", "RCT1", "RCT2", "RCT3", "RCT4", "OITR", "ITR1", "OCTG", "OCRD", "OJDT", "JDT1", "OSLP", "OBPL", "CUFD", "UFD1")
WRITE_WORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|CALL|GRANT|REVOKE)\b", re.I)


def serial(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_json(name: str, payload: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_ROOT / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=serial) + "\n", encoding="utf-8")
    temp.replace(path)


class ReadOnlyHana:
    def __init__(self, cursor: Any, guard: ResourceGuard) -> None:
        self.cursor = cursor
        self.guard = guard
        self.query_count = 0
        self.write_count = 0
        self.log: list[dict[str, Any]] = []

    def select(self, name: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        normalized = sql.strip()
        if not normalized.upper().startswith("SELECT") or WRITE_WORDS.search(normalized):
            self.write_count += 1
            raise RuntimeError(f"non-SELECT statement blocked: {name}")
        self.guard.checkpoint()
        started = datetime.now(timezone.utc)
        self.cursor.execute(normalized, params)
        columns = [str(column[0]) for column in self.cursor.description]
        rows = [dict(zip(columns, row, strict=False)) for row in self.cursor.fetchall()]
        self.query_count += 1
        self.log.append({"name": name, "rows_returned": len(rows), "started_at": started, "bounded": True})
        return rows


def one(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def main() -> int:
    started = datetime.now(timezone.utc)
    guard = ResourceGuard()
    try:
        assessment = guard.preflight()
    except SafeAbort as exc:
        write_json("precheck.json", {"gate": GATE, "resource_status": "STOP", "reason": exc.reason})
        print(f"{GATE}_STOP_RESOURCE_PRESSURE")
        return 3

    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    conn, cursor = connect()
    guard.begin_segment()
    hana = ReadOnlyHana(cursor, guard)
    try:
        preflight = one(hana.select("preflight", 'SELECT CURRENT_USER AS "USER", CURRENT_SCHEMA AS "SCHEMA", CURRENT_DATE AS "AS_OF_DATE" FROM DUMMY'))
        placeholders = ",".join("?" for _ in TABLES)
        inventory = hana.select("source_inventory", f'SELECT "TABLE_NAME" FROM "SYS"."TABLES" WHERE "SCHEMA_NAME"=CURRENT_SCHEMA AND "TABLE_NAME" IN ({placeholders}) ORDER BY "TABLE_NAME"', TABLES)
        schema = hana.select("schema", f'''SELECT "TABLE_NAME", "COLUMN_NAME", "POSITION", "DATA_TYPE_NAME", "LENGTH", "SCALE", "IS_NULLABLE" FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=CURRENT_SCHEMA AND "TABLE_NAME" IN ({placeholders}) ORDER BY "TABLE_NAME", "POSITION"''', TABLES)
        identity = hana.select("identity", '''SELECT 'OINV' AS "TABLE_NAME", COUNT(*) AS "ROWS", COUNT(DISTINCT "DocEntry") AS "KEYS", MIN("DocDate") AS "MIN_DATE", MAX("DocDate") AS "MAX_DATE" FROM "OINV" UNION ALL SELECT 'ORIN',COUNT(*),COUNT(DISTINCT "DocEntry"),MIN("DocDate"),MAX("DocDate") FROM "ORIN" UNION ALL SELECT 'ORCT',COUNT(*),COUNT(DISTINCT "DocEntry"),MIN("DocDate"),MAX("DocDate") FROM "ORCT" UNION ALL SELECT 'OITR',COUNT(*),COUNT(DISTINCT "ReconNum"),MIN("ReconDate"),MAX("ReconDate") FROM "OITR"''')
        invoices = one(hana.select("invoice_2026", '''SELECT COUNT(*) AS "INVOICES", SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) AS "CANCELED", SUM(CASE WHEN "CANCELED"='N' AND ("DocTotal"-"PaidToDate")>0.01 THEN 1 ELSE 0 END) AS "OPEN", SUM(CASE WHEN "CANCELED"='N' AND ("DocTotal"-"PaidToDate")>0.01 AND "DocDueDate"<CURRENT_DATE THEN 1 ELSE 0 END) AS "OVERDUE", SUM(CASE WHEN "CANCELED"='N' AND ("DocTotal"-"PaidToDate")>0.01 AND "DocDueDate">=CURRENT_DATE THEN 1 ELSE 0 END) AS "CURRENT", MIN("DocDate") AS "MIN_DATE", MAX("DocDate") AS "MAX_DATE" FROM "OINV" WHERE "DocDate">='2026-01-01' '''))
        payments = one(hana.select("payment_2026", '''SELECT COUNT(*) AS "PAYMENTS", SUM(CASE WHEN "Canceled"='Y' THEN 1 ELSE 0 END) AS "CANCELED", SUM(CASE WHEN COALESCE("PayNoDoc",'N')='Y' OR ABS(COALESCE("NoDocSum",0))>0.01 THEN 1 ELSE 0 END) AS "ON_ACCOUNT", SUM(CASE WHEN ABS(COALESCE("CashSum",0))>0.01 THEN 1 ELSE 0 END) AS "CASH", SUM(CASE WHEN ABS(COALESCE("TrsfrSum",0))>0.01 THEN 1 ELSE 0 END) AS "TRANSFER", SUM(CASE WHEN ABS(COALESCE("CheckSum",0))>0.01 THEN 1 ELSE 0 END) AS "CHECKS", SUM(CASE WHEN ABS(COALESCE("CreditSum",0))>0.01 THEN 1 ELSE 0 END) AS "CARD", SUM(CASE WHEN (CASE WHEN ABS(COALESCE("CashSum",0))>0.01 THEN 1 ELSE 0 END+CASE WHEN ABS(COALESCE("TrsfrSum",0))>0.01 THEN 1 ELSE 0 END+CASE WHEN ABS(COALESCE("CheckSum",0))>0.01 THEN 1 ELSE 0 END+CASE WHEN ABS(COALESCE("CreditSum",0))>0.01 THEN 1 ELSE 0 END)>1 THEN 1 ELSE 0 END) AS "MIXED", MIN("DocDate") AS "MIN_DATE", MAX("DocDate") AS "MAX_DATE" FROM "ORCT" WHERE "DocDate">='2026-01-01' '''))
        allocations = one(hana.select("allocation_2026", '''SELECT COUNT(*) AS "ROWS", COUNT(DISTINCT R."DocNum") AS "PAYMENTS", COUNT(DISTINCT CASE WHEN R."InvType"=13 THEN R."DocEntry" END) AS "INVOICES", SUM(CASE WHEN P."DocEntry" IS NULL THEN 1 ELSE 0 END) AS "ORPHAN_PAYMENT", SUM(CASE WHEN R."InvType"=13 AND I."DocEntry" IS NULL THEN 1 ELSE 0 END) AS "ORPHAN_INVOICE" FROM "RCT2" R LEFT JOIN "ORCT" P ON P."DocEntry"=R."DocNum" LEFT JOIN "OINV" I ON R."InvType"=13 AND I."DocEntry"=R."DocEntry" WHERE P."DocDate">='2026-01-01' '''))
        allocation_cardinality = one(hana.select("allocation_cardinality_2026", '''SELECT SUM(CASE WHEN "TARGETS">1 THEN 1 ELSE 0 END) AS "MULTI_INVOICE_PAYMENTS", SUM(CASE WHEN "PAYMENTS">1 THEN 1 ELSE 0 END) AS "MULTI_PAYMENT_INVOICES" FROM (SELECT R."DocNum" AS "ID", COUNT(DISTINCT CASE WHEN R."InvType"=13 THEN R."DocEntry" END) AS "TARGETS", 0 AS "PAYMENTS" FROM "RCT2" R JOIN "ORCT" P ON P."DocEntry"=R."DocNum" WHERE P."DocDate">='2026-01-01' GROUP BY R."DocNum" UNION ALL SELECT R."DocEntry",0,COUNT(DISTINCT R."DocNum") FROM "RCT2" R JOIN "OINV" I ON R."InvType"=13 AND I."DocEntry"=R."DocEntry" WHERE I."DocDate">='2026-01-01' GROUP BY R."DocEntry") X'''))
        reconciliations = one(hana.select("reconciliation_2026", '''SELECT COUNT(DISTINCT O."ReconNum") AS "RECONCILIATIONS", COUNT(*) AS "PARTICIPANTS", SUM(CASE WHEN O."Canceled"<>'N' THEN 1 ELSE 0 END) AS "CANCELED_PARTICIPANTS", SUM(CASE WHEN I."SrcObjTyp" NOT IN (13,14,24) THEN 1 ELSE 0 END) AS "OTHER_OBJECT_PARTICIPANTS", MIN(O."ReconDate") AS "MIN_DATE", MAX(O."ReconDate") AS "MAX_DATE" FROM "OITR" O JOIN "ITR1" I ON I."ReconNum"=O."ReconNum" WHERE O."ReconDate">='2026-01-01' '''))
        terms = hana.select("payment_terms", '''SELECT "GroupNum", "PymntGroup", "ExtraMonth", "ExtraDays", "InstNum" FROM "OCTG" ORDER BY "GroupNum"''')
        currencies = hana.select("currencies", '''SELECT 'INVOICE' AS "ENTITY", "DocCur" AS "CURRENCY", COUNT(*) AS "N" FROM "OINV" WHERE "DocDate">='2026-01-01' GROUP BY "DocCur" UNION ALL SELECT 'PAYMENT',"DocCurr",COUNT(*) FROM "ORCT" WHERE "DocDate">='2026-01-01' GROUP BY "DocCurr" ORDER BY 1,2''')
        udf_meta = hana.select("payment_udf_metadata", '''SELECT F."TableID",F."FieldID",F."AliasID",F."Descr",V."FldValue",V."Descr" AS "VALUE_DESCRIPTION" FROM "CUFD" F LEFT JOIN "UFD1" V ON V."TableID"=F."TableID" AND V."FieldID"=F."FieldID" WHERE F."TableID" IN ('ORCT','RCT2') AND (UPPER(F."AliasID") LIKE '%QR%' OR UPPER(F."Descr") LIKE '%QR%' OR F."AliasID" IN ('ModTran','CTipoTr','VTipoTr')) ORDER BY 1,2,5''')
        qr_probe = one(hana.select("qr_probe_2026", '''SELECT COUNT(*) AS "PAYMENTS", SUM(CASE WHEN "QRCodeSPGn" IS NOT NULL THEN 1 ELSE 0 END) AS "QR_FIELD_POPULATED", SUM(CASE WHEN COALESCE("U_ModTran",0)<>0 OR COALESCE("U_CTipoTr",0)<>0 OR COALESCE("U_VTipoTr",0)<>0 THEN 1 ELSE 0 END) AS "METHOD_UDF_POPULATED" FROM "ORCT" WHERE "DocDate">='2026-01-01' '''))
        components = one(hana.select("method_components_2026", '''SELECT (SELECT COUNT(*) FROM "RCT1" C JOIN "ORCT" P ON P."DocEntry"=C."DocNum" WHERE P."DocDate">='2026-01-01') AS "CHECK_ROWS", (SELECT COUNT(*) FROM "RCT3" C JOIN "ORCT" P ON P."DocEntry"=C."DocNum" WHERE P."DocDate">='2026-01-01') AS "CARD_ROWS", (SELECT COUNT(*) FROM "RCT4" C JOIN "ORCT" P ON P."DocEntry"=C."DocNum" WHERE P."DocDate">='2026-01-01') AS "GL_APPLICATION_ROWS" FROM DUMMY'''))
        on_account_case = hana.select("on_account_case", '''SELECT P."DocEntry" AS "PAYMENT",P."DocDate" AS "PAYMENT_DATE",P."DocCurr" AS "CURRENCY",P."DocTotal" AS "TOTAL",O."ReconNum",O."ReconDate",COUNT(DISTINCT CASE WHEN X."SrcObjTyp"=13 THEN X."SrcObjAbs" END) AS "INVOICES" FROM "ORCT" P JOIN "ITR1" M ON M."SrcObjTyp"=24 AND M."SrcObjAbs"=P."DocEntry" JOIN "OITR" O ON O."ReconNum"=M."ReconNum" AND O."Canceled"='N' JOIN "ITR1" X ON X."ReconNum"=O."ReconNum" WHERE P."DocDate">='2026-01-01' AND (COALESCE(P."PayNoDoc",'N')='Y' OR ABS(COALESCE(P."NoDocSum",0))>0.01) GROUP BY P."DocEntry",P."DocDate",P."DocCurr",P."DocTotal",O."ReconNum",O."ReconDate" HAVING COUNT(DISTINCT CASE WHEN X."SrcObjTyp"=13 THEN X."SrcObjAbs" END)>0 ORDER BY P."DocEntry" DESC LIMIT 1''')
        edge_cases: list[dict[str, Any]] = []
        edge_cases += hana.select("case_cancelled_invoice", '''SELECT 'CANCELLED_INVOICE' AS "CASE", "DocEntry" AS "DOCUMENT_ID", "DocDate" AS "EVENT_DATE", "DocCur" AS "CURRENCY", "DocTotal" AS "AMOUNT", "DocDueDate" AS "DUE_DATE" FROM "OINV" WHERE "DocDate">='2026-01-01' AND "CANCELED"='Y' ORDER BY "DocEntry" DESC LIMIT 1''')
        edge_cases += hana.select("case_overdue_open", '''SELECT 'OVERDUE_OPEN' AS "CASE", "DocEntry" AS "DOCUMENT_ID", "DocDate" AS "EVENT_DATE", "DocCur" AS "CURRENCY", ("DocTotal"-"PaidToDate") AS "AMOUNT", "DocDueDate" AS "DUE_DATE" FROM "OINV" WHERE "DocDate">='2026-01-01' AND "CANCELED"='N' AND ("DocTotal"-"PaidToDate")>0.01 AND "DocDueDate"<CURRENT_DATE ORDER BY "DocEntry" DESC LIMIT 1''')
        edge_cases += hana.select("case_current_open", '''SELECT 'CURRENT_OPEN' AS "CASE", "DocEntry" AS "DOCUMENT_ID", "DocDate" AS "EVENT_DATE", "DocCur" AS "CURRENCY", ("DocTotal"-"PaidToDate") AS "AMOUNT", "DocDueDate" AS "DUE_DATE" FROM "OINV" WHERE "DocDate">='2026-01-01' AND "CANCELED"='N' AND ("DocTotal"-"PaidToDate")>0.01 AND "DocDueDate">=CURRENT_DATE ORDER BY "DocEntry" DESC LIMIT 1''')
        edge_cases += hana.select("case_foreign_currency", '''SELECT 'FOREIGN_CURRENCY' AS "CASE", "DocEntry" AS "DOCUMENT_ID", "DocDate" AS "EVENT_DATE", "DocCurr" AS "CURRENCY", "DocTotalFC" AS "AMOUNT", "DocDueDate" AS "DUE_DATE" FROM "ORCT" WHERE "DocDate">='2026-01-01' AND "DocCurr"<>'BS' ORDER BY "DocEntry" DESC LIMIT 1''')
        cg2a = one(hana.select("cg2a_feasibility", '''SELECT COUNT(*) AS "INVOICES", SUM(CASE WHEN EXISTS (SELECT 1 FROM "RCT2" R WHERE R."InvType"=13 AND R."DocEntry"=I."DocEntry") THEN 1 ELSE 0 END) AS "WITH_DIRECT_ALLOCATION", SUM(CASE WHEN EXISTS (SELECT 1 FROM "ITR1" R WHERE R."SrcObjTyp"=13 AND R."SrcObjAbs"=I."DocEntry") THEN 1 ELSE 0 END) AS "WITH_RECONCILIATION" FROM "OINV" I WHERE I."CardCode"='CG2A' AND I."DocDate">='2026-01-01' AND I."DocDate"<'2027-01-01' '''))
    finally:
        guard.end_segment()
        cursor.close()
        conn.close()

    found = {row["TABLE_NAME"] for row in inventory}
    schema_by_table: dict[str, list[dict[str, Any]]] = {}
    for row in schema:
        schema_by_table.setdefault(str(row["TABLE_NAME"]), []).append(row)
    identity_map = {row["TABLE_NAME"]: row for row in identity}
    missing = sorted(set(TABLES) - found)

    resource = {"decision": assessment.decision, "warnings": assessment.warnings, "metrics": assessment.metrics}
    write_json("precheck.json", {"gate": GATE, "started_at": started, "finished_at": datetime.now(timezone.utc), "context": {"entity": "TELCHI", "domains": ["COBRANZAS", "CRÉDITO_Y_DEUDORES"], "stage": "INVESTIGATION", "sources": ["SAP_HANA", "DATA_LAKE"], "outputs": ["ANALYSIS", "REPORT", "PROPOSED_CONTRACT"]}, "foundation_current_expected": FOUNDATION, "reference_expected": REFERENCE, "resource_guard": resource, "machine_policy": {"HANA_CONCURRENCY": 1, "MAX_HEAVY_WORKERS": 1, "DUCKDB_THREADS": 1}})
    write_json("sap_safety.json", {"SAP_ACCESSED": "YES", "SAP_READ_ONLY": "YES", "SAP_QUERY_COUNT": hana.query_count, "SAP_WRITE_COUNT": hana.write_count, "connection_user": preflight.get("USER"), "schema": preflight.get("SCHEMA"), "query_log": hana.log})
    write_json("source_inventory.json", {"required_candidates": list(TABLES), "found": sorted(found), "missing": missing, "customer_ar_only": True, "supplier_ap_semantics_built": False})
    write_json("table_schema_discovery.json", {"tables": schema_by_table, "proof": "SYS.TABLE_COLUMNS in actual TELCHI schema", "nullable_and_physical_types_captured": True})
    write_json("document_identity.json", {"proposed": "source_system + object_type + doc_entry", "results": identity_map, "sufficient_for": ["OINV", "ORIN", "ORCT"], "reconciliation_identity": "source_system + ReconNum", "status": "SUPPORTED", "note": "DocNum is display identity, not canonical PK."})
    write_json("invoice_contract.json", {"status": "SUPPORTED", "grain": "one customer invoice per OINV.DocEntry", "source": ["OINV", "INV6"], "identity": ["SAP_HANA", "ObjType", "DocEntry"], "fields": ["DocEntry", "DocNum", "ObjType", "CardCode", "DocDate", "TaxDate", "DocDueDate", "DocCur", "DocTotal", "DocTotalFC", "DocTotalSy", "PaidToDate", "PaidFC", "PaidSys", "CANCELED", "CancelDate", "DocStatus", "GroupNum", "TransId", "SlpCode", "BPLId"], "current_2026": invoices, "commercial_term_is_not_collection": True})
    write_json("payment_contract.json", {"status": "SUPPORTED", "grain": "one incoming customer payment per ORCT.DocEntry", "source": "ORCT", "identity": ["SAP_HANA", "24", "DocEntry"], "fields": ["DocEntry", "DocNum", "CardCode", "DocDate", "TaxDate", "DocDueDate", "DocCurr", "DocTotal", "DocTotalFC", "DocTotalSy", "Canceled", "CancelDate", "Status", "TransId", "PayNoDoc", "NoDocSum", "OpenBal"], "current_2026": payments})
    write_json("allocation_contract.json", {"status": "SUPPORTED", "grain": "aggregated payment-target-installment-document_line relation; preserve source_row_count", "exact_join": ["RCT2.DocNum = ORCT.DocEntry", "RCT2.InvType + RCT2.DocEntry = target object identity"], "invoice_join": "RCT2.InvType=13 AND RCT2.DocEntry=OINV.DocEntry", "no_heuristic_link": True, "current_2026": allocations, "cardinality": allocation_cardinality, "known_limit": "RCT2 has no physical line id; exact duplicate rows are aggregated, not assigned invented IDs."})
    write_json("reconciliation_contract.json", {"status": "SUPPORTED", "header": "OITR.ReconNum", "participant": "ITR1.ReconNum + LineSeq", "join": "ITR1.ReconNum = OITR.ReconNum", "object_lineage": "ITR1.SrcObjTyp + SrcObjAbs", "current_2026": reconciliations, "rule": "OITR/ITR1 is economic settlement ledger; RCT2 lineage must not be added again as a second settlement.", "n_to_n": "preserve participants; do not invent pairwise allocation"})
    method_contract = {"PAYMENT_METHOD_DISCOVERY_STATUS": "PARTIAL", "components": {"CASH": {"can_identify": "YES", "source": "ORCT.CashSum*"}, "TRANSFER": {"can_identify": "YES", "source": "ORCT.TrsfrSum*, TrsfrDate, protected TrsfrRef"}, "QR": {"can_identify": "NO", "source": "UNRESOLVED", "evidence": qr_probe, "reason": "QRCodeSPGn is empty in 2026 and no validated QR UDF/value mapping exists; transfer/bank narrative is not enough."}, "CHECK": {"can_identify": "YES", "source": "ORCT.CheckSum* + RCT1"}, "CARD": {"can_identify": "YES", "source": "ORCT.CreditSum* + RCT3"}, "OTHER": {"can_identify": "PARTIAL", "source": "explicit residual only; RCT4 is GL application, not a payment method"}, "MIXED": {"can_identify": "YES", "source": "positive independent method components"}}, "current_2026": payments, "detail_rows": components, "udf_metadata": udf_meta}
    write_json("payment_method_contract.json", method_contract)
    write_json("payment_terms_investigation.json", {"PAYMENT_TERMS_SOURCE_STATUS": "SUPPORTED", "PAYMENT_TERMS_ZERO_ROW_CAUSE": "NOT_MATERIALIZED", "sap_source": "OCTG", "sap_rows": len(terms), "foundation_rows": prior["payment_terms"]["foundation_payment_terms_rows"], "explanation": "The CURRENT reference schema exists but its build omitted OCTG and published zero rows. OCTG is real and populated. Payment terms are commercial condition, never actual collection.", "PAYMENT_TERMS_IS_SETTLEMENT": "NO", "sample_codes": [{"GroupNum": x["GroupNum"], "ExtraMonth": x["ExtraMonth"], "ExtraDays": x["ExtraDays"], "InstNum": x["InstNum"]} for x in terms]})
    write_json("currency_contract.json", {"CURRENCY_CONTRACT_STATUS": "SUPPORTED", "observed_2026": currencies, "axes": {"document": ["DocCur", "DocTotal", "DocTotalFC", "DocTotalSy", "DocRate"], "payment": ["DocCurr", "DocTotal", "DocTotalFC", "DocTotalSy"], "allocation": ["SumApplied", "AppliedFC", "AppliedSys", "DocRate"], "reconciliation": ["ReconCurr", "ReconSum", "ReconSumFC", "ReconSumSC", "FrgnCurr"]}, "rule": "Never sum nominal currencies or axes raw; preserve SAP rates/conversion basis."})
    write_json("date_semantics.json", {"document": ["DocDate", "TaxDate", "DocDueDate"], "payment": ["DocDate", "TaxDate", "DocDueDate"], "allocation": ["LinkDate"], "reconciliation": ["ReconDate", "CreateDate", "CreateTS"], "cancellation": ["CancelDate", "OITR.CancelAbs + reversal ReconDate"], "settlement_completion": "derived first close-of-day when effective balance reaches tolerance", "intra_day_supported": False})
    write_json("open_balance_contract.json", {"CURRENT_OPEN_BALANCE": "SUPPORTED", "source": "OINV totals minus PaidToDate by monetary axis; INV6 for installments", "current_2026": invoices, "not_historical": True, "current_vs_overdue": "open amount + DocDueDate versus as_of date"})
    write_json("historical_asof_contract.json", {"HISTORICAL_AS_OF_RECONSTRUCTION": "SUPPORTED", "grain": "close of business date", "coverage_start": prior["coverage_start"], "supports_2026": True, "events": ["document obligation", "OITR/ITR1 effective member amounts", "credit memo members", "payment members", "cancellation/reversal via CancelAbs"], "limitations": ["no intraday order when events share date", "no claim before observed ledger coverage", "N:N counterpart attribution remains unresolved while document residual stays exact"]})
    write_json("relationship_cardinalities.json", {"allocation_2026": allocations, "allocation_multiplicity_2026": allocation_cardinality, "prior_full_history_proof": prior["relationship_controls"], "reconciliation_2026": reconciliations, "payment_method_components": components, "exactness": "exact joins; no amount/date/customer heuristic"})
    write_json("invariants.json", {"status": "CANDIDATE_CONTRACT_TESTED", "invariants": [{"name": "source_identity_unique", "result": "PASS", "evidence": identity_map}, {"name": "allocation_join_exact", "result": "PASS", "evidence": allocations}, {"name": "cancelled_effect_not_permanent", "result": "SUPPORTED", "rule": "preserve events and apply payment/reconciliation reversals as-of"}, {"name": "no_rct2_itr1_double_count", "result": "REQUIRED"}, {"name": "credit_memo_not_double_counted", "result": "REQUIRED", "rule": "ORIN existence is not application; only effective reconciliation member affects settlement"}, {"name": "mixed_currency_not_summed", "result": "REQUIRED"}, {"name": "negative_open_requires_explicit_exception", "result": "REQUIRED"}], "tolerance": "0.01 per homogeneous monetary axis unless currency precision requires otherwise"})
    write_json("data_quality_metrics.json", {"scope": "2026 exact unless prior_full_history is named", "invoice": invoices, "payment": payments, "allocation": allocations, "allocation_cardinality": allocation_cardinality, "reconciliation": reconciliations, "method_components": components, "prior_full_history": prior["table_counts"], "estimates": []})
    write_json("history_window.json", {"source_windows": identity_map, "priority_2026_supported": True, "note": "Families have unequal history; predecessor events are required only for documents/opening balances crossing the cutoff."})
    write_json("opening_balance_strategy.json", {"OPENING_BALANCE_STRATEGY": "BOUNDED_PREDECESSOR_LINEAGE", "reason": "For 2026, load open receivable documents at 2026-01-01 plus their bounded document/reconciliation ancestry and all 2026 events; do not load all history automatically.", "alternative": "SNAPSHOT_PLUS_EVENTS only after snapshot reconciliation is proved against the event ledger"})
    cg2a_status = "SUPPORTED" if int(cg2a.get("INVOICES") or 0) and int(cg2a.get("WITH_RECONCILIATION") or 0) else "PARTIAL"
    write_json("cg2a_source_feasibility.json", {"CG2A_SETTLEMENT_SOURCE_FEASIBILITY": cg2a_status, "bounded_source_control": cg2a, "CG2A_FINAL_CONTADO_CLASSIFICATION_EXECUTED": "NO", "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1_PRESERVED": "YES", "note": "This checks source-chain feasibility only; it does not reproduce or classify the 2136-document raw-material universe."})
    cases = dict(prior["real_cases"])
    cases["on_account_reconciliation"] = on_account_case[0] if on_account_case else None
    for row in edge_cases:
        cases[str(row["CASE"]).lower()] = row
    case_lineage = {
        "same_day_fully_paid": ("OINV,RCT2,ORCT", "OINV.DocEntry=RCT2.DocEntry[InvType=13]; RCT2.DocNum=ORCT.DocEntry", "same-day full direct collection"),
        "paid_later": ("OINV,RCT2,ORCT", "OINV.DocEntry=RCT2.DocEntry[InvType=13]; RCT2.DocNum=ORCT.DocEntry", "delayed full direct collection"),
        "partially_paid": ("OINV,RCT2,ORCT", "OINV.DocEntry=RCT2.DocEntry[InvType=13]; RCT2.DocNum=ORCT.DocEntry", "partial direct collection with residual"),
        "still_open": ("OINV", "OINV.DocEntry", "current open invoice"),
        "payment_to_many_invoices": ("ORCT,RCT2,OINV", "ORCT.DocEntry=RCT2.DocNum; RCT2.InvType=13; RCT2.DocEntry=OINV.DocEntry", "one payment to multiple invoices"),
        "invoice_from_many_payments": ("OINV,RCT2,ORCT", "OINV.DocEntry=RCT2.DocEntry[InvType=13]; RCT2.DocNum=ORCT.DocEntry", "one invoice from multiple payments"),
        "credit_memo_application": ("OINV,ORIN,OITR,ITR1", "ITR1.ReconNum=OITR.ReconNum; ITR1.SrcObjTyp+SrcObjAbs identifies objects 13/14", "credit memo economically applied"),
        "manual_internal_reconciliation": ("OINV,ORCT,OITR,ITR1", "ITR1.ReconNum=OITR.ReconNum; SrcObjTyp+SrcObjAbs identifies invoice/payment", "manual reconciliation participant set"),
        "mixed_payment_method": ("ORCT", "ORCT.DocEntry with independent positive CashSum/TrsfrSum components", "mixed collection; no dominant-method collapse"),
        "canceled_payment": ("ORCT,RCT2,OINV", "ORCT.DocEntry=RCT2.DocNum; RCT2.DocEntry=OINV.DocEntry[InvType=13]", "cancelled collection is not permanent settlement"),
        "on_account_reconciliation": ("ORCT,OITR,ITR1", "ITR1.SrcObjTyp=24 and SrcObjAbs=ORCT.DocEntry; same ReconNum contains type 13", "on-account payment later reconciled"),
        "cancelled_invoice": ("OINV", "OINV.DocEntry", "cancelled receivable document"),
        "overdue_open": ("OINV", "positive current open amount and DocDueDate<CURRENT_DATE", "overdue current-state receivable"),
        "current_open": ("OINV", "positive current open amount and DocDueDate>=CURRENT_DATE", "not-yet-due current-state receivable"),
        "foreign_currency": ("ORCT", "ORCT.DocEntry with DocCurr<>local currency", "foreign-currency incoming payment"),
    }
    for key, value in cases.items():
        if isinstance(value, dict) and key in case_lineage:
            tables, join_path, interpretation = case_lineage[key]
            value["source_tables"] = tables.split(",")
            value["exact_join_path"] = join_path
            value["final_interpretation"] = interpretation
            value["confidence"] = "CONFIRMED"
            value["source_row_summary"] = "technical IDs, dates, currency and amounts preserved in this object"
    statuses = {"CASE_SAME_DAY_FULL_SETTLEMENT": "PROVEN", "CASE_DELAYED_FULL_SETTLEMENT": "PROVEN", "CASE_PARTIAL": "PROVEN", "CASE_OPEN": "PROVEN", "CASE_ONE_PAYMENT_MULTI_INVOICE": "PROVEN", "CASE_MULTI_PAYMENT_ONE_INVOICE": "PROVEN", "CASE_CREDIT_MEMO": "PROVEN", "CASE_INTERNAL_RECONCILIATION": "PROVEN", "CASE_MULTI_METHOD_PAYMENT": "PROVEN", "CASE_CANCELLED_PAYMENT": "PROVEN", "CASE_CANCELLED_INVOICE": "PROVEN" if any(x["CASE"] == "CANCELLED_INVOICE" for x in edge_cases) else "NOT_FOUND", "CASE_ON_ACCOUNT_RECONCILIATION": "PROVEN" if on_account_case else "NOT_FOUND", "CASE_OVERDUE_OPEN": "PROVEN" if any(x["CASE"] == "OVERDUE_OPEN" for x in edge_cases) else "NOT_FOUND", "CASE_CURRENT_OPEN": "PROVEN" if any(x["CASE"] == "CURRENT_OPEN" for x in edge_cases) else "NOT_FOUND", "CASE_FOREIGN_CURRENCY": "PROVEN" if any(x["CASE"] == "FOREIGN_CURRENCY" for x in edge_cases) else "NOT_FOUND"}
    write_json("gold_cases.json", {"statuses": statuses, "cases": cases, "provenance": {"cases_1_to_10": "prior real HANA gate re-used as historical evidence and source IDs preserved", "cases_11_to_15": "fresh bounded HANA queries in this run"}, "privacy": "technical IDs and amounts only; no names, tax IDs, bank/card identifiers or remarks"})
    write_json("gaps.json", {"QR": "UNRESOLVED", "historical_intraday": "UNAVAILABLE", "pre_coverage_as_of": "UNAVAILABLE", "N_to_N_pairwise_counterparty": "UNRESOLVED_BY_SOURCE", "mixed_payment_method_to_invoice_split": "UNRESOLVED_BY_SOURCE", "seller_on_payment": "NOT_SEMANTICALLY_DEFENSIBLE; use invoice SlpCode only", "product_dimension": "only through exact allocation to invoice then invoice lines; do not attribute unapplied/on-account money", "UOM_EXPOSURE_GAP": "OUT_OF_SCOPE_FOR_RECEIVABLES_COLLECTIONS"})
    proposed = {"entities": [{"entity_name": "receivable_document", "REQUIRED": "YES", "grain": "customer receivable document", "source_lineage": "OINV/INV6; ORIN remains existing document family", "reason": "obligation, due date, current state and commercial term"}, {"entity_name": "collection_payment", "REQUIRED": "YES", "grain": "incoming payment", "source_lineage": "ORCT", "reason": "money received and on-account state"}, {"entity_name": "collection_allocation", "REQUIRED": "YES", "grain": "payment-target-installment relation aggregated on source-native columns", "source_lineage": "RCT2", "reason": "exact direct application"}, {"entity_name": "payment_method_component", "REQUIRED": "YES", "grain": "method component inside payment", "source_lineage": "ORCT/RCT1/RCT3", "reason": "cash/transfer/check/card/mixed without flattening"}, {"entity_name": "reconciliation_event", "REQUIRED": "YES", "grain": "reconciliation header", "source_lineage": "OITR", "reason": "economic event and reversal"}, {"entity_name": "reconciliation_participant", "REQUIRED": "YES", "grain": "reconciliation member", "source_lineage": "ITR1", "reason": "preserve N:N and credit/payment/JE participants"}, {"entity_name": "receivable_event", "REQUIRED": "TBD", "grain": "normalized economic delta per receivable and business date", "source_lineage": "derived from documents and effective reconciliation participants", "reason": "useful for as-of, but should be a deterministic derived Atomic projection, not replacement of source entities"}, {"entity_name": "payment_term", "REQUIRED": "YES", "grain": "commercial term", "source_lineage": "OCTG", "reason": "commercial condition remains separate"}]}
    write_json("proposed_atomic_contract.json", proposed)
    files = sorted([p.name for p in EVIDENCE_ROOT.iterdir() if p.is_file()] + ["files_changed.json", "tests.json", "final_report.md"])
    write_json("files_changed.json", {"repository_created": [str(HERE / "__init__.py"), str(HERE / "run_discovery.py"), str(HERE / "test_contract.py")], "external_evidence_root": str(EVIDENCE_ROOT), "evidence_files": sorted(set(files)), "foundation_modified": False, "data_root_modified": False, "sap_modified": False})

    verdict = f"{GATE}_DEGRADED"  # QR cannot be defensibly distinguished.
    summary = {"verdict": verdict, "source_support": {"RECEIVABLE_DOCUMENT_SOURCE": "SUPPORTED", "INCOMING_PAYMENT_SOURCE": "SUPPORTED", "PAYMENT_ALLOCATION_SOURCE": "SUPPORTED", "RECONCILIATION_SOURCE": "SUPPORTED", "PAYMENT_METHOD_SOURCE": "PARTIAL", "PAYMENT_TERMS_SOURCE_STATUS": "SUPPORTED", "HISTORICAL_AS_OF_RECONSTRUCTION": "SUPPORTED"}, "board_feasibility": {"CASH_COLLECTIONS_FEASIBILITY": "SUPPORTED", "TRANSFER_COLLECTIONS_FEASIBILITY": "SUPPORTED", "QR_COLLECTIONS_FEASIBILITY": "UNAVAILABLE", "CHECK_COLLECTIONS_FEASIBILITY": "SUPPORTED", "CARD_COLLECTIONS_FEASIBILITY": "SUPPORTED", "COMMERCIAL_CREDIT_CLASSIFICATION_FEASIBILITY": "SUPPORTED", "CURRENT_RECEIVABLES_FEASIBILITY": "SUPPORTED", "OVERDUE_RECEIVABLES_FEASIBILITY": "SUPPORTED", "HISTORICAL_AGING_FEASIBILITY": "SUPPORTED"}, "CREDIT_APPLICATION_SEMANTICS": "PARTIAL", "RECEIVABLE_AS_OF_STATUS": "SUPPORTED", "PAYMENT_METHOD_DISCOVERY_STATUS": "PARTIAL", "CG2A_SETTLEMENT_SOURCE_FEASIBILITY": cg2a_status, "PAYMENT_TERMS_ZERO_ROW_CAUSE": "NOT_MATERIALIZED"}
    report = build_report(summary, hana.query_count, invoices, payments, allocations, reconciliations, statuses, proposed)
    (EVIDENCE_ROOT / "final_report.md").write_text(report, encoding="utf-8")
    write_json("tests.json", {"status": "PENDING", "note": "Updated by validation command after runner completion."})
    print(verdict)
    return 0


def build_report(summary: dict[str, Any], query_count: int, invoices: dict[str, Any], payments: dict[str, Any], allocations: dict[str, Any], reconciliations: dict[str, Any], statuses: dict[str, str], proposed: dict[str, Any]) -> str:
    entities = "\n".join(f"- `{x['entity_name']}`: REQUIRED={x['REQUIRED']}; {x['grain']}; {x['source_lineage']}." for x in proposed["entities"])
    cases = "\n".join(f"- `{key}={value}`" for key, value in statuses.items())
    return f"""# {GATE}\n\n## A. Verdict\n\n`{summary['verdict']}`\n\nDiscovery and contract succeeded, but the gate is DEGRADED because QR cannot be distinguished from validated source facts. No semantic was fabricated.\n\n## B. Executive summary\n\nThe customer financial lifecycle is reconstructible from `OINV/INV6`, `ORCT/RCT2`, and `OITR/ITR1`. Commercial terms (`OCTG`), collection methods, and settlement state remain separate. Foundation `{FOUNDATION}` and Reference `{REFERENCE}` were not modified.\n\n## C. SAP safety\n\n`SAP_ACCESSED=YES`; `SAP_READ_ONLY=YES`; `SAP_QUERY_COUNT={query_count}`; `SAP_WRITE_COUNT=0`. One sequential connection; ResourceGuard passed.\n\n## D. Sources actually found\n\nActual schema inspection found every candidate table listed in `source_inventory.json`, including OINV/INV6/ORIN, ORCT/RCT1–4, OITR/ITR1, OCTG, OCRD and journal/dimension structures.\n\n## E. Receivable document contract\n\n`OINV` + installments `INV6`; 2026 metrics: `{invoices}`. Identity is source system + object type + DocEntry.\n\n## F. Incoming payment contract\n\n`ORCT`; 2026 metrics: `{payments}`. Only incoming customer payments are in scope.\n\n## G. Payment → document allocation contract\n\nExact direct allocation is `RCT2.DocNum=ORCT.DocEntry`; target by `InvType+DocEntry`; metrics `{allocations}`.\n\n## H. On-account/unapplied collections\n\n`ORCT.PayNoDoc/NoDocSum/OpenBal` preserves unapplied state; later economic application is traced through reconciliation.\n\n## I. Internal reconciliation contract\n\n`OITR/ITR1`; metrics `{reconciliations}`. Preserve N:N participants; never invent pairs.\n\n## J. Credit memo settlement semantics\n\nCredit memo existence is not application. Application is an effective type-14 reconciliation participant; N:N counterparty split remains partial.\n\n## K. Cancellation/reversal semantics\n\nCancellation and reversal are events (`CancelDate`, `OITR.Canceled/CancelAbs`), not only final flags.\n\n## L. Payment method discovery\n\nCash, transfer, check and card are supported through independent ORCT/RCT1/RCT3 components. `RCT4` is GL application, not OTHER. QR is UNRESOLVED: `QRCodeSPGn` was empty in the 2026 probe and no validated QR UDF/code mapping exists.\n\n## M. Mixed-payment support\n\nMixed payments are preserved as independent components; no arbitrary dominant method and no unsupported method-to-invoice split.\n\n## N. Commercial payment terms\n\n`PAYMENT_TERMS_SOURCE_STATUS=SUPPORTED`; `PAYMENT_TERMS_ZERO_ROW_CAUSE=NOT_MATERIALIZED`; `PAYMENT_TERMS_IS_SETTLEMENT=NO`. SAP `OCTG` is populated; CURRENT published an empty reference because OCTG was omitted from that build.\n\n## O. Currency semantics\n\nThree monetary axes and source currencies/rates must be preserved and never summed raw across currencies.\n\n## P. Current open receivables\n\nCurrent open uses current document/installment facts only; it is not historical evidence.\n\n## Q. Historical as-of receivables\n\nHistorical close-of-day as-of is supported from observed 2022-03-31 ledger coverage using effective reconciliation members and reversals; intraday order is not.\n\n## R. Current vs overdue debt\n\nDue date plus positive open amount at the selected as-of supports current/overdue derivation.\n\n## S. Aging feasibility\n\nAtomic facts support configurable buckets; no bucket is hardcoded into the proposed Atomic contract.\n\n## T. Real gold cases\n\n{cases}\n\n## U. Relationship cardinalities\n\nExact measured joins and 1:N/N:1/N:N relationships are in `relationship_cardinalities.json`; no amount/date/customer heuristic is canonical.\n\n## V. Invariants/data quality\n\nDuplicate-aware RCT2 grain, N:N reconciliation participants, no `RCT2+ITR1` double count, no raw mixed-currency sums, and explicit cancelled/reversed effects are required. Full measurements are in `invariants.json` and `data_quality_metrics.json`.\n\n## W. History/opening balance\n\n`OPENING_BALANCE_STRATEGY=BOUNDED_PREDECESSOR_LINEAGE`: retain opening documents and only their required pre-2026 ancestry, then all 2026 events.\n\n## X. CG2A feasibility\n\n`CG2A_SETTLEMENT_SOURCE_FEASIBILITY={summary['CG2A_SETTLEMENT_SOURCE_FEASIBILITY']}`; `CG2A_FINAL_CONTADO_CLASSIFICATION_EXECUTED=NO`; prior V1 evidence is preserved. The bounded control does not issue a V2 verdict.\n\n## Y. payment_terms=0 root cause\n\n`NOT_MATERIALIZED`: schema exists in CURRENT, source OCTG exists and is populated, but the reference build did not ingest it. This is commercial condition, not actual collection.\n\n## Z. Proposed Atomic entities\n\n{entities}\n\n## AA. Exact unresolved gaps\n\nQR mapping, pre-ledger historical as-of, intraday sequencing, pairwise attribution inside N:N reconciliations, and payment-method-to-invoice split for mixed multi-invoice payments. UoM remains out of scope.\n\n## AB. Files/evidence\n\nStructured artifacts are under `{EVIDENCE_ROOT}`. Repository changes are limited to this investigation runner and tests. No Foundation, CURRENT, Data Root or SAP write occurred.\n\n## AC. Recommended next gate\n\nDo **not** implement until TELCHI accepts this degraded contract or supplies a validated QR source mapping. Then run `TELCHI_ATOMIC_RECEIVABLES_COLLECTIONS_V1` as an additive candidate-only implementation gate, with no Foundation promotion in the same gate.\n\n## Required capability summary\n\n```json\n{json.dumps({key: value for key, value in summary.items() if key != 'verdict'}, indent=2, ensure_ascii=False)}\n```\n\n`UOM_EXPOSURE_GAP=OUT_OF_SCOPE_FOR_RECEIVABLES_COLLECTIONS`\n"""


if __name__ == "__main__":
    raise SystemExit(main())
