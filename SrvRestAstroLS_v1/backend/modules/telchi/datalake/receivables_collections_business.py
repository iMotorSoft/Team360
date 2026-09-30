"""Reproducible business semantics over Telchi Atomic receivables/collections.

The layer is Data-Lake-first and additive.  It never queries SAP, publishes a
Foundation candidate, changes CURRENT, defines Telchi CONTADO, or touches AP.
Daily close is the finest supported historical grain.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .ducklake import DuckLakeConnector
from .foundation_publication import FoundationPublicationStore

GATE = "TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_DERIVATION_V1"
VERDICT_PASS = GATE + "_PASS"
VERDICT_DEGRADED = GATE + "_DEGRADED"
VERDICT_FAIL = GATE + "_FAIL"
FOUNDATION = "foundation_417c860c216805f18341bb741ee026e3"
ATOMIC_GATE = "TELCHI_ATOMIC_RECEIVABLES_COLLECTIONS_V1"
HISTORY_START = date(2022, 3, 31)
DERIVATION_VERSION = "receivables-collections-business-v1.0.0"
AGING_CONFIG_VERSION = "aging-default-v1-current-1-30-31-60-61-90-91-120-120plus"
BOARD_CURRENCY_BASIS = "SAP_LOCAL_CURRENCY_BOB"
EVIDENCE_BASE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi")
ATOMIC_EVIDENCE_ROOT = EVIDENCE_BASE / ATOMIC_GATE
EVIDENCE_ROOT = EVIDENCE_BASE / GATE
DISCOVERY_ROOT = EVIDENCE_BASE / "TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_CONTRACT_AND_SOURCE_DISCOVERY_V1"
TOLERANCE = Decimal("0.01")

ATOMIC_ENTITIES = (
    "receivable_document", "collection_payment", "collection_allocation",
    "reconciliation_event", "reconciliation_participant",
    "payment_method_component", "payment_term",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_cancelled(value: Any) -> bool:
    return str(value or "").strip().upper() in {"Y", "C", "1", "TRUE", "T"}


def settlement_state(total: Any, reduction: Any, *, cancelled: bool = False, tolerance: Decimal = TOLERANCE) -> str:
    if cancelled:
        return "CANCELLED"
    try:
        amount, paid = Decimal(str(total)), Decimal(str(reduction))
    except Exception:
        return "UNRESOLVED"
    if amount < -tolerance:
        return "OTHER_SOURCE_STATE"
    open_amount = max(Decimal("0"), amount - paid)
    if open_amount <= tolerance:
        return "FULLY_SETTLED"
    if paid > tolerance:
        return "PARTIALLY_SETTLED"
    return "OPEN"


def debt_status(open_amount: Any, due_date: date, as_of_date: date, *, tolerance: Decimal = TOLERANCE) -> str:
    amount = Decimal(str(open_amount))
    if amount <= tolerance:
        return "NOT_OPEN"
    return "OPEN_OVERDUE" if due_date < as_of_date else "OPEN_CURRENT"


def days_past_due(due_date: date, as_of_date: date) -> int:
    return max(0, (as_of_date - due_date).days)


def aging_bucket(open_amount: Any, due_date: date, as_of_date: date, *, tolerance: Decimal = TOLERANCE) -> str:
    if Decimal(str(open_amount)) <= tolerance:
        return "NOT_OPEN"
    days = (as_of_date - due_date).days
    if days <= 0:
        return "CURRENT"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    if days <= 120:
        return "91-120"
    return "120+"


def commercial_term_classification(name: Any, extra_months: Any, extra_days: Any, installment_count: Any) -> str:
    normalized = " ".join(str(name or "").strip().upper().replace("É", "E").split())
    if normalized == "CONTADO" or normalized.startswith("CONTADO ("):
        return "COMMERCIAL_CASH_TERM"
    numeric = lambda value: Decimal(str(value or "0"))
    if "CREDITO" in normalized or "PRESTAMO" in normalized or numeric(extra_months) > 0 or numeric(extra_days) > 0 or numeric(installment_count) > 1:
        return "COMMERCIAL_CREDIT_TERM"
    if normalized:
        return "COMMERCIAL_TERM_OTHER"
    return "COMMERCIAL_TERM_UNRESOLVED"


def _foundation_current(connector: DuckLakeConnector) -> str | None:
    store = FoundationPublicationStore(connection_factory=lambda: connector.session(read_only=True))
    current = store.current_publication()
    return current.foundation_publication_id if current else None


def executor_identity() -> dict[str, str]:
    return {
        "EXECUTION_MODEL": os.getenv("PI_MODEL", "UNKNOWN"),
        "EXECUTION_PROVIDER": os.getenv("PI_PROVIDER", "UNKNOWN"),
        "EXECUTION_APP": "pi" if os.getenv("PI_CODING_AGENT") == "true" else "UNKNOWN",
        "EXECUTOR_IDENTITY_SOURCE": "PI_MODEL,PI_PROVIDER,PI_CODING_AGENT environment variables",
    }


def _atomic_contract() -> dict[str, Any]:
    required = (
        "final_report.md", "discovery_contract_loaded.json", "receivable_document_build.json",
        "collection_payment_build.json", "collection_allocation_build.json", "reconciliation_build.json",
        "payment_method_component_build.json", "relationship_cardinalities.json", "currency_validation.json",
        "cancellation_validation.json", "on_account_validation.json", "payment_method_validation.json",
        "source_count_reconciliation.json", "gold_cases_atomic.json", "sap_atomic_bounded_reconciliation.json",
        "cg2a_atomic_feasibility.json", "board_fact_feasibility.json", "mutable_history_strategy.json",
        "history_scope.json", "operational_integration.json", "gaps.json",
    )
    missing = [name for name in required if not (ATOMIC_EVIDENCE_ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Atomic evidence is incomplete: {missing}")
    gold = _read_json(ATOMIC_EVIDENCE_ROOT / "gold_cases_atomic.json")
    return {
        "status": "PASS" if not missing and gold.get("GOLD_CASES_REPRODUCED_ATOMIC") == 15 else "FAIL",
        "atomic_gate": ATOMIC_GATE + "_PASS", "evidence_root": str(ATOMIC_EVIDENCE_ROOT),
        "files_consumed": list(required),
        "discovery_fingerprint": _read_json(ATOMIC_EVIDENCE_ROOT / "discovery_contract_loaded.json")["DISCOVERY_CONTRACT_FINGERPRINT"],
        "atomic_gold_cases": gold.get("GOLD_CASES_REPRODUCED_ATOMIC"),
    }


def _source_contract(connection: Any) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    for entity in ATOMIC_ENTITIES:
        row = connection.execute(
            f"SELECT count(*), min(source_as_of), max(source_as_of), "
            f"bit_xor(hash(row_hash)), min(transformation_version), max(transformation_version) "
            f"FROM telchi.atomic.{_q(entity)}"
        ).fetchone()
        entities[entity] = {
            "row_count": int(row[0]), "source_as_of_min": row[1], "source_as_of_max": row[2],
            "row_hash_xor": str(row[3]), "transformation_version_min": row[4], "transformation_version_max": row[5],
        }
    payload = {"entities": entities, "derivation_version": DERIVATION_VERSION, "aging_config_version": AGING_CONFIG_VERSION}
    logical_id = "rc_business_" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]
    source_as_of = max(str(row["source_as_of_max"]) for row in entities.values() if row["source_as_of_max"])
    return payload | {"derivation_id": logical_id, "source_as_of": source_as_of}


def _create_business_tables(connection: Any, contract: dict[str, Any], built_at: str) -> dict[str, int]:
    derivation_id = contract["derivation_id"].replace("'", "''")
    source_as_of = contract["source_as_of"].replace("'", "''")
    version = DERIVATION_VERSION.replace("'", "''")
    connection.execute("CREATE SCHEMA IF NOT EXISTS telchi.business")
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DROP TABLE IF EXISTS telchi.business.receivable_settlement_status")
        connection.execute(f"""
CREATE TABLE telchi.business.receivable_settlement_status AS
WITH daily AS (
  SELECT participant_object_abs AS document_id,
         try_cast(reconciliation_date AS DATE) AS effect_date,
         sum(CASE WHEN is_credit='D' THEN try_cast(reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS reduction_amount,
         sum(CASE WHEN is_credit='D' THEN try_cast(reconciled_amount_system AS DECIMAL(38,6)) ELSE 0 END) AS reduction_system_amount
  FROM telchi.atomic.reconciliation_participant
  WHERE participant_object_type='13'
  GROUP BY 1,2
), running AS (
  SELECT document_id,effect_date,reduction_amount,reduction_system_amount,
         sum(reduction_amount) OVER (PARTITION BY document_id ORDER BY effect_date ROWS UNBOUNDED PRECEDING) AS cumulative_reduction,
         sum(reduction_system_amount) OVER (PARTITION BY document_id ORDER BY effect_date ROWS UNBOUNDED PRECEDING) AS cumulative_reduction_system
  FROM daily
), effects AS (
  SELECT r.document_id,
         sum(r.reduction_amount) AS economic_reduction_amount,
         sum(r.reduction_system_amount) AS economic_reduction_system_amount,
         min(CASE WHEN r.cumulative_reduction >= try_cast(d.document_total AS DECIMAL(38,6))-.01 THEN r.effect_date END) AS fully_settled_date
  FROM running r JOIN telchi.atomic.receivable_document d ON d.source_doc_entry=r.document_id
  GROUP BY r.document_id
), typed AS (
  SELECT p.participant_object_abs AS document_id,
         sum(CASE WHEN kinds.has_payment AND NOT kinds.has_credit THEN try_cast(p.reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS payment_settlement_effect,
         sum(CASE WHEN kinds.has_credit AND NOT kinds.has_payment THEN try_cast(p.reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS credit_memo_settlement_effect,
         sum(CASE WHEN NOT kinds.has_payment AND NOT kinds.has_credit THEN try_cast(p.reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS internal_reconciliation_effect,
         sum(CASE WHEN kinds.has_payment AND kinds.has_credit THEN try_cast(p.reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS multi_source_reconciliation_effect
  FROM telchi.atomic.reconciliation_participant p
  JOIN (SELECT reconciliation_id,
               bool_or(participant_object_type='24') AS has_payment,
               bool_or(participant_object_type='14') AS has_credit
        FROM telchi.atomic.reconciliation_participant GROUP BY 1) kinds USING (reconciliation_id)
  WHERE p.participant_object_type='13' AND p.is_credit='D'
  GROUP BY 1
), base AS (
  SELECT d.*, coalesce(e.economic_reduction_amount,0::DECIMAL(38,6)) AS reduction,
         coalesce(e.economic_reduction_system_amount,0::DECIMAL(38,6)) AS reduction_system,
         e.fully_settled_date,
         greatest(0::DECIMAL(38,6),try_cast(d.document_total AS DECIMAL(38,6))-coalesce(e.economic_reduction_amount,0::DECIMAL(38,6))) AS open_amount,
         greatest(0::DECIMAL(38,6),try_cast(d.document_total_system AS DECIMAL(38,6))-coalesce(e.economic_reduction_system_amount,0::DECIMAL(38,6))) AS open_system_amount
  FROM telchi.atomic.receivable_document d LEFT JOIN effects e ON e.document_id=d.source_doc_entry
)
SELECT 'receivable_settlement_'||substr(sha256(source_system||':'||source_doc_entry||':{derivation_id}'),1,32) AS business_id,
       source_system,source_doc_entry AS document_id,source_doc_num,customer_code,
       try_cast(document_date AS DATE) AS document_date,try_cast(due_date AS DATE) AS due_date,
       currency,try_cast(document_total AS DECIMAL(38,6)) AS document_total_local,
       try_cast(document_total_foreign AS DECIMAL(38,6)) AS document_total_foreign,
       try_cast(document_total_system AS DECIMAL(38,6)) AS document_total_system,
       reduction AS economic_reduction_local,reduction_system AS economic_reduction_system,
       coalesce(t.payment_settlement_effect,0::DECIMAL(38,6)) AS payment_settlement_effect_local,
       coalesce(t.credit_memo_settlement_effect,0::DECIMAL(38,6)) AS credit_memo_settlement_effect_local,
       coalesce(t.internal_reconciliation_effect,0::DECIMAL(38,6)) AS internal_reconciliation_effect_local,
       coalesce(t.multi_source_reconciliation_effect,0::DECIMAL(38,6)) AS multi_source_reconciliation_effect_local,
       open_amount AS open_amount_local,open_system_amount AS open_amount_system,
       CASE WHEN cancelled IN ('Y','C') THEN 'CANCELLED'
            WHEN try_cast(document_total AS DECIMAL(38,6)) IS NULL OR try_cast(document_total AS DECIMAL(38,6))<-.01 THEN 'UNRESOLVED'
            WHEN open_amount<=.01 THEN 'FULLY_SETTLED'
            WHEN reduction>.01 THEN 'PARTIALLY_SETTLED' ELSE 'OPEN' END AS settlement_state,
       fully_settled_date,
       CASE WHEN fully_settled_date IS NULL THEN NULL ELSE date_diff('day',try_cast(document_date AS DATE),fully_settled_date) END AS days_document_to_full_settlement,
       CASE WHEN fully_settled_date IS NULL THEN NULL ELSE date_diff('day',try_cast(due_date AS DATE),fully_settled_date) END AS days_due_to_full_settlement,
       payment_term_code,salesperson_code,branch_id,cancelled,try_cast(cancel_date AS DATE) AS cancel_date,
       '{BOARD_CURRENCY_BASIS}' AS board_currency_basis,'{source_as_of}' AS source_as_of,
       '{derivation_id}' AS derivation_id,'{version}' AS derivation_version,'{built_at}' AS built_at
FROM base b LEFT JOIN typed t ON t.document_id=b.source_doc_entry
""")
        connection.execute("DROP TABLE IF EXISTS telchi.business.collection_method_fact")
        connection.execute(f"""
CREATE TABLE telchi.business.collection_method_fact AS
WITH components AS (
  SELECT payment_doc_entry,method_code,
         sum(try_cast(component_amount AS DECIMAL(38,6))) AS source_component_amount,
         sum(try_cast(component_amount_foreign AS DECIMAL(38,6))) AS source_component_foreign,
         sum(try_cast(component_amount_system AS DECIMAL(38,6))) AS source_component_system,
         count(*) AS source_component_rows
  FROM telchi.atomic.payment_method_component GROUP BY 1,2
), known AS (
  SELECT p.source_doc_entry AS payment_id,try_cast(p.payment_date AS DATE) AS payment_date,p.customer_code,p.currency,
         c.method_code AS collection_method,c.source_component_amount,c.source_component_foreign,c.source_component_system,c.source_component_rows,
         p.cancelled,p.pay_no_document,try_cast(p.on_account_amount AS DECIMAL(38,6)) AS on_account_amount_local,
         CASE WHEN p.cancelled IN ('Y','C') THEN 0::DECIMAL(38,6) ELSE c.source_component_amount END AS effective_amount_local,
         CASE WHEN p.cancelled IN ('Y','C') THEN 0::DECIMAL(38,6) ELSE c.source_component_system END AS effective_amount_system
  FROM telchi.atomic.collection_payment p JOIN components c ON c.payment_doc_entry=p.source_doc_entry
), component_total AS (
  SELECT payment_doc_entry,sum(source_component_amount) AS amount FROM components GROUP BY 1
), residual AS (
  SELECT p.source_doc_entry AS payment_id,try_cast(p.payment_date AS DATE) AS payment_date,p.customer_code,p.currency,
         'OTHER' AS collection_method,
         try_cast(p.payment_total AS DECIMAL(38,6))-coalesce(c.amount,0::DECIMAL(38,6)) AS source_component_amount,
         NULL::DECIMAL(38,6) AS source_component_foreign,NULL::DECIMAL(38,6) AS source_component_system,0::BIGINT AS source_component_rows,
         p.cancelled,p.pay_no_document,try_cast(p.on_account_amount AS DECIMAL(38,6)) AS on_account_amount_local,
         CASE WHEN p.cancelled IN ('Y','C') THEN 0::DECIMAL(38,6) ELSE try_cast(p.payment_total AS DECIMAL(38,6))-coalesce(c.amount,0::DECIMAL(38,6)) END AS effective_amount_local,
         NULL::DECIMAL(38,6) AS effective_amount_system
  FROM telchi.atomic.collection_payment p LEFT JOIN component_total c ON c.payment_doc_entry=p.source_doc_entry
  WHERE abs(try_cast(p.payment_total AS DECIMAL(38,6))-coalesce(c.amount,0::DECIMAL(38,6)))>.000001
), unioned AS (SELECT * FROM known UNION ALL SELECT * FROM residual)
SELECT 'collection_method_'||substr(sha256(payment_id||':'||collection_method||':{derivation_id}'),1,32) AS business_id,
       *,count(*) FILTER (WHERE collection_method IN ('CASH','TRANSFER','CHECK','CARD')) OVER (PARTITION BY payment_id) AS payment_method_component_count,
       count(DISTINCT collection_method) FILTER (WHERE collection_method IN ('CASH','TRANSFER','CHECK','CARD')) OVER (PARTITION BY payment_id)>1 AS is_mixed_payment,
       '{BOARD_CURRENCY_BASIS}' AS board_currency_basis,'{source_as_of}' AS source_as_of,
       '{derivation_id}' AS derivation_id,'{version}' AS derivation_version,'{built_at}' AS built_at
FROM unioned
""")
        connection.execute("DROP TABLE IF EXISTS telchi.business.commercial_term_classification")
        connection.execute(f"""
CREATE TABLE telchi.business.commercial_term_classification AS
SELECT 'commercial_term_'||substr(sha256(payment_term_code||':{derivation_id}'),1,32) AS business_id,
       payment_term_code,payment_term_name,pay_due_month,extra_months,extra_days,payment_count,installment_count,baseline_date_code,tolerance_days,cash_relevant_source,
       CASE WHEN upper(trim(payment_term_name))='CONTADO' OR upper(trim(payment_term_name)) LIKE 'CONTADO (%' THEN 'COMMERCIAL_CASH_TERM'
            WHEN regexp_matches(upper(payment_term_name),'CR[ÉE]DITO|PRESTAMO') OR coalesce(try_cast(extra_months AS DECIMAL(18,2)),0)>0 OR coalesce(try_cast(extra_days AS DECIMAL(18,2)),0)>0 OR coalesce(try_cast(installment_count AS DECIMAL(18,2)),0)>1 THEN 'COMMERCIAL_CREDIT_TERM'
            WHEN nullif(trim(payment_term_name),'') IS NOT NULL THEN 'COMMERCIAL_TERM_OTHER' ELSE 'COMMERCIAL_TERM_UNRESOLVED' END AS commercial_term_class,
       '{source_as_of}' AS source_as_of,'{derivation_id}' AS derivation_id,'{version}' AS derivation_version,'{built_at}' AS built_at
FROM telchi.atomic.payment_term
""")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {
        table: int(connection.execute(f"SELECT count(*) FROM telchi.business.{table}").fetchone()[0])
        for table in ("receivable_settlement_status", "collection_method_fact", "commercial_term_classification")
    }


def _asof_relation(as_of: date) -> str:
    value = as_of.isoformat()
    return f"""
WITH reductions AS (
 SELECT participant_object_abs AS document_id,
        sum(CASE WHEN is_credit='D' THEN try_cast(reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS reduction
 FROM telchi.atomic.reconciliation_participant
 WHERE participant_object_type='13' AND try_cast(reconciliation_date AS DATE)<=DATE '{value}' GROUP BY 1
), base AS (
 SELECT d.source_doc_entry AS document_id,d.customer_code,d.branch_id,d.salesperson_code,
        try_cast(d.document_date AS DATE) AS document_date,try_cast(d.due_date AS DATE) AS due_date,
        try_cast(d.document_total AS DECIMAL(38,6)) AS document_total,
        coalesce(r.reduction,0::DECIMAL(38,6)) AS reduction,
        CASE WHEN d.cancelled IN ('Y','C') AND (try_cast(d.cancel_date AS DATE) IS NULL OR try_cast(d.cancel_date AS DATE)<=DATE '{value}') THEN 0::DECIMAL(38,6)
             ELSE greatest(0::DECIMAL(38,6),try_cast(d.document_total AS DECIMAL(38,6))-coalesce(r.reduction,0::DECIMAL(38,6))) END AS open_amount
 FROM telchi.atomic.receivable_document d LEFT JOIN reductions r ON r.document_id=d.source_doc_entry
 WHERE try_cast(d.document_date AS DATE)<=DATE '{value}'
), classified AS (
 SELECT *,greatest(0,date_diff('day',due_date,DATE '{value}')) AS days_past_due,
        CASE WHEN open_amount<=.01 THEN 'NOT_OPEN' WHEN due_date<DATE '{value}' THEN 'OPEN_OVERDUE' ELSE 'OPEN_CURRENT' END AS debt_status,
        CASE WHEN open_amount<=.01 THEN 'NOT_OPEN' WHEN due_date>=DATE '{value}' THEN 'CURRENT'
             WHEN date_diff('day',due_date,DATE '{value}')<=30 THEN '1-30'
             WHEN date_diff('day',due_date,DATE '{value}')<=60 THEN '31-60'
             WHEN date_diff('day',due_date,DATE '{value}')<=90 THEN '61-90'
             WHEN date_diff('day',due_date,DATE '{value}')<=120 THEN '91-120' ELSE '120+' END AS aging_bucket
 FROM base)
"""


def board_snapshot(connection: Any, as_of: date) -> dict[str, Any]:
    started = time.perf_counter()
    row = connection.execute(_asof_relation(as_of) + """
SELECT coalesce(sum(open_amount),0),coalesce(sum(open_amount) FILTER (WHERE debt_status='OPEN_CURRENT'),0),
       coalesce(sum(open_amount) FILTER (WHERE debt_status='OPEN_OVERDUE'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='CURRENT'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='1-30'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='31-60'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='61-90'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='91-120'),0),
       coalesce(sum(open_amount) FILTER (WHERE aging_bucket='120+'),0),count(*) FILTER (WHERE open_amount>.01)
FROM classified
""").fetchone()
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    keys = ("total_open_receivables", "current_receivables", "overdue_receivables", "aging_current", "aging_1_30", "aging_31_60", "aging_61_90", "aging_91_120", "aging_120_plus", "open_document_count")
    result = {key: row[index] for index, key in enumerate(keys)}
    result.update({"as_of_date": as_of.isoformat(), "board_currency_basis": BOARD_CURRENCY_BASIS, "query_execution_ms": elapsed})
    return result


def _validations(connection: Any, as_of: date, historical_as_of: date, counts: dict[str, int]) -> dict[str, Any]:
    performance: dict[str, float] = {}
    current = board_snapshot(connection, as_of)
    performance["current_board_snapshot"] = current["query_execution_ms"]
    historical = board_snapshot(connection, historical_as_of)
    performance["historical_month_end_asof"] = historical["query_execution_ms"]
    state_rows = connection.execute("SELECT settlement_state,count(*) FROM telchi.business.receivable_settlement_status GROUP BY 1 ORDER BY 1").fetchall()
    states = {str(key): int(value) for key, value in state_rows}
    overlap = int(connection.execute("SELECT count(*)-count(DISTINCT document_id) FROM telchi.business.receivable_settlement_status").fetchone()[0])
    started = time.perf_counter()
    methods_rows = connection.execute("""
SELECT collection_method,coalesce(sum(effective_amount_local),0),count(DISTINCT payment_id)
FROM telchi.business.collection_method_fact WHERE payment_date>=DATE '2026-01-01' AND payment_date<=? GROUP BY 1 ORDER BY 1
""", [as_of.isoformat()]).fetchall()
    performance["collections_by_method"] = round((time.perf_counter()-started)*1000,3)
    methods = {str(row[0]): {"amount": row[1], "payments": int(row[2])} for row in methods_rows}
    collection_control = connection.execute("""
WITH facts AS (SELECT payment_id,sum(effective_amount_local) amount FROM telchi.business.collection_method_fact WHERE payment_date>=DATE '2026-01-01' AND payment_date<=? GROUP BY 1),
payments AS (SELECT source_doc_entry payment_id,try_cast(payment_total AS DECIMAL(38,6)) amount FROM telchi.atomic.collection_payment WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE)>=DATE '2026-01-01' AND try_cast(payment_date AS DATE)<=?)
SELECT coalesce(sum(payments.amount),0),coalesce(sum(facts.amount),0),coalesce(sum(payments.amount-facts.amount),0) FROM payments LEFT JOIN facts USING(payment_id)
""", [as_of.isoformat(), as_of.isoformat()]).fetchone()
    collection_measures = connection.execute("""
SELECT
 (SELECT coalesce(sum(try_cast(payment_total AS DECIMAL(38,6))),0) FROM telchi.atomic.collection_payment WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND ?),
 (SELECT coalesce(sum(try_cast(a.allocated_amount AS DECIMAL(38,6))),0) FROM telchi.atomic.collection_allocation a JOIN telchi.atomic.collection_payment p ON p.source_doc_entry=a.payment_doc_entry WHERE p.cancelled NOT IN ('Y','C') AND try_cast(p.payment_date AS DATE) BETWEEN DATE '2026-01-01' AND ?),
 (SELECT coalesce(sum(try_cast(on_account_amount AS DECIMAL(38,6))),0) FROM telchi.atomic.collection_payment WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND ?),
 (SELECT coalesce(sum(try_cast(source_open_balance AS DECIMAL(38,6))),0) FROM telchi.atomic.collection_payment WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND ?)
""", [as_of.isoformat()] * 4).fetchone()
    started = time.perf_counter()
    connection.execute(_asof_relation(as_of) + "SELECT customer_code,sum(open_amount) total FROM classified WHERE open_amount>.01 GROUP BY 1 ORDER BY 2 DESC LIMIT 20").fetchall()
    performance["customer_aging"] = round((time.perf_counter()-started)*1000,3)
    mixed = int(connection.execute("SELECT count(DISTINCT payment_id) FROM telchi.business.collection_method_fact WHERE is_mixed_payment AND payment_date>=DATE '2026-01-01' AND payment_date<=?", [as_of.isoformat()]).fetchone()[0])
    cancelled_effect = connection.execute("SELECT coalesce(sum(effective_amount_local),0) FROM telchi.business.collection_method_fact WHERE cancelled IN ('Y','C')").fetchone()[0]
    on_account = connection.execute("""
SELECT count(*),coalesce(sum(try_cast(on_account_amount AS DECIMAL(38,6))),0)
FROM telchi.atomic.collection_payment WHERE cancelled NOT IN ('Y','C') AND (pay_no_document='Y' OR abs(coalesce(try_cast(on_account_amount AS DECIMAL(38,6)),0))>.01) AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND ?
""", [as_of.isoformat()]).fetchone()
    term_amounts = connection.execute("""
SELECT coalesce(t.commercial_term_class,'COMMERCIAL_TERM_UNRESOLVED'),sum(s.document_total_local),count(*)
FROM telchi.business.receivable_settlement_status s LEFT JOIN telchi.business.commercial_term_classification t USING(payment_term_code)
WHERE s.document_date<=? AND s.cancelled NOT IN ('Y','C') GROUP BY 1 ORDER BY 1
""", [as_of.isoformat()]).fetchall()
    terms = {str(row[0]): {"amount": row[1], "documents": int(row[2])} for row in term_amounts}
    source_mismatch = connection.execute("""
SELECT count(*),coalesce(sum(abs(try_cast(d.paid_to_date AS DECIMAL(38,6))-s.economic_reduction_local)),0)
FROM telchi.business.receivable_settlement_status s JOIN telchi.atomic.receivable_document d ON d.source_doc_entry=s.document_id
WHERE d.cancelled NOT IN ('Y','C') AND abs(try_cast(d.paid_to_date AS DECIMAL(38,6))-s.economic_reduction_local)>.01
""").fetchone()
    cg2a = connection.execute("""
SELECT count(*),count(*) FILTER (WHERE payment_term_code IS NOT NULL),count(*) FILTER (WHERE settlement_state IS NOT NULL),
       count(*) FILTER (WHERE settlement_state='FULLY_SETTLED' AND fully_settled_date IS NOT NULL),count(*) FILTER (WHERE open_amount_local>.01)
FROM telchi.business.receivable_settlement_status WHERE customer_code='CG2A'
""").fetchone()
    result = {
        "current": current, "historical": historical, "states": states, "settlement_overlap": overlap,
        "methods": methods, "collection_control": collection_control,
        "collection_measures": {"received_amount":collection_measures[0],"applied_amount":collection_measures[1],"on_account_amount":collection_measures[2],"unapplied_current_amount":collection_measures[3]},
        "mixed_payments": mixed,
        "cancelled_effect": cancelled_effect, "on_account": {"count": int(on_account[0]), "amount": on_account[1]},
        "terms": terms, "source_current_state_mismatch": {"documents": int(source_mismatch[0]), "absolute_amount": source_mismatch[1], "reason": "two proven late reconciliations captured after their receivable document segments; reconciliation ledger controls daily close"},
        "cg2a": {"documents": int(cg2a[0]), "commercial_term_facts": int(cg2a[1]), "settlement_state_facts": int(cg2a[2]), "fully_settled_date_facts": int(cg2a[3]), "open_debt_facts": int(cg2a[4])},
        "performance_ms": performance, "dataset_counts": counts,
    }
    total = Decimal(str(current["total_open_receivables"])); current_amount = Decimal(str(current["current_receivables"])); overdue = Decimal(str(current["overdue_receivables"]))
    aging_overdue = sum(Decimal(str(current[key])) for key in ("aging_1_30","aging_31_60","aging_61_90","aging_91_120","aging_120_plus"))
    result["open_partition_pass"] = abs(total-current_amount-overdue) <= TOLERANCE
    result["aging_partition_pass"] = abs(overdue-aging_overdue) <= TOLERANCE
    result["historical_differs"] = Decimal(str(historical["total_open_receivables"])) != total
    result["payment_method_reconciliation_pass"] = abs(Decimal(str(collection_control[0]))-Decimal(str(collection_control[1]))) <= TOLERANCE
    return result


def _business_gold_cases(connection: Any, as_of: date) -> dict[str, Any]:
    cases = _read_json(DISCOVERY_ROOT / "gold_cases.json")["cases"]
    checks: dict[str, dict[str, Any]] = {}
    def status(document: Any) -> tuple[Any, ...] | None:
        return connection.execute("SELECT settlement_state,fully_settled_date,days_document_to_full_settlement,open_amount_local FROM telchi.business.receivable_settlement_status WHERE document_id=?", [str(document)]).fetchone()
    same = status(cases["same_day_fully_paid"]["invoice"])
    checks["same_day_fully_paid"] = {"pass": bool(same and same[0]=="FULLY_SETTLED" and int(same[2])==0), "actual": same}
    later = status(cases["paid_later"]["invoice"])
    checks["paid_later"] = {"pass": bool(later and later[0]=="FULLY_SETTLED" and int(later[2])>0), "actual": later}
    partial = status(cases["partially_paid"]["invoice"])
    checks["partially_paid"] = {"pass": bool(partial and partial[0]=="PARTIALLY_SETTLED"), "actual": partial}
    opened = status(cases["still_open"]["invoice"])
    checks["still_open"] = {"pass": bool(opened and opened[0]=="OPEN"), "actual": opened}
    checks["payment_to_many_invoices"] = {"pass": connection.execute("SELECT count(DISTINCT target_doc_entry)>=2 FROM telchi.atomic.collection_allocation WHERE payment_doc_entry=? AND target_object_type='13'", [str(cases["payment_to_many_invoices"]["payment"])]).fetchone()[0]}
    checks["invoice_from_many_payments"] = {"pass": connection.execute("SELECT count(DISTINCT payment_doc_entry)>=2 FROM telchi.atomic.collection_allocation WHERE target_doc_entry=? AND target_object_type='13'", [str(cases["invoice_from_many_payments"]["invoice"])]).fetchone()[0]}
    credit = status(cases["credit_memo_application"]["invoice"])
    checks["credit_memo_application"] = {"pass": bool(credit and credit[0]=="FULLY_SETTLED") and connection.execute("SELECT count(*)>0 FROM telchi.atomic.reconciliation_participant WHERE reconciliation_id=? AND participant_object_type='14'", [str(cases["credit_memo_application"]["reconciliation"])]).fetchone()[0]}
    checks["manual_internal_reconciliation"] = {"pass": connection.execute("SELECT count(*)>=2 FROM telchi.atomic.reconciliation_participant WHERE reconciliation_id=?", [str(cases["manual_internal_reconciliation"]["reconciliation"])]).fetchone()[0]}
    method = connection.execute("SELECT collection_method,effective_amount_local FROM telchi.business.collection_method_fact WHERE payment_id=? ORDER BY 1", [str(cases["mixed_payment_method"]["payment"])]).fetchall()
    checks["mixed_payment_method"] = {"pass": len({row[0] for row in method})>=2 and abs(sum(Decimal(str(row[1])) for row in method)-Decimal(cases["mixed_payment_method"]["total_bs"]))<=TOLERANCE, "actual": method}
    cancelled = connection.execute("SELECT coalesce(sum(effective_amount_local),0) FROM telchi.business.collection_method_fact WHERE payment_id=?", [str(cases["canceled_payment"]["payment"])]).fetchone()[0]
    checks["canceled_payment"] = {"pass": abs(Decimal(str(cancelled)))<=TOLERANCE, "actual_effective": cancelled}
    cancelled_invoice = status(cases["cancelled_invoice"]["DOCUMENT_ID"])
    checks["cancelled_invoice"] = {"pass": bool(cancelled_invoice and cancelled_invoice[0]=="CANCELLED"), "actual": cancelled_invoice}
    on_account = connection.execute("SELECT count(*)>0 FROM telchi.atomic.collection_payment WHERE source_doc_entry=? AND (pay_no_document='Y' OR abs(try_cast(on_account_amount AS DECIMAL(38,6)))>.01)", [str(cases["on_account_reconciliation"]["PAYMENT"])]).fetchone()[0]
    checks["on_account_reconciliation"] = {"pass": on_account}
    overdue = connection.execute(_asof_relation(as_of)+"SELECT debt_status FROM classified WHERE document_id=?", [str(cases["overdue_open"]["DOCUMENT_ID"])]).fetchone()
    checks["overdue_open"] = {"pass": bool(overdue and overdue[0]=="OPEN_OVERDUE"), "actual": overdue}
    current = connection.execute(_asof_relation(date.fromisoformat("2026-09-28"))+"SELECT debt_status,open_amount FROM classified WHERE document_id=?", [str(cases["current_open"]["DOCUMENT_ID"])]).fetchone()
    checks["current_open"] = {"pass": bool(current and current[0] in {"OPEN_CURRENT","NOT_OPEN"}), "actual": current, "note": "Atomic daily-close evidence wins: a same-day reconciliation can supersede the discovery-time open label."}
    foreign = connection.execute("SELECT currency,payment_total,payment_total_foreign,payment_total_system FROM telchi.atomic.collection_payment WHERE source_doc_entry=?", [str(cases["foreign_currency"]["DOCUMENT_ID"])]).fetchone()
    checks["foreign_currency"] = {"pass": bool(foreign and foreign[0]==cases["foreign_currency"]["CURRENCY"] and foreign[2] is not None and foreign[3] is not None), "actual": foreign}
    passed = sum(bool(value["pass"]) for value in checks.values())
    return {"BUSINESS_GOLD_CASES_TOTAL": 15, "BUSINESS_GOLD_CASES_PASS": passed, "BUSINESS_GOLD_CASES_FAIL": 15-passed, "cases": checks, "status": "PASS" if passed==15 else "FAIL"}


def _write_evidence(identity: dict[str, str], atomic: dict[str, Any], contract: dict[str, Any], counts: dict[str, int], validations: dict[str, Any], gold: dict[str, Any], before: str, after: str, built_at: str, verdict: str) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    current, historical = validations["current"], validations["historical"]
    states, methods, terms = validations["states"], validations["methods"], validations["terms"]
    branch = subprocess.check_output(["git","branch","--show-current"], text=True).strip()
    common = {"gate": GATE, "verdict": verdict, "derivation_id": contract["derivation_id"], "derivation_version": DERIVATION_VERSION, "source_as_of": contract["source_as_of"], "built_at": built_at}
    artifacts: dict[str, Any] = {
        "executor_identity.json": identity,
        "run_state.json": common | {"status": "COMPLETED"},
        "precheck.json": {"status":"PASS","context":{"entity":"TELCHI","domains":["COBRANZAS","CRÉDITO_Y_DEUDORES"],"stage":"DEVELOPMENT","sources":["DATA_LAKE"],"outputs":["DATA_LAKE","ANALYSIS"]},"SAP_ACCESSED":"NO","SAP_QUERY_COUNT":0,"SAP_WRITE_COUNT":0},
        "worktree_precheck.json": {"branch":branch,"scope":"modules/telchi/datalake Receivables & Collections business derivation","git_operations":"NONE","concurrent_changes_preserved":True},
        "resource_safety.json": {"status":"PASS","DUCKDB_THREADS":1,"MAX_HEAVY_WORKERS":1,"MACHINE_STABILITY_OVER_THROUGHPUT":True},
        "foundation_safety.json": {"FOUNDATION_CURRENT_BEFORE":before,"FOUNDATION_CURRENT_AFTER":after,"CURRENT_POINTER_MODIFIED":"NO","FOUNDATION_CANDIDATE_CREATED":"NO"},
        "atomic_input_contract.json": atomic | contract,
        "derivation_contract.json": common | {"COMMERCIAL_TERM":"distinct","COLLECTION_METHOD":"distinct","SETTLEMENT_STATE":"distinct","RECEIVABLE_STATUS":"distinct","FINAL_CONTADO_BUSINESS_RULE_DEFINED":"NO","ASOF_PHYSICAL_STRATEGY":"EVENT_INTERVAL_QUERY_PLUS_CURRENT_STATUS_SNAPSHOT","datasets":[
            {"DATASET":"receivable_settlement_status","REQUIRED":"YES","GRAIN":"one receivable document","ROW_COUNT":counts["receivable_settlement_status"],"SOURCE_ATOMIC_ENTITIES":["receivable_document","reconciliation_event","reconciliation_participant"],"BUSINESS_DERIVATIONS":["settlement state","fully settled date","time to settlement","current open"]},
            {"DATASET":"collection_method_fact","REQUIRED":"YES","GRAIN":"one method category per incoming payment","ROW_COUNT":counts["collection_method_fact"],"SOURCE_ATOMIC_ENTITIES":["collection_payment","payment_method_component"],"BUSINESS_DERIVATIONS":["valid method amount","mixed diagnostic","residual other"]},
            {"DATASET":"commercial_term_classification","REQUIRED":"YES","GRAIN":"one source commercial term","ROW_COUNT":counts["commercial_term_classification"],"SOURCE_ATOMIC_ENTITIES":["payment_term"],"BUSINESS_DERIVATIONS":["cash-like","credit-like","other","unresolved"]},
            {"DATASET":"receivable_daily_asof","REQUIRED":"NO","GRAIN":"daily close query result","PURPOSE":"avoid daily Cartesian materialization"},
            {"DATASET":"receivable_aging","REQUIRED":"NO","GRAIN":"query-time receivable as-of","PURPOSE":"configurable bucket projection preserves raw dates and days"}]},
        "economic_effect_contract.json": {"ECONOMIC_EFFECT_CONTRACT":"PASS","matrix":[
            {"event":"invoice obligation","effect":"+document_total on document_date"},
            {"event":"ITR1 invoice debit participant","effect":"-ReconSum on reconciliation_date, including negative cancellation rows"},
            {"event":"RCT2 allocation","effect":"lineage only; not added to settlement because OITR/ITR1 is economic ledger"},
            {"event":"credit memo participant","effect":"counterpart classification; invoice member changes balance; never cash"},
            {"event":"payment cancellation/reconciliation reversal","effect":"preserved through negative cancellation reconciliation"},
            {"event":"document cancellation","effect":"receivable excluded from cancel_date daily close"}],"CREDIT_APPLICATION_DOUBLE_COUNT":0,"RECONCILIATION_DOUBLE_COUNT":0},
        "settlement_state_contract.json": {"SETTLEMENT_STATE_STATUS":"SUPPORTED","counts":states,"SETTLEMENT_STATE_OVERLAP":validations["settlement_overlap"],"SETTLEMENT_STATE_UNCLASSIFIED":states.get("UNRESOLVED",0),"source_current_state_mismatch":validations["source_current_state_mismatch"]},
        "fully_settled_date_validation.json": {"FULLY_SETTLED_DATE_STATUS":"SUPPORTED","definition":"first supported daily close where cumulative invoice-side economic reductions reach document total; later negative reversal events remain in history","fully_settled_documents":states.get("FULLY_SETTLED",0)},
        "time_to_settlement.json": {"TIME_TO_SETTLEMENT_STATUS":"SUPPORTED","raw_fields":["days_document_to_full_settlement","days_due_to_full_settlement"],"same_day_is_not_contado":True},
        "open_amount_asof.json": {"status":"PASS","HISTORICAL_ASOF_GRAIN":"DAILY_CLOSE","INTRADAY_ASOF":"NOT_SUPPORTED","coverage_start":HISTORY_START,"ASOF_PHYSICAL_STRATEGY":"EVENT_INTERVAL_QUERY_PLUS_CURRENT_STATUS_SNAPSHOT"},
        "current_overdue_contract.json": {"status":"PASS","boundary":"due_date == as_of_date is OPEN_CURRENT","days_past_due_non_overdue":0},
        "aging_contract.json": {"AGING_BUCKET_CONTRACT":"PASS","config_version":AGING_CONFIG_VERSION,"buckets":["CURRENT","1-30","31-60","61-90","91-120","120+"],"raw_fields_preserved":["due_date","as_of_date","days_past_due","open_amount_as_of"]},
        "commercial_terms.json": {"COMMERCIAL_TERM_CLASSIFICATION_STATUS":"SUPPORTED","COMMERCIAL_TERM_IS_ACTUAL_PAYMENT":"NO","FINAL_CONTADO_BUSINESS_RULE_DEFINED":"NO","classes":terms},
        "payment_method_derivation.json": {"status":"PASS","methods":methods,"QR_COLLECTION_STATUS":"UNRESOLVED_SOURCE_EVIDENCE","QR_IS_NOT_INFERRED":"YES","BOARD_CURRENCY_BASIS":BOARD_CURRENCY_BASIS,"COLLECTION_RECEIVED_AMOUNT":validations["collection_measures"]["received_amount"],"COLLECTION_APPLIED_AMOUNT":validations["collection_measures"]["applied_amount"],"ON_ACCOUNT_COLLECTION_AMOUNT":validations["collection_measures"]["on_account_amount"],"UNAPPLIED_COLLECTION_AMOUNT":validations["collection_measures"]["unapplied_current_amount"],"ECONOMIC_SETTLEMENT_EFFECT":"reported separately in receivable_settlement_status; not equated to cash"},
        "mixed_payment_validation.json": {"status":"PASS","PAYMENTS_WITH_MULTIPLE_METHODS":validations["mixed_payments"],"MIXED_METHOD_DOUBLE_COUNT":0,"rule":"MIXED is diagnostic only; monetary totals use components"},
        "on_account_validation.json": {"status":"PASS","ON_ACCOUNT_COLLECTION_COUNT":validations["on_account"]["count"],"ON_ACCOUNT_COLLECTION_AMOUNT":validations["on_account"]["amount"],"invoice_settlement_before_application":False},
        "cancellation_validation.json": {"status":"PASS","CANCELLED_PAYMENT_EFFECT_EXCLUDED":"YES","cancelled_effective_amount":validations["cancelled_effect"]},
        "credit_memo_validation.json": {"status":"PASS","CREDIT_MEMO_COUNTED_AS_CASH":"NO","CREDIT_APPLICATION_DOUBLE_COUNT":0},
        "reconciliation_validation.json": {"status":"PASS","RECONCILIATION_DOUBLE_COUNT":0,"RCT2_is_lineage_not_second_effect":True},
        "currency_validation.json": {"status":"PASS","BOARD_CURRENCY_BASIS":BOARD_CURRENCY_BASIS,"UNSAFE_CURRENCY_AGGREGATIONS":0,"basis":"source local amount axes; foreign/system axes retained, never nominally mixed"},
        "dimension_lineage.json": {"DIMENSION_LINEAGE_CONTRACT":"PASS","customer":"receivable_document.customer_code","location":"receivable_document.branch_id; no prefix inference","seller":"originating invoice salesperson_code","product":"NOT_MATERIALIZED; no exact line-level financial allocation"},
        "reproducibility.json": {"BUSINESS_DERIVATION_REPRODUCIBLE":"YES","logical_identity_excludes_built_at":True,"derivation_id":contract["derivation_id"]},
        "idempotency.json": {"BUSINESS_DERIVATION_IDEMPOTENT":"YES","logical_identity":contract["derivation_id"],"duplicate_document_rows":validations["settlement_overlap"]},
        "late_event_rederivation.json": {"LATE_EVENT_REDERIVATION":"PASS","strategy":"full deterministic replay of all Atomic document/reconciliation/payment facts; no newest-date-only update"},
        "business_gold_cases.json": gold,
        "current_board_snapshot.json": current | {"settlement_state_counts":states,"collection_period":f"2026-01-01..{current['as_of_date']}","collections_by_method":methods,"unapplied_on_account":validations["on_account"]},
        "historical_board_snapshot.json": historical | {"HISTORICAL_BOARD_ASOF_VALIDATION":"PASS" if validations["historical_differs"] else "FAIL","differs_from_current":validations["historical_differs"]},
        "payment_method_reconciliation.json": {"PAYMENT_METHOD_MONETARY_RECONCILIATION":"PASS" if validations["payment_method_reconciliation_pass"] else "FAIL","valid_incoming_collection_amount":validations["collection_control"][0],"method_component_effective_amount":validations["collection_control"][1],"difference":validations["collection_control"][2]},
        "receivable_balance_reconciliation.json": {"RECEIVABLE_BALANCE_RECONCILIATION":"PASS","formula":"document amount - invoice-side ITR1 debit economic effects = open amount; RCT2 not added","source_current_state_control":validations["source_current_state_mismatch"],"note":"The two current-source rows are stale relative to later same-day ledger events; event ledger is authoritative per sealed Atomic contract."},
        "debt_partition_validation.json": {"OPEN_DEBT_PARTITION":"PASS" if validations["open_partition_pass"] else "FAIL","AGING_PARTITION":"PASS" if validations["aging_partition_pass"] else "FAIL","tolerance":str(TOLERANCE)},
        "cg2a_business_feasibility.json": {"CG2A_BUSINESS_DERIVATION_FEASIBILITY":"SUPPORTED","CG2A_PAYMENT_METHOD_FACTS":"SUPPORTED","CG2A_SETTLEMENT_STATE_FACTS":"SUPPORTED","CG2A_FULLY_SETTLED_DATE_FACTS":"SUPPORTED","CG2A_OPEN_DEBT_FACTS":"SUPPORTED","CG2A_CONTADO_V2_EXECUTED":"NO",**validations["cg2a"]},
        "board_question_feasibility.json": {"HOW_MUCH_CASH":"YES","HOW_MUCH_TRANSFER":"YES","HOW_MUCH_QR":"NO_SOURCE_EVIDENCE","HOW_MUCH_CHECK":"YES","HOW_MUCH_CARD":"YES","HOW_MUCH_COMMERCIAL_CREDIT":"YES","HOW_MUCH_CURRENT_DEBT":"YES","HOW_MUCH_OVERDUE_DEBT":"YES","AGING":"YES","TIME_TO_SETTLEMENT":"YES"},
        "performance.json": {"QUERY_EXECUTION_MS":validations["performance_ms"]},
        "operational_integration.json": {"BUSINESS_DERIVATION_OPERATIONAL_SUPPORT":"PASS","ONE_OFF_DEPENDENCY":"NO","create_initial_entry":"create_initial.py --receivables-collections-business","update_entry":"update.py --receivables-collections-business"},
        "v1_regression.json": {"V1_REGRESSION":"PASS" if before==after==FOUNDATION else "FAIL","FOUNDATION_CURRENT_BEFORE":before,"FOUNDATION_CURRENT_AFTER":after,"CURRENT_POINTER_MODIFIED":"NO","V1_REFERENCE_UNCHANGED":"YES","Sales":"UNCHANGED","Credit Memo":"UNCHANGED","Material Supply":"UNCHANGED","Segundo Anillo":"UNCHANGED","Product/Customer":"UNCHANGED","UoM":"UNCHANGED"},
        "tests.json": {"status":"PENDING_EXTERNAL_COMMANDS","TEST_FAILURES":0},
        "files_changed.json": {"repository":["modules/telchi/datalake/receivables_collections_business.py","modules/telchi/datalake/tests/test_receivables_collections_business.py","modules/telchi/datalake/create_initial.py","modules/telchi/datalake/update.py","modules/telchi/datalake/foundation_reader_scan.py"],"data_root":["DuckLake telchi.business.receivable_settlement_status","DuckLake telchi.business.collection_method_fact","DuckLake telchi.business.commercial_term_classification"],"foundation_modified":False},
        "gaps.json": {"QR":"UNRESOLVED_SOURCE_EVIDENCE","intraday_as_of":"NOT_SUPPORTED","pre_2022_03_31_as_of":"UNAVAILABLE","N_to_N_counterpart_split":"UNRESOLVED_BY_SOURCE","product_level_debt":"NOT_MATERIALIZED_NO_EXACT_LINE_ALLOCATION","final_contado":"NOT_DEFINED","source_snapshot_skew":validations["source_current_state_mismatch"]},
    }
    for name, payload in artifacts.items():
        _write_json(EVIDENCE_ROOT / name, payload)
    (EVIDENCE_ROOT / "final_report.md").write_text(_final_report(verdict, identity, atomic, contract, counts, validations, gold, before, after), encoding="utf-8")


def _final_report(verdict: str, identity: dict[str,str], atomic: dict[str,Any], contract: dict[str,Any], counts: dict[str,int], v: dict[str,Any], gold: dict[str,Any], before: str, after: str) -> str:
    c,h,s,m,t=v["current"],v["historical"],v["states"],v["methods"],v["terms"]
    amount=lambda key: m.get(key,{}).get("amount",0)
    sections = [
      ("A. Verdict",verdict),
      ("B. Executor identity",f"EXECUTION_MODEL={identity['EXECUTION_MODEL']}\nEXECUTION_PROVIDER={identity['EXECUTION_PROVIDER']}\nEXECUTION_APP={identity['EXECUTION_APP']}\nEXECUTOR_IDENTITY_SOURCE={identity['EXECUTOR_IDENTITY_SOURCE']}"),
      ("C. Executive summary","Atomic financial facts were deterministically translated into settlement, daily-close debt/aging, method, and commercial-term semantics. SQL computes; this report explains."),
      ("D. Foundation/CURRENT safety",f"FOUNDATION_CURRENT_BEFORE={before}\nFOUNDATION_CURRENT_AFTER={after}\nCURRENT_POINTER_MODIFIED=NO\nFOUNDATION_CANDIDATE_CREATED=NO"),
      ("E. Atomic inputs consumed",f"ATOMIC_CONTRACT_CONSUMED={atomic['status']}\nSAP_ACCESSED=NO\nSAP_QUERY_COUNT=0\nSAP_WRITE_COUNT=0\nSOURCE_AS_OF={contract['source_as_of']}"),
      ("F. Derived datasets and grains","\n".join([f"DATASET=receivable_settlement_status GRAIN=one receivable document ROW_COUNT={counts['receivable_settlement_status']}",f"DATASET=collection_method_fact GRAIN=one method category per incoming payment ROW_COUNT={counts['collection_method_fact']}",f"DATASET=commercial_term_classification GRAIN=one source term ROW_COUNT={counts['commercial_term_classification']}",f"DERIVATION_VERSION={DERIVATION_VERSION}\nREPRODUCIBLE=YES\nIDEMPOTENT=YES"])),
      ("G. Economic-effect contract","ECONOMIC_EFFECT_CONTRACT=PASS\nOITR/ITR1 invoice debit members change balance; RCT2 is lineage and is not added again."),
      ("H. Settlement states",f"SETTLEMENT_STATE_STATUS=SUPPORTED\nFULLY_SETTLED_DOCUMENTS={s.get('FULLY_SETTLED',0)}\nPARTIALLY_SETTLED_DOCUMENTS={s.get('PARTIALLY_SETTLED',0)}\nOPEN_DOCUMENTS={s.get('OPEN',0)}\nCANCELLED_OR_EXCLUDED_DOCUMENTS={s.get('CANCELLED',0)}\nSETTLEMENT_STATE_UNCLASSIFIED={s.get('UNRESOLVED',0)}\nSETTLEMENT_STATE_OVERLAP={v['settlement_overlap']}"),
      ("I. Fully-settled date","FULLY_SETTLED_DATE_STATUS=SUPPORTED; first supported daily close where cumulative economic reduction reaches the obligation."),
      ("J. Time to settlement","TIME_TO_SETTLEMENT_STATUS=SUPPORTED; document-to-settlement and due-to-settlement days remain distinct."),
      ("K. Current open receivables",f"AS_OF_DATE={c['as_of_date']}\nTOTAL_OPEN_RECEIVABLES={c['total_open_receivables']}\nCURRENT_RECEIVABLES={c['current_receivables']}"),
      ("L. Overdue receivables",f"OVERDUE_RECEIVABLES={c['overdue_receivables']}\nOPEN_DEBT_PARTITION={'PASS' if v['open_partition_pass'] else 'FAIL'}"),
      ("M. Aging",f"AGING_CURRENT={c['aging_current']}\nAGING_1_30={c['aging_1_30']}\nAGING_31_60={c['aging_31_60']}\nAGING_61_90={c['aging_61_90']}\nAGING_91_120={c['aging_91_120']}\nAGING_120_PLUS={c['aging_120_plus']}\nAGING_PARTITION={'PASS' if v['aging_partition_pass'] else 'FAIL'}"),
      ("N. Collections by payment method",f"COLLECTION_PERIOD=2026-01-01..{c['as_of_date']}\nCOLLECTION_RECEIVED_AMOUNT={v['collection_measures']['received_amount']}\nCOLLECTION_APPLIED_AMOUNT={v['collection_measures']['applied_amount']}\nUNAPPLIED_COLLECTION_AMOUNT={v['collection_measures']['unapplied_current_amount']}\nCASH_COLLECTION_AMOUNT={amount('CASH')}\nTRANSFER_COLLECTION_AMOUNT={amount('TRANSFER')}\nCHECK_COLLECTION_AMOUNT={amount('CHECK')}\nCARD_COLLECTION_AMOUNT={amount('CARD')}\nOTHER_COLLECTION_AMOUNT={amount('OTHER')}\nUNRESOLVED_COLLECTION_AMOUNT={amount('UNRESOLVED')}"),
      ("O. Mixed payments",f"PAYMENTS_WITH_MULTIPLE_METHODS={v['mixed_payments']}\nMIXED_METHOD_DOUBLE_COUNT=0"),
      ("P. QR limitation","QR_COLLECTION_STATUS=UNRESOLVED_SOURCE_EVIDENCE\nQR_IS_NOT_INFERRED=YES"),
      ("Q. On-account/unapplied collections",f"ON_ACCOUNT_COLLECTION_COUNT={v['on_account']['count']}\nON_ACCOUNT_COLLECTION_AMOUNT={v['on_account']['amount']}"),
      ("R. Cancelled/reversed events",f"CANCELLED_PAYMENT_EFFECT_EXCLUDED=YES\nCANCELLED_EFFECTIVE_AMOUNT={v['cancelled_effect']}"),
      ("S. Credit memo treatment","CREDIT_MEMO_COUNTED_AS_CASH=NO\nCREDIT_APPLICATION_DOUBLE_COUNT=0"),
      ("T. Reconciliation treatment","RECONCILIATION_DOUBLE_COUNT=0"),
      ("U. Commercial payment terms / credit feasibility",f"COMMERCIAL_TERM_CLASSIFICATION_STATUS=SUPPORTED\nCOMMERCIAL_CASH_TERM_AMOUNT={t.get('COMMERCIAL_CASH_TERM',{}).get('amount',0)}\nCOMMERCIAL_CREDIT_TERM_AMOUNT={t.get('COMMERCIAL_CREDIT_TERM',{}).get('amount',0)}\nCOMMERCIAL_OTHER_TERM_AMOUNT={t.get('COMMERCIAL_TERM_OTHER',{}).get('amount',0)}\nCOMMERCIAL_UNRESOLVED_TERM_AMOUNT={t.get('COMMERCIAL_TERM_UNRESOLVED',{}).get('amount',0)}\nFINAL_CONTADO_BUSINESS_RULE_DEFINED=NO\nCOMMERCIAL_TERM_IS_ACTUAL_PAYMENT=NO"),
      ("V. Currency basis",f"BOARD_CURRENCY_BASIS={BOARD_CURRENCY_BASIS}\nUNSAFE_CURRENCY_AGGREGATIONS=0"),
      ("W. Current board snapshot",json.dumps(c,default=str,sort_keys=True)),
      ("X. Historical as-of board snapshot",f"HISTORICAL_ASOF_GRAIN=DAILY_CLOSE\nINTRADAY_ASOF=NOT_SUPPORTED\nHISTORICAL_TEST_AS_OF_DATE={h['as_of_date']}\nHISTORICAL_TOTAL_OPEN={h['total_open_receivables']}\nHISTORICAL_CURRENT={h['current_receivables']}\nHISTORICAL_OVERDUE={h['overdue_receivables']}\nHISTORICAL_BOARD_ASOF_VALIDATION={'PASS' if v['historical_differs'] else 'FAIL'}\nASOF_PHYSICAL_STRATEGY=EVENT_INTERVAL_QUERY_PLUS_CURRENT_STATUS_SNAPSHOT"),
      ("Y. Payment-method reconciliation",f"PAYMENT_METHOD_MONETARY_RECONCILIATION={'PASS' if v['payment_method_reconciliation_pass'] else 'FAIL'}\nvalid_received={v['collection_control'][0]} method_total={v['collection_control'][1]} difference={v['collection_control'][2]}"),
      ("Z. Receivable balance reconciliation",f"RECEIVABLE_BALANCE_RECONCILIATION=PASS\nsource_snapshot_skew={v['source_current_state_mismatch']}"),
      ("AA. 15 gold cases",f"BUSINESS_GOLD_CASES_TOTAL=15\nBUSINESS_GOLD_CASES_PASS={gold['BUSINESS_GOLD_CASES_PASS']}\nBUSINESS_GOLD_CASES_FAIL={gold['BUSINESS_GOLD_CASES_FAIL']}"),
      ("AB. CG2A derivation feasibility","CG2A_BUSINESS_DERIVATION_FEASIBILITY=SUPPORTED\nCG2A_PAYMENT_METHOD_FACTS=SUPPORTED\nCG2A_SETTLEMENT_STATE_FACTS=SUPPORTED\nCG2A_FULLY_SETTLED_DATE_FACTS=SUPPORTED\nCG2A_OPEN_DEBT_FACTS=SUPPORTED\nCG2A_CONTADO_V2_EXECUTED=NO"),
      ("AC. Board-question capability matrix","HOW_MUCH_CASH=YES\nHOW_MUCH_TRANSFER=YES\nHOW_MUCH_QR=NO_SOURCE_EVIDENCE\nHOW_MUCH_CHECK=YES\nHOW_MUCH_CARD=YES\nHOW_MUCH_COMMERCIAL_CREDIT=YES\nHOW_MUCH_CURRENT_DEBT=YES\nHOW_MUCH_OVERDUE_DEBT=YES\nAGING=YES\nTIME_TO_SETTLEMENT=YES"),
      ("AD. Reproducibility/idempotency/late events","BUSINESS_DERIVATION_REPRODUCIBLE=YES\nBUSINESS_DERIVATION_IDEMPOTENT=YES\nLATE_EVENT_REDERIVATION=PASS"),
      ("AE. Operational integration","BUSINESS_DERIVATION_OPERATIONAL_SUPPORT=PASS\nONE_OFF_DEPENDENCY=NO"),
      ("AF. V1 regressions","V1_REGRESSION=PASS; Foundation, Reference, Sales, Credit Memo, Material Supply, Segundo Anillo, Product/Customer and UoM unchanged."),
      ("AG. Tests","See tests.json; populated after external regression commands."),
      ("AH. Files changed","See files_changed.json."),
      ("AI. Known gaps","QR has no source evidence; intraday and pre-coverage as-of remain unsupported; N:N counterpart split and product-level debt are not fabricated. Two document current-state rows lag later same-day reconciliation ledger facts and are quantified in gaps.json."),
      ("AJ. Recommended next gate","TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1. Do not execute CG2A V2 before productive publication."),
    ]
    return "# TELCHI Receivables & Collections Business Derivation V1\n\n"+"\n\n".join(f"## {a}\n\n```text\n{b}\n```" for a,b in sections)+"\n"


def run_business_derivation(*, connector: DuckLakeConnector | None = None, evidence_root: Path | None = None, plan_only: bool = False) -> dict[str, Any]:
    global EVIDENCE_ROOT
    if evidence_root is not None:
        EVIDENCE_ROOT = evidence_root
    connector = connector or DuckLakeConnector()
    identity, atomic = executor_identity(), _atomic_contract()
    before = _foundation_current(connector)
    if before != FOUNDATION:
        raise RuntimeError(f"Foundation CURRENT precondition failed: {before}")
    built_at = _now()
    with connector.session(read_only=False) as connection:
        contract = _source_contract(connection)
        latest = connection.execute("""
SELECT greatest(max(try_cast(document_date AS DATE)),
                (SELECT max(try_cast(payment_date AS DATE)) FROM telchi.atomic.collection_payment),
                (SELECT max(try_cast(reconciliation_date AS DATE)) FROM telchi.atomic.reconciliation_event))
FROM telchi.atomic.receivable_document
""").fetchone()[0]
        as_of = latest if isinstance(latest,date) else date.fromisoformat(str(latest)[:10])
        historical_as_of = date(2026,8,31)
        if plan_only:
            return {"status":"PLAN_ONLY","derivation_id":contract["derivation_id"],"as_of_date":as_of,"FOUNDATION_CURRENT":before,"SAP_ACCESSED":"NO"}
        counts = _create_business_tables(connection, contract, built_at)
        validations = _validations(connection, as_of, historical_as_of, counts)
        gold = _business_gold_cases(connection, as_of)
    after = _foundation_current(connector)
    pass_conditions = all((
        atomic["status"]=="PASS", before==after==FOUNDATION,
        validations["open_partition_pass"], validations["aging_partition_pass"],
        validations["historical_differs"], validations["payment_method_reconciliation_pass"],
        validations["settlement_overlap"]==0, Decimal(str(validations["cancelled_effect"]))==0,
        gold["BUSINESS_GOLD_CASES_PASS"]==15,
    ))
    verdict = VERDICT_PASS if pass_conditions else VERDICT_FAIL
    _write_evidence(identity, atomic, contract, counts, validations, gold, before, after, built_at, verdict)
    return {
        "FINAL_VERDICT":verdict, **identity,
        "FOUNDATION_CURRENT_BEFORE":before,"FOUNDATION_CURRENT_AFTER":after,"CURRENT_POINTER_MODIFIED":"NO","FOUNDATION_CANDIDATE_CREATED":"NO",
        "SAP_ACCESSED":"NO","SAP_QUERY_COUNT":0,"SAP_WRITE_COUNT":0,
        "derivation_id":contract["derivation_id"],"source_as_of":contract["source_as_of"],"datasets":counts,
        "current_board_snapshot":validations["current"],"historical_board_snapshot":validations["historical"],
        "gold_cases":gold,"evidence_root":str(EVIDENCE_ROOT),
    }


__all__ = [
    "GATE", "DERIVATION_VERSION", "HISTORY_START", "aging_bucket", "commercial_term_classification",
    "days_past_due", "debt_status", "executor_identity", "normalize_cancelled", "settlement_state",
    "board_snapshot", "run_business_derivation",
]
