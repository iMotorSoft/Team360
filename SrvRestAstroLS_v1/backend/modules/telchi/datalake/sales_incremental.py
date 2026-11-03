"""Sales-only incremental capture V1 (DEVELOPMENT, capture-only).

No Foundation writes. CLI deliberately permits only the offline-validated pilot
until a sales extraction budget is accredited. No automatic retries. Raw and
checkpoints live under DATA_ROOT, never in the source tree.

DocDate is business scope, UpdateDate is a coarse change indicator, DocEntry is
keyset pagination. Seven-day overlap is a proposed policy, NOT proof of complete
CDC: line-only changes without header UpdateDate, deletes, changes during paging,
and updates outside the overlap remain explicit gaps. Resume freezes the plan;
a fresh overlap run must reconcile changes after the frozen cutoff.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import signal
import time
from typing import Any
import uuid

from .create_initial import transform, validate_candidate, reconcile_candidate
from modules.telchi.runtime.config import open_safe_duckdb, DuckDBSafetyProfile
from .ducklake import DATA_ROOT
from .raw import digest, file_hash, write_raw
from .source import HanaReadOnlySource, HanaTransportLimits, hana_config
from .sql import SALES_EXTRACT_SQL, CREDIT_MEMO_EXTRACT_SQL, assert_read_only_select

CONTRACT = "sales-incremental-capture-v1.0.0"
DOMAINS = {"sales": ("OINV", "INV1"), "credit_memo": ("ORIN", "RIN1")}
GAPS = ["LINE_CHANGE_WITHOUT_HEADER_UPDATEDATE", "PHYSICAL_DELETION",
        "CONCURRENT_SOURCE_MUTATION_NOT_SNAPSHOT_ISOLATED", "CHANGES_OUTSIDE_OVERLAP",
        "SAP_TIMEZONE_NOT_VERIFIED", "FIRST_RUN_NO_ACCREDITED_CHANGE_WATERMARK"]


@dataclass(frozen=True)
class PilotBudget:
    """Proposal, not accredited for extensive capture. Different query classes.

    TOP 0 schema probes: no data transfer. Capture: <=5 whole documents,
    <=1000 joined rows; statement 5s, network wait 15s, connection 8s.
    Conservative 10s pauses; one block only, no second block authorized.
    180s session including 40s reserved for persistence/closure. Driver limits
    are not a hard server execution/remote cancellation verification guarantee.
    """
    max_window_days: int = 1
    max_documents: int = 5
    max_queries: int = 4
    query_pause_seconds: int = 10
    block_pause_seconds: int = 30
    total_seconds: int = 180
    close_reserve_seconds: int = 40


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def projection(domain: str) -> str:
    if domain not in DOMAINS:
        raise ValueError("unsupported sales domain")
    original = SALES_EXTRACT_SQL if domain == "sales" else CREDIT_MEMO_EXTRACT_SQL
    fields = original.split("FROM", 1)[0].strip()[len("SELECT"):].strip()
    extra = ['H."TransId"', 'H."DiscPrcnt" AS "HeaderDiscPrcnt"',
             'H."VatSum" AS "HeaderVatSum"']
    if domain == "sales":
        extra += ['H."UpdateDate"', 'H."CreateDate"']
    else:
        extra += ['H."TaxDate"', 'H."DocDueDate"']
    return fields + ", " + ", ".join(extra)


def query(domain: str, *, probe: bool = False, limit: int = 5) -> str:
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("pilot document bound exceeded")
    if domain not in DOMAINS:
        raise ValueError("unsupported sales domain")
    header, lines = DOMAINS[domain]
    if probe:
        sql = f'SELECT TOP 0 {projection(domain)} FROM "TELCHI"."{header}" H LEFT JOIN "TELCHI"."{lines}" L ON L."DocEntry"=H."DocEntry"'
    else:
        # Limit HEADERS, never joined rows: complete document replacement unit.
        header_page = f'''SELECT TOP {limit} H."DocEntry" FROM "TELCHI"."{header}" H
WHERE ((H."DocDate">=? AND H."DocDate"<?) OR (H."UpdateDate">=? AND H."UpdateDate"<?))
AND H."DocDate"<? AND H."DocEntry">? ORDER BY H."DocEntry"'''
        sql = f'''SELECT {projection(domain)} FROM "TELCHI"."{header}" H
JOIN ({header_page}) P ON P."DocEntry"=H."DocEntry"
LEFT JOIN "TELCHI"."{lines}" L ON L."DocEntry"=H."DocEntry"
ORDER BY H."DocEntry", L."LineNum"'''
    return assert_read_only_select(sql)


def plan(day: date, *, run_id: str | None = None, cursors: dict[str, int] | None = None) -> dict:
    if day > date.today():
        raise ValueError("future dates prohibited")
    end = day + timedelta(days=1)
    return dict(contract=CONTRACT, run_id=run_id or uuid.uuid4().hex,
                source="SAP_B1_HANA/TELCHI", business_from=day.isoformat(),
                business_to_exclusive=end.isoformat(), change_from=day.isoformat(),
                change_to_exclusive=end.isoformat(), document_cutoff_exclusive=end.isoformat(),
                created_at=now(), cursors_before=cursors or {name: -1 for name in DOMAINS},
                host_timezone=str(datetime.now().astimezone().tzinfo),
                source_timezone="NOT_VERIFIED", budget=asdict(PilotBudget()),
                limits=asdict(HanaTransportLimits()), overlap_days_proposed=7,
                incremental_completeness="PARTIAL", gaps=GAPS,
                publication="NOT_AUTHORIZED_BY_CAPTURE", scope="MINIMAL_PILOT_ONLY")


def validate_plan(p: dict) -> None:
    if (p["contract"] != CONTRACT or p["budget"] != asdict(PilotBudget()) or
            p["limits"] != asdict(HanaTransportLimits()) or p["source"] != "SAP_B1_HANA/TELCHI"):
        raise ValueError("unaccredited budget/contract")
    cursors = p.get("cursors_before", {name: -1 for name in DOMAINS})
    if set(cursors) != set(DOMAINS) or any(type(v) is not int or v < -1 for v in cursors.values()):
        raise ValueError("invalid native document cursors")
    start, end = date.fromisoformat(p["business_from"]), date.fromisoformat(p["business_to_exclusive"])
    if (end-start).days != 1 or start > date.today():
        raise ValueError("invalid pilot window")
    if (p["change_from"] != p["business_from"] or p["change_to_exclusive"] != p["business_to_exclusive"]
            or p["document_cutoff_exclusive"] != p["business_to_exclusive"]):
        raise ValueError("pilot change window mismatch")


def continuation_plan(root: Path) -> dict:
    """Offline proposal from verified cursors; NEVER execute or extend a pilot.

    Accreditation/authorization of another block remains an operational gate.
    A new overlap cycle resets cursors; continuing this frozen window does not.
    """
    with locked(root):
        previous = read_json(root / "plan.json")
        receipts = recover(root, previous)
        if set(receipts) != set(DOMAINS):
            raise ValueError("continuation requires both intact domain checkpoints")
        proposed = dict(previous, run_id=uuid.uuid4().hex, created_at=now(),
                        cursors_before={name: receipts[name]["metrics"]["last_cursor"] for name in DOMAINS},
                        continuation_of=previous["run_id"], continuation_plan_sha256=digest(previous))
        validate_plan(proposed)
        return proposed


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def seal(path: Path, value: Any) -> None:
    """Immutable, fsynced, no-clobber JSON commit. Orphan temp is untrusted."""
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temp, path)
        sync_dir(path.parent)
    finally:
        temp.unlink()


@contextmanager
def locked(root: Path):
    with (root / ".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_json(path: Path) -> Any:
    if path.is_symlink():
        raise ValueError("symlink checkpoint prohibited")
    return json.loads(path.read_text())


def validate_rows(domain: str, rows: list[dict], *, limit: int = 5, after: int = -1) -> dict:
    headers, keys = {}, set()
    for row in rows:
        entry, line = int(row["DocEntry"]), row.get("LineNum")
        if entry <= after or line is None or int(line) < 0:
            raise ValueError("document without lines or invalid native key")
        key = (entry, int(line))
        if key in keys:
            raise ValueError("duplicate document/line")
        keys.add(key)
        if not row.get("DocCur") or row.get("DocTotal") is None or not row.get("DocDate"):
            raise ValueError("missing monetary/document provenance")
        if (not Decimal(str(row["DocTotal"])).is_finite() or row.get("CANCELED") not in {"N", "Y", "C"}):
            raise ValueError("invalid source amount/cancellation")
        header = {k: v for k, v in row.items() if k not in {
            "LineNum", "LineStatus", "ItemCode", "Dscription", "Quantity", "unitMsr", "NumPerMsr",
            "WhsCode", "Price", "PriceBefDi", "LineCurrency", "LineRate", "LineDiscPrcnt", "LineTotal",
            "TotalFrgn", "TotalSumSy", "VatPrcnt", "LineVatSum", "LineSlpCode", "BaseType", "BaseEntry", "BaseLine"}}
        if entry in headers and headers[entry] != header:
            raise ValueError("inconsistent repeated header")
        headers[entry] = header
    if len(headers) > limit:
        raise ValueError("document budget exceeded")
    return dict(documents=len(headers), lines=len(keys), last_cursor=max(headers, default=after),
                cancellations=sum(h.get("CANCELED") != "N" for h in headers.values()),
                currencies=sorted({str(h["DocCur"]) for h in headers.values()}),
                header_sha256=digest(headers), line_key_sha256=digest(sorted(keys)))


def transform_capture(domain: str, rows: list[dict], manifest: dict):
    """Reuse the existing transform with accredited staging-native key types.

    Published update.py reconstructs VARCHAR native keys. hdbcli returns ints;
    passing those directly changes the existing transform's line-ID hash.
    Normalize only the native keys, retaining exact raw input separately.
    """
    canonical = [dict(row, DocEntry=str(int(row["DocEntry"])), LineNum=str(int(row["LineNum"]))) for row in rows]
    return transform(domain, canonical, manifest)


def reconcile_documents(domain: str, previous: list[dict], captured: list[dict]) -> tuple[list[dict], dict]:
    """Whole-document upsert, offline and idempotent; absent documents preserved.

    A removed line is replaced by the complete captured document, never merged
    line-by-line. Input must be a successfully completed document page. This
    does not turn an incomplete source window into a complete coverage proof.
    """
    validate_rows(domain, captured)
    grouped = {}
    for row in previous:
        grouped.setdefault(int(row["DocEntry"]), []).append(row)
    incoming = {}
    for row in captured:
        incoming.setdefault(int(row["DocEntry"]), []).append(row)
    counts = dict(new=0, modified=0, unchanged=0, cancelled=0)
    def identity(rows):
        return digest(sorted(rows, key=lambda r: int(r["LineNum"])))
    for entry, rows in incoming.items():
        if entry not in grouped:
            counts["new"] += 1
        elif identity(grouped[entry]) == identity(rows):
            counts["unchanged"] += 1
        else:
            counts["modified"] += 1
        counts["cancelled"] += rows[0].get("CANCELED") != "N"
        grouped[entry] = rows
    return [r for entry in sorted(grouped) for r in sorted(grouped[entry], key=lambda r: int(r["LineNum"]))], counts


def raw_rows(path: str) -> list[dict]:
    connection = open_safe_duckdb(":memory:", profile=DuckDBSafetyProfile(threads=1))
    try:
        cursor = connection.execute("SELECT * FROM read_parquet(?) LIMIT 1001", [path])
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def recover(root: Path, p: dict) -> dict:
    """Only durable, hash-verified receipts may advance a cursor. No SAP here."""
    validate_plan(p)
    result = {}
    for domain in DOMAINS:
        intent_path, receipt_path, commit_path = [root / f"{domain}.{s}.json" for s in ("intent", "receipt", "commit")]
        if not intent_path.exists():
            if receipt_path.exists() or commit_path.exists():
                raise ValueError("checkpoint without intent")
            continue
        intent = read_json(intent_path)
        cursor_before = p.get("cursors_before", {}).get(domain, -1)
        if intent != dict(plan_sha256=digest(p), domain=domain, cursor_before=cursor_before):
            raise ValueError("intent binding mismatch")
        if not receipt_path.exists():
            raise RuntimeError("UNCERTAIN_REQUEST_NO_AUTOMATIC_RETRY")
        receipt = read_json(receipt_path)
        if receipt["plan_sha256"] != digest(p) or receipt["domain"] != domain:
            raise ValueError("receipt binding mismatch")
        source_path = root / f"{domain}.source.json"
        if source_path.is_symlink() or file_hash(source_path) != receipt["source_rows_sha256"]:
            raise ValueError("source row hash mismatch")
        exact_rows = read_json(source_path)
        if validate_rows(domain, exact_rows, after=cursor_before) != receipt["metrics"]:
            raise ValueError("source checkpoint metric mismatch")
        raw = receipt.get("raw")
        if raw:
            raw_path = Path(raw["path"])
            expected_parent = (root / "raw" / domain / p["run_id"]).resolve()
            if raw_path.is_symlink() or raw_path.resolve().parent != expected_parent:
                raise ValueError("raw path binding mismatch")
            if file_hash(raw_path) != raw["file_hashes"][0]:
                raise ValueError("raw hash mismatch")
            stored = read_json(Path(raw["manifest_path"]))
            claimed = stored.pop("manifest_hash")
            if digest(stored) != claimed or claimed != raw["manifest_hash"]:
                raise ValueError("raw manifest mismatch")
            if stored.get("plan_sha256") != digest(p) or stored.get("row_count") != receipt["metrics"]["lines"]:
                raise ValueError("raw plan/count mismatch")
            replay = [{k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if v is not None else None)
                       for k, v in row.items()} for row in raw_rows(str(raw_path))]
            # DuckDB infers numeric/date fields; identity and exact file hash are
            # authoritative. Metric hashes use original source representations.
            replay_metrics = validate_rows(domain, replay, after=cursor_before)
            for key in ("documents", "lines", "last_cursor", "cancellations", "currencies"):
                if replay_metrics[key] != receipt["metrics"][key]:
                    raise ValueError("raw checkpoint metric mismatch")
        elif receipt["metrics"] != validate_rows(domain, [], after=cursor_before):
            raise ValueError("nonempty checkpoint without raw")
        commit = dict(journal="COMMITTED", receipt_sha256=file_hash(receipt_path),
                      plan_sha256=digest(p), cursor=receipt["metrics"]["last_cursor"])
        if commit_path.exists():
            if read_json(commit_path) != commit:
                raise ValueError("checkpoint hash mismatch")
        else:
            seal(commit_path, commit)
        result[domain] = receipt
    return result


def run(root: Path, p: dict, source: HanaReadOnlySource, *, sleep=time.sleep, clock=time.monotonic) -> dict:
    """One minimal block. Resume is offline-only for uncertain requests."""
    validate_plan(p)
    if source.limits != HanaTransportLimits():
        raise ValueError("effective driver limits required")
    if not root.exists():
        root.mkdir(parents=True, mode=0o700)
        sync_dir(root.parent)
    with locked(root):
        if not (root / "plan.json").exists():
            seal(root / "plan.json", p)
        elif read_json(root / "plan.json") != p:
            raise ValueError("resume plan changed")
        completed = recover(root, p)
        state = dict(status="PARTIAL", plan_sha256=digest(p), started_at=now(),
                     scope="MINIMAL_PILOT_ONLY", queries=[], retries=0, publication="NOT_ATTEMPTED",
                     incremental_completeness="PARTIAL", gaps=GAPS)
        started, stopped = clock(), []
        def stop(signum, frame):
            stopped.append(signum)
        previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            for domain in DOMAINS:
                if domain in completed:
                    continue
                for is_probe in (True, False):
                    if stopped or clock()-started + 40 + 45 + (10 if source.query_log else 0) >= 180:
                        raise RuntimeError("STOP_OR_SESSION_BUDGET")
                    if len(source.query_log) >= 4:
                        raise RuntimeError("QUERY_BUDGET")
                    if source.query_log:
                        sleep(10)
                    if stopped:
                        raise RuntimeError("STOP_REQUESTED")
                    sql = query(domain, probe=is_probe)
                    params = () if is_probe else tuple(p[k] for k in (
                        "business_from", "business_to_exclusive", "change_from", "change_to_exclusive",
                        "document_cutoff_exclusive")) + (p.get("cursors_before", {}).get(domain, -1),)
                    if not is_probe:
                        seal(root / f"{domain}.intent.json", dict(plan_sha256=digest(p), domain=domain, cursor_before=params[-1]))
                    rows = source.query_read_only(f"incremental_{domain}_{'schema' if is_probe else 'capture'}", sql, params)
                    if is_probe:
                        continue
                    persistence_started = clock()
                    # Retain exact decimal/text representations before Parquet
                    # schema inference and even if analytical validation rejects.
                    seal(root / f"{domain}.source.json", rows)
                    metrics = validate_rows(domain, rows, after=params[-1])
                    raw = None
                    validation = {}
                    if rows:
                        raw = write_raw(root=root / "raw", segment_id=domain, extraction_id=p["run_id"], rows=rows,
                                        metadata=dict(source_as_of=now(), contract=CONTRACT, plan_sha256=digest(p)))
                        # Standard raw persistence reused; make its files durable before journal commit.
                        for file in Path(raw["path"]).parent.iterdir():
                            with file.open("rb") as stream:
                                os.fsync(stream.fileno())
                        for directory in (Path(raw["path"]).parent, Path(raw["path"]).parent.parent, root / "raw"):
                            sync_dir(directory)
                        candidate = transform_capture(domain, rows, raw)
                        validation = dict(validation=validate_candidate(candidate, 1000),
                                          reconciliation=reconcile_candidate(candidate, candidate.source_rows),
                                          reconciliation_scope="CAPTURE_TRANSFORMATION_ONLY_NOT_INDEPENDENT_SAP_REREAD")
                        if validation["validation"]["status"] != "PASS":
                            raise ValueError("candidate validation failed")
                    receipt = dict(plan_sha256=digest(p), domain=domain, contract=CONTRACT,
                                   source_rows_sha256=file_hash(root / f"{domain}.source.json"),
                                   source=p["source"], window={k: p[k] for k in ("business_from", "business_to_exclusive", "change_from", "change_to_exclusive")},
                                   metrics=metrics, raw=raw, validation=validation,
                                   hana_ms=source.query_log[-1]["duration_ms"], captured_at=now(),
                                   persistence_seconds=clock()-persistence_started,
                                   window_exhausted=metrics["documents"] < 5,
                                   watermark_status="PILOT_ONLY_NOT_GLOBAL_CHANGE_WATERMARK")
                    seal(root / f"{domain}.receipt.json", receipt)
                    completed = recover(root, p)
                    if clock()-persistence_started > 10:
                        raise RuntimeError("PERSISTENCE_BUDGET_EXCEEDED")
            state["reason"] = "PILOT_COMPLETE_NO_EXTENSIVE_BUDGET_ACCREDITED"
        except BaseException as exc:
            safe_codes = {"STOP_OR_SESSION_BUDGET", "QUERY_BUDGET", "STOP_REQUESTED", "PERSISTENCE_BUDGET_EXCEEDED"}
            state.update(reason=type(exc).__name__, error_code=str(exc) if str(exc) in safe_codes else "REVIEW_LOCAL_JOURNAL")
        finally:
            for s, handler in previous.items():
                signal.signal(s, handler)
            state.update(queries=source.query_log, completed={k: v["metrics"] for k, v in completed.items()},
                         finished_at=now(), elapsed_seconds=clock()-started)
            seal(root / ("session-" + uuid.uuid4().hex + ".json"), state)
        return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "pilot", "recover"))
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 10, 1))
    parser.add_argument("--run-id")
    parser.add_argument("--authorize-hana", action="store_true")
    args = parser.parse_args()
    if args.run_id and (not args.run_id.replace("-", "").isalnum() or len(args.run_id) > 80):
        parser.error("invalid run id")
    p = plan(args.day, run_id=args.run_id)
    root = DATA_ROOT / "raw" / "sap" / CONTRACT / p["run_id"]
    if args.action == "plan":
        print(json.dumps(p, indent=2))
        return 0
    if (root / "plan.json").exists():
        p = read_json(root / "plan.json")
    if args.action == "recover":
        with locked(root):
            print(json.dumps({k: v["metrics"] for k, v in recover(root, p).items()}))
        return 0
    if not args.authorize_hana:
        parser.error("explicit --authorize-hana required")
    if hana_config()["schema"] != "TELCHI":
        raise ValueError("unexpected company schema")
    result = run(root, p, HanaReadOnlySource(limits=HanaTransportLimits()))
    print(json.dumps(dict(result, checkpoint_root=str(root)), indent=2))
    return 0 if len(result["completed"]) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
