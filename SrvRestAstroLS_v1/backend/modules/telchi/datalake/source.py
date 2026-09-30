"""SAP HANA READ ONLY source adapter for create_initial."""
from __future__ import annotations

import hashlib
import os
import shlex
import time
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from .planner import SegmentSpec, inventory_movement_segments_from_bounds, month_ranges, sales_segments_from_bounds
from .sql import (
    CREDIT_MEMO_DISCOVERY_SQL, CREDIT_MEMO_EXTRACT_SQL, CREDIT_MEMO_YTD_MAX_DATE_SQL,
    INVENTORY_EXTRACT_SQL, SALES_EXTRACT_SQL, SALES_DISCOVERY_SQL, OINM_FIELD_CANDIDATES,
    OINM_REQUIRED_FIELDS, OINM_YTD_MAX_DATE_SQL, OITW_SOURCE_AS_OF_SQL,
    SALES_YTD_MAX_DATE_SQL, assert_read_only_select, inventory_discovery_sql, oinm_extract_sql,
)

PRIVATE_HANA_ENV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/sap/hana.env")


class SourceAdapter(Protocol):
    def plan(self, start: date, end: date, *, max_rows: int, max_segments: int | None = None) -> list[SegmentSpec]: ...
    def extract(self, segment: SegmentSpec) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...
    def verify(self, segment: SegmentSpec) -> list[dict[str, Any]]: ...


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        if not separator:
            raise ValueError(f"invalid HANA private config line: {line!r}")
        parsed = shlex.split(raw, posix=True)
        if len(parsed) != 1:
            raise ValueError(f"invalid HANA private config value for {key}")
        values[key.strip()] = parsed[0]
    return values


def hana_config() -> dict[str, str]:
    private = _read_env(Path(os.getenv("TEAM360_TELCHI_SAP_PRIVATE_CONFIG", str(PRIVATE_HANA_ENV))))
    def value(key: str) -> str:
        return os.getenv(key, private.get(key, "")).strip()
    result = {
        "host": os.getenv("HANA_HOST", value("TELCHI_SAP_HANA_HOST")),
        "port": os.getenv("HANA_PORT", value("TELCHI_SAP_HANA_PORT")),
        "schema": os.getenv("HANA_SCHEMA", value("TELCHI_SAP_HANA_SCHEMA")),
        "user": os.getenv("HANA_USER", value("TELCHI_SAP_HANA_USER")),
        "password": os.getenv("HANA_PASSWORD", value("TELCHI_SAP_HANA_PASSWORD")),
    }
    missing = [key for key, item in result.items() if not item]
    if missing:
        raise RuntimeError(f"SAP HANA private configuration is incomplete: {', '.join(missing)}")
    return result


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _rows(cursor: Any, batch_size: int = 1000) -> list[dict[str, Any]]:
    columns = [str(item[0]) for item in cursor.description or ()]
    result: list[dict[str, Any]] = []
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            return result
        result.extend({column: _canonical(value) for column, value in zip(columns, row)} for row in batch)


class HanaReadOnlySource:
    """One explicit hdbcli connection per bounded operation, never a pool."""

    def __init__(self, *, connect_factory: Any | None = None) -> None:
        self._connect_factory = connect_factory
        self.query_log: list[dict[str, Any]] = []
        self.sap_write_count = 0
        self.oinm_schema: dict[str, Any] | None = None

    def _connect(self) -> tuple[Any, Any]:
        if self._connect_factory is not None:
            return self._connect_factory()
        from hdbcli import dbapi
        config = hana_config()
        connection = dbapi.connect(
            address=config["host"], port=int(config["port"]), user=config["user"],
            password=config["password"], currentSchema=config["schema"], encrypt="false",
        )
        return connection, connection.cursor()

    def query_read_only(self, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Public, explicitly read-only bounded query entry point.

        This is the single supported way for other modules (for example the
        Material Supply fact capture) to reuse this adapter without opening a
        second HANA connection strategy. The SQL is always passed through
        :func:`assert_read_only_select` first.
        """
        return self._execute(query_id, sql, params)

    def _execute(self, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        assert_read_only_select(sql)
        started = time.perf_counter()
        connection = cursor = None
        try:
            connection, cursor = self._connect()
            cursor.execute(sql, params)
            rows = _rows(cursor)
            self.query_log.append({
                "query_id": query_id, "query_hash": hashlib.sha256(sql.encode()).hexdigest(),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "rows_returned": len(rows), "sap_access_mode": "READ_ONLY", "sap_write_count": 0,
            })
            return rows
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()

    def plan(self, start: date, end: date, *, max_rows: int, max_segments: int | None = None) -> list[SegmentSpec]:
        from .planner import month_ranges
        bounds: list[tuple[str, str, int, int]] = []
        for month_from, month_to in month_ranges(start, end):
            rows = self._execute("sales_segment_discovery", SALES_DISCOVERY_SQL, (month_from.isoformat(), month_to.isoformat()))
            if not rows or rows[0].get("min_doc_entry") is None:
                continue
            bounds.append((month_from.isoformat(), month_to.isoformat(), int(rows[0]["min_doc_entry"]), int(rows[0]["max_doc_entry"])))
        # A key span is conservative: extraction still enforces max_rows and
        # the runner splits a range rather than increasing memory or threads.
        segments = sales_segments_from_bounds(bounds, max_docentries_per_segment=max_rows, prefix="sales")
        return segments if max_segments is None else segments[:max_segments]

    def plan_credit_memo(self, start: date, end: date, *, max_rows: int, max_segments: int | None = None) -> list[SegmentSpec]:
        """Plan ORIN/RIN1 by month and immutable DocEntry ranges."""
        bounds: list[tuple[str, str, int, int]] = []
        for month_from, month_to in month_ranges(start, end):
            rows = self._execute("credit_memo_segment_discovery", CREDIT_MEMO_DISCOVERY_SQL, (month_from.isoformat(), month_to.isoformat()))
            if rows and rows[0].get("min_doc_entry") is not None:
                bounds.append((month_from.isoformat(), month_to.isoformat(), int(rows[0]["min_doc_entry"]), int(rows[0]["max_doc_entry"])))
        segments = sales_segments_from_bounds(bounds, max_docentries_per_segment=max_rows, prefix="credit-memo")
        result = [SegmentSpec(item.segment_id, "credit_memo", item.business_date_from, item.business_date_to, item.key_from, item.key_to, item.strategy, item.scope, item.estimated_rows) for item in segments]
        return result if max_segments is None else result[:max_segments]

    def discover_oinm_schema(self) -> dict[str, Any]:
        """Discover OINM columns and DBAPI types without reading source rows.

        HANA installations used by Telchi do not expose OINM consistently in
        SYS.TABLE_COLUMNS, so each approved candidate is probed with TOP 0.
        Missing optional columns are recorded as nullable/unavailable; required
        fields fail closed before any extraction can be planned.
        """
        discovered: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for canonical, candidates in OINM_FIELD_CANDIDATES:
            found = False
            for physical in candidates:
                connection = cursor = None
                try:
                    connection, cursor = self._connect()
                    sql = f'SELECT TOP 0 "{physical}" AS "{canonical}" FROM "TELCHI"."OINM"'
                    assert_read_only_select(sql)
                    cursor.execute(sql)
                    description = cursor.description[0] if cursor.description else ()
                    discovered[canonical] = {
                        "canonical_name": canonical, "source_name": physical,
                        "type_code": str(description[1]) if len(description) > 1 else None,
                        "display_size": description[2] if len(description) > 2 else None,
                        "internal_size": description[3] if len(description) > 3 else None,
                        "precision": description[4] if len(description) > 4 else None,
                        "scale": description[5] if len(description) > 5 else None,
                        "nullable": description[6] if len(description) > 6 else None,
                    }
                    found = True
                    break
                except Exception:
                    continue
                finally:
                    if cursor is not None:
                        cursor.close()
                    if connection is not None:
                        try:
                            connection.rollback()
                        finally:
                            connection.close()
            if not found:
                missing.append(canonical)
        available = {key: value["source_name"] for key, value in discovered.items()}
        required_missing = sorted(OINM_REQUIRED_FIELDS - set(available))
        if required_missing:
            raise RuntimeError(f"OINM schema discovery missing required fields: {required_missing}")
        if "TransSeq" in available:
            source_key_columns = ["TransNum", "TransSeq"]
        elif "Instance" in available:
            source_key_columns = ["TransNum", "Instance"]
        elif {"DocLineNum", "ItemCode", "Warehouse"} <= set(available):
            source_key_columns = ["TransNum", "DocLineNum", "ItemCode", "Warehouse"]
        else:
            source_key_columns = ["TransNum", "DocDate", "ItemCode", "Warehouse"]
        result = {
            "source_table": "OINM", "schema": "TELCHI", "columns": list(discovered.values()),
            "available_columns": sorted(available), "missing_candidates": missing,
            "source_key_columns": source_key_columns,
            "source_key_resolution": "PREFERRED_NATIVE_SEQUENCE" if source_key_columns == ["TransNum", "TransSeq"] else "OBSERVED_FALLBACK",
            "schema_discovery_method": "TOP_0_EXPLICIT_COLUMN_PROBES",
        }
        self.oinm_schema = result
        return result

    def analyze_oinm_source_key(self) -> dict[str, Any]:
        schema = self.oinm_schema or self.discover_oinm_schema()
        key_columns = list(schema["source_key_columns"])
        projection = ", ".join(f'M."{schema_column["source_name"]}"' for schema_column in (next(item for item in schema["columns"] if item["canonical_name"] == name) for name in key_columns))
        group_projection = ", ".join(f'M."{next(item for item in schema["columns"] if item["canonical_name"] == name)["source_name"]}"' for name in key_columns)
        sql = f'SELECT COUNT(*) AS "duplicate_source_key_count", COALESCE(SUM("key_count" - 1), 0) AS "duplicate_source_rows" FROM (SELECT {group_projection}, COUNT(*) AS "key_count" FROM "TELCHI"."OINM" M GROUP BY {group_projection} HAVING COUNT(*) > 1) D'
        duplicate = self._execute("oinm_source_key_duplicate_analysis", sql)
        null_sql = "SELECT " + ", ".join(f'SUM(CASE WHEN M."{next(item for item in schema["columns"] if item["canonical_name"] == name)["source_name"]}" IS NULL THEN 1 ELSE 0 END) AS "{name}"' for name in key_columns) + ' FROM "TELCHI"."OINM" M'
        nulls = self._execute("oinm_source_key_null_analysis", null_sql)
        row = duplicate[0] if duplicate else {}
        null_row = nulls[0] if nulls else {}
        result = {
            "source_table": "OINM", "source_key_columns": key_columns,
            "source_key_unique": int(row.get("duplicate_source_key_count") or 0) == 0,
            "duplicate_source_key_count": int(row.get("duplicate_source_key_count") or 0),
            "duplicate_source_rows": int(row.get("duplicate_source_rows") or 0),
            "key_null_counts": {name: int(null_row.get(name) or 0) for name in key_columns},
            "identity_resolution": "EXACT_NATIVE_KEY" if int(row.get("duplicate_source_key_count") or 0) == 0 and all(int(null_row.get(name) or 0) == 0 for name in key_columns) else "UNRESOLVED",
        }
        schema["source_key_analysis"] = result
        return result

    def analyze_oinm_nullability(self) -> dict[str, Any]:
        schema = self.oinm_schema or self.discover_oinm_schema()
        fields = [item["canonical_name"] for item in schema["columns"]]
        required = ["TransNum", "TransSeq", "Instance", "TransType", "DocDate", "ItemCode", "Warehouse", "InQty", "OutQty"]
        references = ["DocEntry", "BaseRef", "CreatedBy", "AppObjAbs", "AppObjType", "DocLineNum", "Ref1", "Ref2"]
        selected = [name for name in required + references if name in fields]
        expressions = ", ".join(f'SUM(CASE WHEN M."{next(item for item in schema["columns"] if item["canonical_name"] == name)["source_name"]}" IS NULL THEN 1 ELSE 0 END) AS "{name}"' for name in selected)
        row = self._execute("oinm_nullability_analysis", f'SELECT COUNT(*) AS "row_count", {expressions} FROM "TELCHI"."OINM" M')[0]
        return {"source_table": "OINM", "row_count": int(row.get("row_count") or 0), "identity_columns": [name for name in selected if name in {"TransNum", "TransSeq", "Instance", "DocDate", "ItemCode", "Warehouse"}], "reference_columns": [name for name in selected if name in set(references)], "null_counts": {name: int(row.get(name) or 0) for name in selected}, "nullable_reference_policy": "OPTIONAL_SOURCE_REFERENCE_NULL_ALLOWED"}

    def oinm_trans_type_sample(self, *, start: date | None = None, end: date | None = None) -> dict[str, Any]:
        schema = self.oinm_schema or self.discover_oinm_schema()
        date_name = next(item for item in schema["columns"] if item["canonical_name"] == "DocDate")["source_name"]
        predicate = ""
        params: tuple[Any, ...] = ()
        if start and end:
            predicate = f' WHERE M."{date_name}" >= ? AND M."{date_name}" < ?'
            params = (start.isoformat(), end.isoformat())
        rows = self._execute("oinm_trans_type_sample", f'SELECT TOP 21 M."{next(item for item in schema["columns"] if item["canonical_name"] == "TransType")["source_name"]}" AS "TransType", COUNT(*) AS "row_count" FROM "TELCHI"."OINM" M{predicate} GROUP BY M."{next(item for item in schema["columns"] if item["canonical_name"] == "TransType")["source_name"]}" ORDER BY COUNT(*) DESC', params)
        return {"source_table": "OINM", "rows": rows, "scope": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None}}

    def discover_2026_bounds(self, start: date) -> dict[str, Any]:
        """Discover YTD boundaries without selecting operational source rows."""
        started = time.perf_counter()
        connectivity = self._execute("baseline_connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if not connectivity or connectivity[0].get("ok") != 1:
            raise RuntimeError("SAP connectivity preflight failed")
        sales = self._execute("baseline_sales_source_max_date", SALES_YTD_MAX_DATE_SQL, (start.isoformat(),))
        movements = self._execute("baseline_oinm_source_max_date", OINM_YTD_MAX_DATE_SQL, (start.isoformat(),))
        credit_memos = self._execute("baseline_credit_memo_source_max_date", CREDIT_MEMO_YTD_MAX_DATE_SQL, (start.isoformat(),))
        current = self._execute("baseline_oitw_source_as_of", OITW_SOURCE_AS_OF_SQL)
        return {
            "hana_connectivity": "PASS", "hana_latency_ms": latency_ms,
            "sales_source_max_date": _canonical(sales[0].get("max_doc_date")) if sales else None,
            "oinm_source_max_date": _canonical(movements[0].get("max_doc_date")) if movements else None,
            "credit_memo_source_max_date": _canonical(credit_memos[0].get("max_doc_date")) if credit_memos else None,
            "oitw_source_as_of": _canonical(current[0].get("source_as_of")) if current else None,
            "oitw_source_row_count": int(current[0].get("row_count") or 0) if current else 0,
            "sap_mode": "READ_ONLY", "sap_write_count": self.sap_write_count,
            "query_log": list(self.query_log),
        }

    def discover_inventory(self, *, max_rows: int, max_segments: int | None = None) -> list[SegmentSpec]:
        cursor_key = ("", "", "")
        specs: list[SegmentSpec] = []
        ordinal = 0
        while max_segments is None or ordinal < max_segments:
            sql = inventory_discovery_sql(max_rows)
            rows = self._execute("inventory_segment_discovery", sql, cursor_key)
            if not rows:
                break
            # The discovery is bounded. One returned page is one executable
            # group, and the next page starts after its final native key.
            first = (str(rows[0]["ItemCode"]), str(rows[0]["WhsCode"]))
            last = (str(rows[-1]["ItemCode"]), str(rows[-1]["WhsCode"]))
            specs.append(SegmentSpec(
                segment_id=f"inventory-{ordinal:04d}", domain="inventory",
                business_date_from=None, business_date_to=None,
                key_from="\x1f".join(first), key_to="\x1f".join(last),
                strategy="ITEMCODE_WHS_BOUNDED_GROUP",
                scope=f"ItemCode x WhsCode {first[0]}×{first[1]} .. {last[0]}×{last[1]}",
                estimated_rows=len(rows),
            ))
            cursor_key = (last[0], last[1], "")
            if len(rows) < max_rows:
                break
            ordinal += 1
        return specs if max_segments is None else specs[:max_segments]

    def plan_inventory_movement(self, start: date, end: date, *, max_transnum_per_segment: int = 100_000, max_segments: int | None = None) -> list[SegmentSpec]:
        schema = self.oinm_schema or self.discover_oinm_schema()
        date_name = next(item for item in schema["columns"] if item["canonical_name"] == "DocDate")["source_name"]
        trans_name = next(item for item in schema["columns"] if item["canonical_name"] == "TransNum")["source_name"]
        bounds: list[tuple[str, str, int, int, int]] = []
        for month_from, month_to in month_ranges(start, end):
            rows = self._execute("oinm_monthly_segment_discovery", f'SELECT MIN(M."{date_name}") AS "min_doc_date", MAX(M."{date_name}") AS "max_doc_date", MIN(M."{trans_name}") AS "min_trans_num", MAX(M."{trans_name}") AS "max_trans_num", COUNT(*) AS "row_count" FROM "TELCHI"."OINM" M WHERE M."{date_name}" >= ? AND M."{date_name}" < ?', (month_from.isoformat(), month_to.isoformat()))
            if rows and rows[0].get("min_trans_num") is not None:
                bounds.append((month_from.isoformat(), month_to.isoformat(), int(rows[0]["min_trans_num"]), int(rows[0]["max_trans_num"]), int(rows[0]["row_count"] or 0)))
        planned = inventory_movement_segments_from_bounds(bounds, max_transnum_per_segment=max_transnum_per_segment, domain="inventory_movement")
        candidates = planned if max_segments is None else planned[:max_segments]
        # Monthly min/max TransNum bounds can contain gaps. Empty ranges are
        # recorded explicitly by create_initial rather than hidden as gaps.
        nonempty: list[SegmentSpec] = []
        seen = {item.segment_id for item in candidates}
        ordered = candidates + ([] if max_segments is None else [item for item in planned if item.segment_id not in seen])
        for spec in ordered:
            rows = self._execute("oinm_segment_cardinality_probe", f'SELECT COUNT(*) AS "row_count" FROM "TELCHI"."OINM" M WHERE M."{date_name}" >= ? AND M."{date_name}" < ? AND M."{trans_name}" >= ? AND M."{trans_name}" < ?', (spec.business_date_from, spec.business_date_to, int(spec.key_from), int(spec.key_to)))
            if rows and int(rows[0].get("row_count") or 0) > 0:
                nonempty.append(spec)
            if max_segments is not None and len(nonempty) >= max_segments:
                break
        return nonempty

    def extract(self, segment: SegmentSpec) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if segment.domain == "sales":
            params = (segment.business_date_from, segment.business_date_to, int(segment.key_from), int(segment.key_to))
            sql = SALES_EXTRACT_SQL
            query_id = "sales_extract"
        elif segment.domain == "credit_memo":
            params = (segment.business_date_from, segment.business_date_to, int(segment.key_from), int(segment.key_to))
            sql = CREDIT_MEMO_EXTRACT_SQL
            query_id = "credit_memo_extract"
        elif segment.domain == "inventory":
            first_item, first_whs = segment.key_from.split("\x1f", 1)
            last_item, last_whs = segment.key_to.split("\x1f", 1)
            params = (first_item, first_item, first_whs, last_item, last_item, last_whs)
            sql = INVENTORY_EXTRACT_SQL
            query_id = "inventory_extract"
        else:
            schema = self.oinm_schema or self.discover_oinm_schema()
            sql = oinm_extract_sql({item["canonical_name"]: item["source_name"] for item in schema["columns"]})
            params = (segment.business_date_from, segment.business_date_to, int(segment.key_from), int(segment.key_to))
            query_id = "oinm_extract"
        rows = self._execute(query_id, sql, params)
        metadata = {"query_id": query_id, "query_hash": hashlib.sha256(sql.encode()).hexdigest()}
        if segment.domain == "inventory":
            as_of = self._execute("oitw_source_as_of_for_segment", OITW_SOURCE_AS_OF_SQL)
            metadata["source_as_of"] = _canonical(as_of[0].get("source_as_of")) if as_of else None
            metadata["source_type"] = "CURRENT_STATE"
        if segment.domain in {"inventory_movement", "inventory_movements"}:
            metadata["source_key_columns"] = list((self.oinm_schema or {}).get("source_key_columns", ["TransNum", "TransSeq"]))
            metadata["source_columns"] = sorted((self.oinm_schema or {}).get("available_columns", []))
        return rows, metadata

    def verify(self, segment: SegmentSpec) -> list[dict[str, Any]]:
        return self.extract(segment)[0]
