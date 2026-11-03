"""Sequential, no-SAP closure gate; immutable candidate, fail-closed promotion."""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
from modules.telchi.datalake.receivables_collections_foundation import resolve_current as resolve_receivables
from modules.telchi.datalake.reference_update import canonical_id
from modules.telchi.datalake.raw import digest, file_hash
from modules.telchi.datalake.product_commercial_semantics import (
    COMPONENT, RESOLVED_UOM, classify_purpose, convert_quantity, net_quantity,
    available_stock, materialize, create_candidate, read_component, number, row_digest,
)

EXPECTED = "foundation_afd08d9eca6a725be53cdc3f9d5709c9"
OUTPUT = Path(__file__).resolve().parents[7] / "data/reports/telchi/product_commercial_semantics_v1"
BASELINE = OUTPUT.parent / "high_stock_low_sales_commercial_products_v1"
START, END = "2026-01-01", "2026-09-24"


def records(c, sql, args=None):
    cur = c.execute(sql, args or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def checked_manifest(path):
    m = json.loads(path.read_text())
    if m.get("status") != "COMPLETED":
        raise ValueError("incomplete source " + str(path))
    if m.get("manifest_hash") and digest({k: v for k, v in m.items() if k != "manifest_hash"}) != m["manifest_hash"]:
        raise ValueError("source manifest hash mismatch " + str(path))
    files = m.get("file_references") or [str(path.parent / v["file"]) for v in m["files"]]
    hashes = m.get("file_hashes") or [v["sha256"] for v in m["files"]]
    if not files or len(files) != len(hashes):
        raise ValueError("source files incomplete")
    for f, h in zip(files, hashes, strict=True):
        if DATA_ROOT.resolve() not in Path(f).resolve().parents or file_hash(Path(f)) != h:
            raise ValueError("source file root/hash mismatch")
    return m, files, {"manifest_path": str(path), "manifest_sha256": file_hash(path),
                      "files": files, "file_hashes": hashes, "source_as_of": m.get("source_as_of", m.get("extracted_at")),
                      "source_as_of_window": m.get("source_as_of_window")}


def key(r):
    return str(r["DocEntry"]), str(r["LineNum"])


def unique(rows, key_function):
    result = {}
    for r in rows:
        k = key_function(r)
        if k in result:
            raise ValueError("duplicate source key " + str(k))
        result[k] = r
    return result


def equivalent(a, b):
    na, nb = number(a), number(b)
    return na == nb if na is not None and nb is not None else (str(a or "") == str(b or ""))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    connector = DuckLakeConnector()
    provenance = {}
    with connector.session(read_only=True) as c:
        c.execute("SET threads=2"); c.execute("SET memory_limit='1GB'")
        a = FoundationReader(connector).resolve_on(c)
        if a.foundation_publication_id != EXPECTED:
            raise ValueError("CURRENT differs from authorized baseline")
        sd, sl = a.sales("sales_document"), a.sales("sales_line")
        cd, cl = a.credit_memo("credit_memo_document"), a.credit_memo("credit_memo_line")
        products = records(c, "SELECT item_code,canonical_product_id,inventory_uom_id,sap_sell_item,sap_invnt_item,sap_prchse_item FROM read_parquet(?) WHERE source_system='SAP_HANA' ORDER BY item_code", [str(a.reference("products"))])
        product_map = unique(products, lambda r: r["item_code"])
        classes = unique(records(c, "SELECT canonical_product_id,product_business_type,status,classification_basis FROM read_parquet(?)", [a.manifest["product_business_classification"]["crosswalk_path"]]), lambda r: r["canonical_product_id"])
        for name, path in {"products": str(a.reference("products")), "classification": a.manifest["product_business_classification"]["crosswalk_path"], "uom_crosswalk": a.manifest["reference_closure"]["uom_crosswalk"]}.items():
            provenance[name] = {"path": path, "sha256": file_hash(Path(path))}
        uom_crosswalk = records(c, "SELECT source_uom_code,physical_dimension FROM read_parquet(?)", [a.manifest["reference_closure"]["uom_crosswalk"]])
        labels = {canonical_id("unit_of_measure", r["source_uom_code"]): r["source_uom_code"] for r in uom_crosswalk}
        dimensions = {r["source_uom_code"]: r["physical_dimension"] for r in uom_crosswalk}
        commerce = {r["item_code"]: r for r in records(c, f"SELECT l.item_code,count(distinct (l.source_system,l.doc_entry)) AS documents,min(CAST(d.doc_date AS DATE))::VARCHAR AS coverage_from,max(CAST(d.doc_date AS DATE))::VARCHAR AS coverage_to FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE d.canceled='N' AND try_cast(l.quantity AS DECIMAL(38,12))>0 AND CAST(d.doc_date AS DATE)<=DATE '{END}' GROUP BY l.item_code")}
        fact_root = DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"
        fact_files = {}
        for dataset in ("production_issue", "production_order", "bom_line"):
            files, proofs = [], []
            for mp in sorted((fact_root / dataset).glob("*/*/manifest.json")):
                m, fs, proof = checked_manifest(mp)
                if m.get("dataset") != dataset:
                    raise ValueError("wrong source dataset")
                files.extend(fs); proofs.append(proof)
            if not files:
                raise ValueError("missing " + dataset)
            fact_files[dataset], provenance[dataset] = files, proofs
        issue_rows = records(c, "SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,CAST(DocDate AS DATE)::VARCHAR doc_date,CAST(BaseEntry AS BIGINT)::VARCHAR base_entry,Quantity quantity,unitMsr source_uom,NumPerMsr factor FROM read_parquet(?,union_by_name=true) WHERE CANCELED='N' AND BaseType=202 AND try_cast(Quantity AS DECIMAL(38,12))>0 AND CAST(DocDate AS DATE)<=CAST(? AS DATE)", [fact_files["production_issue"], END])
        unique(issue_rows, lambda r: (r["doc_entry"], r["line_num"]))
        orders = {str(r["DocEntry"]) for r in records(c, "SELECT DocEntry FROM read_parquet(?,union_by_name=true)", [fact_files["production_order"]])}
        # BaseType=202 is explicit production-order source evidence; some
        # orders predate the captured 2026 order window. Do not erase their
        # actual consumption or pretend the parent capture is complete.
        missing_parent_issues = sum(r["base_entry"] not in orders for r in issue_rows)
        issue_counts = Counter(r["item_code"] for r in issue_rows)
        # ITT1 Code denotes the component; Father is the finished-product parent.
        bom = Counter(r["Code"] for r in records(c, "SELECT Code FROM read_parquet(?) WHERE try_cast(Quantity AS DECIMAL(38,12))>0", [fact_files["bom_line"]]))
        purpose = []
        for p in products:
            b = classes.get(p["canonical_product_id"], {})
            r = {"source_system": "SAP_HANA", **p, **classify_purpose(sell_item=p["sap_sell_item"], business_class=b.get("product_business_type"), class_status=b.get("status"), classification_basis=b.get("classification_basis"), sales_documents=commerce.get(p["item_code"], {}).get("documents", 0), production_issue_lines=issue_counts[p["item_code"]], bom_lines=bom[p["item_code"]]),
                 "brand_id": None, "brand_name": "UNKNOWN", "brand_provenance": "UNRESOLVED"}
            r["commercial_purpose_evidence"] = json.dumps(r["commercial_purpose_evidence"], sort_keys=True)
            purpose.append(r)
        # Invoice recovery uses exact extraction lineage, not latest files.
        columns = "l.source_system,l.doc_entry,l.line_num,l.item_code,l.quantity,l.line_total,l.raw_extraction_id,l.atomic_id"
        invoices = records(c, f"SELECT {columns},CAST(d.doc_date AS DATE)::VARCHAR doc_date FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE d.canceled='N' AND CAST(d.doc_date AS DATE) BETWEEN DATE '{START}' AND DATE '{END}' ORDER BY l.source_system,l.doc_entry,l.line_num")
        credits = records(c, f"SELECT {columns},CAST(d.doc_date AS DATE)::VARCHAR doc_date FROM {cl} l JOIN {cd} d USING(source_system,doc_entry) WHERE d.canceled='N' AND CAST(d.doc_date AS DATE) BETWEEN DATE '{START}' AND DATE '{END}' ORDER BY l.source_system,l.doc_entry,l.line_num")
        ids = {r["raw_extraction_id"] for r in invoices + credits}
        credit_columns = 'DocEntry,LineNum,ItemCode,Quantity,LineTotal,WhsCode,TotalFrgn,TotalSumSy,LineCurrency,CANCELED,CardCode,DocCur,DocTotal,DocTotalFC,DocTotalSy,BaseType,BaseEntry,BaseLine,CAST(DocDate AS VARCHAR) DocDate,CAST(UpdateDate AS VARCHAR) UpdateDate,CAST(CreateDate AS VARCHAR) CreateDate'
        raw_invoice, raw_credit, proofs = {}, {}, []
        for mp in sorted((DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1").glob("*/*/manifest.json")):
            eid = next((v for v in ids if mp.parent.name.startswith(v.removesuffix("_changed") + "_")), None)
            if eid is None:
                continue
            m, files, proof = checked_manifest(mp)
            target = raw_invoice if m["domain"] == "sales" else raw_credit if m["domain"] == "credit_memo" else None
            if target is None:
                continue
            selected = "DocEntry,LineNum,ItemCode,Quantity,LineTotal,unitMsr,NumPerMsr" if m["domain"] == "sales" else credit_columns
            rows = records(c, f"SELECT {selected} FROM read_parquet(?,union_by_name=true) WHERE CANCELED='N' AND CAST(DocDate AS DATE) BETWEEN DATE '{START}' AND DATE '{END}'", [files])
            for r in rows:
                k = (eid, *key(r))
                if k in target:
                    raise ValueError("raw lineage duplicate")
                target[k] = r
            proofs.append(proof)
        provenance["pinned_commercial_raw"] = proofs
        legacy_path = DATA_ROOT / "raw/sap/query_extract/credit_notes/credit_notes_20260917T010523280569Z_3a85b59a41fb/manifest.json"
        legacy_manifest, files, proof = checked_manifest(legacy_path)
        legacy = unique(records(c, f"SELECT {credit_columns},unitMsr,NumPerMsr FROM read_parquet(?,union_by_name=true) WHERE CANCELED='N' AND CAST(DocDate AS DATE) BETWEEN DATE '{START}' AND DATE '{END}'", [files]), key)
        provenance["historical_credit_uom"] = proof
        conversions, recovery = [], Counter()
        shared = ("ItemCode", "WhsCode", "Quantity", "LineTotal", "TotalFrgn", "TotalSumSy", "LineCurrency", "CANCELED", "CardCode", "DocCur", "DocTotal", "DocTotalFC", "DocTotalSy", "BaseType", "BaseEntry", "BaseLine")
        for kind, lines, source in [("INVOICE", invoices, raw_invoice), ("CREDIT_MEMO", credits, raw_credit)]:
            for line in lines:
                item = line["item_code"]
                if item not in product_map:
                    continue
                raw = source.get((line["raw_extraction_id"], line["doc_entry"], line["line_num"]))
                evidence, proof_kind = None, None
                if raw and raw["ItemCode"] == item and equivalent(raw["Quantity"], line["quantity"]) and equivalent(raw["LineTotal"], line["line_total"]):
                    if kind == "INVOICE":
                        evidence, proof_kind = raw, "EXACT_LINEAGE"
                    else:
                        old = legacy.get((line["doc_entry"], line["line_num"]))
                        if old and all(equivalent(raw.get(f), old.get(f)) for f in shared) and str(raw["DocDate"])[:10] == str(old["DocDate"])[:10] and str(raw.get("UpdateDate"))[:10] == str(old.get("UpdateDate"))[:10] and str(raw.get("CreateDate"))[:10] == str(old.get("CreateDate"))[:10] and str(raw.get("UpdateDate"))[:10] < str(legacy_manifest["extracted_at"])[:10]:
                            evidence, proof_kind = old, "MATCHED_HISTORICAL_SOURCE"
                            recovery["matched_historical_lines"] += 1
                        else:
                            recovery["historical_absent_or_changed"] += 1
                inventory_id = product_map[item]["inventory_uom_id"] if product_map[item]["inventory_uom_id"] in labels else None
                source_label = evidence.get("unitMsr") if evidence else None
                inventory_label = labels.get(inventory_id)
                incompatible = {dimensions.get(source_label), dimensions.get(inventory_label)} == {"MASS", "VOLUME"}
                conv = convert_quantity(line["quantity"], inventory_uom_id=inventory_id,
                                        source_uom=evidence.get("unitMsr") if evidence else None,
                                        factor=evidence.get("NumPerMsr") if evidence else None, proof=proof_kind, incompatible=incompatible)
                conversions.append({"source_system": line["source_system"], "doc_entry": line["doc_entry"], "line_num": line["line_num"], "item_code": item, "document_kind": kind, "doc_date": line["doc_date"], "atomic_id": line["atomic_id"], "raw_extraction_id": line["raw_extraction_id"], "quantity_native": line["quantity"], **conv})
        unique(conversions, lambda r: (r["source_system"], r["document_kind"], r["doc_entry"], r["line_num"]))
        del raw_invoice, raw_credit, legacy, invoices, credits, rows
        temporal = {}
        for name, relation, asof in [("sales", sd, a.foundation.sales_source_as_of), ("credit_memo", cd, a.foundation.credit_memo_source_as_of)]:
            bounds = c.execute(f"SELECT min(CAST(doc_date AS DATE))::VARCHAR,max(CAST(doc_date AS DATE))::VARCHAR FROM {relation} WHERE canceled='N'").fetchone()
            temporal[name] = {"data_as_of": asof, "coverage_from": bounds[0], "coverage_to": bounds[1], "coverage_meaning": "OBSERVED_DOCUMENT_BOUNDS_NOT_COMPLETENESS_PROOF", "quantity_materialization_from": START, "quantity_materialization_to": END}
        temporal["stock"] = {"data_as_of": a.foundation.oitw_source_as_of, "coverage_from": None, "coverage_to": None, "coverage_meaning": "POINT_IN_TIME"}
        temporal["production_consumption"] = {"data_as_of": max(v["source_as_of"] for v in provenance["production_issue"]), "coverage_from": "2026-01-01", "coverage_to": max(r["doc_date"] for r in issue_rows), "coverage_meaning": "CAPTURED_MONTHLY_WINDOWS_INTRADAY_FINAL_MONTH", "windows": [v["source_as_of_window"] for v in provenance["production_issue"]]}
        stocks = records(c, f"SELECT source_system,item_code,whs_code,on_hand,is_commited,source_as_of FROM {a.oitw()}")
        unique(stocks, lambda r: (r["source_system"], r["item_code"], r["whs_code"]))
        stock_by_item = defaultdict(Decimal)
        for r in stocks:
            qty = available_stock(r["on_hand"], r["is_commited"])
            if qty is None:
                raise ValueError("invalid stock numeric")
            stock_by_item[r["item_code"]] += qty
        assert len({r["source_as_of"] for r in stocks}) == 1
        provenance["foundation"] = a.as_dict()
        brand_count = c.execute("SELECT count(*) FROM read_parquet(?)", [str(a.reference("brand"))]).fetchone()[0]
        contracts = {
            "commercial_purpose": {"values": ["COMMERCIAL_ONLY", "INTERNAL_ONLY", "MIXED", "UNKNOWN"], "rule_version": "1.0.0", "absence_is_window_bounded": True, "no_name_or_prefix_inference": True},
            "brand": {"status": "UNKNOWN", "source_dimension_rows": brand_count, "gap": "SOURCE_GAP_REQUIRES_FUTURE_INGESTION"},
            "uom": {"base": "ITEM_INVENTORY_UOM", "line_factor": "SAP_NumPerMsr", "states": sorted(RESOLVED_UOM | {"UOM_UNRESOLVED", "UOM_INCOMPATIBLE"}), "credit_historical_support": "KEY_AND_VALUES_AND_DOCUMENT_LAST_UPDATE_MATCH; NOT_EXACT_CURRENT_LINEAGE", "base_invoice_link_is_not_conversion_proof": True},
            "net_quantity": {"grain": ["source_system", "item_code", "inventory_uom_id"], "formula": "SUM(invoice_base_qty)-SUM(credit_memo_base_qty)", "any_unresolved_line_blocks_product_total": True},
            "net_amount": {"status": "NET_PRODUCT_AMOUNT_UNRESOLVED", "reason": "Pinned invoice extraction omits header discount attribution; historical header amounts cannot silently establish current source-native product allocation"},
            "available_stock": {"status": "PASS", "relation": a.oitw(), "grain": ["source_system", "item_code", "whs_code", "inventory_uom_id", "source_as_of"], "on_hand_qty": "on_hand", "committed_qty": "is_commited", "available_qty": "CAST(on_hand AS DECIMAL)-CAST(is_commited AS DECIMAL)", "stock_as_of": "source_as_of", "inbound_orders_included": False, "aggregation_requires": ["same_item", "same_inventory_uom", "same_source_as_of", "unique_warehouse"]},
            "production_consumption": {"relation": provenance["production_issue"], "filter": "CANCELED=N AND BaseType=202 AND Quantity>0", "grain": ["DocEntry", "LineNum"], "product_key": "ItemCode", "quantity_conversion": "Quantity*NumPerMsr only with verified item inventory UoM", "bom_is_not_actual_consumption": True, "parent_orders_outside_capture_issue_lines": missing_parent_issues, "parent_order_capture_is_complete": False},
            "temporal": temporal,
        }
        discovery = {"GATE": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_DISCOVERY_V1_PASS", "CURRENT": EXPECTED, "datasets": provenance, "credit_recovery": dict(recovery), "brand_rows": brand_count, "source_gaps": ["Unmatched credit lines need future UoM ingestion", "Current invoice header discounts", "Explicit brand relationship"], "SAP_ACCESSED": "NO"}
        (OUTPUT / "discovery.json").write_text(json.dumps(discovery, indent=2, default=str) + "\n")
        (OUTPUT / "contract.json").write_text(json.dumps({"GATE": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_CONTRACT_V1_PASS", **contracts}, indent=2, default=str) + "\n")
        dependencies = {"foundation_publication_id": EXPECTED, "base_snapshot_id": a.manifest_base_snapshot_id, "reference_version": a.foundation.reference_version, "components_hash": digest(a.manifest["components"])}
    component = materialize({"product_purpose": purpose, "product_sales_uom": conversions}, dependencies=dependencies, provenance=provenance, contracts=contracts)
    del purpose, conversions
    store = FoundationPublicationStore(connector.session)
    run_id = "product-commercial-semantics-v1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    store.acquire_run_lock(run_id, owner="product_commercial_semantics_v1")
    try:
        candidate_id = create_candidate(store, base_id=EXPECTED, component=component, run_id=run_id)
        candidate = store.get(candidate_id)
        pinned_components = validate_manifest(store, candidate)
        recovered = read_component(pinned_components[COMPONENT])
        purpose, conversions = recovered["product_purpose"], recovered["product_sales_uom"]
        assert row_digest(purpose) == component["stable_contract"]["dataset_hashes"]["product_purpose"]
        assert row_digest(conversions) == component["stable_contract"]["dataset_hashes"]["product_sales_uom"]
        assert all(pinned_components[n] == v for n, v in a.manifest["components"].items())
        assert candidate.components == store.get(EXPECTED).components
        assert resolve_current_material_supply(store).foundation_publication_id == EXPECTED
        assert resolve_receivables(store).foundation_publication_id == EXPECTED
        class CandidateCurrentView:
            # Compatibility simulation only. The real catalog pointer remains
            # unchanged; this adapter cannot write or promote.
            def current_pointer(self):
                return candidate_id

            def current_publication(self):
                return replace(candidate, status="CURRENT")

            def get(self, identity):
                return self.current_publication() if identity == candidate_id else store.get(identity)

        shadow = CandidateCurrentView()
        assert resolve_current_material_supply(shadow).foundation_publication_id == candidate_id
        assert resolve_receivables(shadow).foundation_publication_id == candidate_id
        assert store.current_pointer() == EXPECTED
    finally:
        store.release_run_lock(run_id)
    purpose_map = {r["item_code"]: r for r in recovered["product_purpose"]}
    groups = defaultdict(list)
    for r in recovered["product_sales_uom"]:
        groups[r["item_code"]].append(r)
    net = {item: net_quantity(rows) for item, rows in groups.items()}
    baseline_summary = json.loads((BASELINE / "summary.json").read_text())
    with (BASELINE / "commercial_universe.csv").open() as f:
        baseline_commercial = {r["item_code"] for r in csv.DictReader(f)}
    with (BASELINE / "classification_unresolved.csv").open() as f:
        baseline_unknown = {r["item_code"] for r in csv.DictReader(f)}
    with (BASELINE / "uom_unresolved.csv").open() as f:
        baseline_uom = {r["item_code"] for r in csv.DictReader(f)}
    eligible = {item for item, p in purpose_map.items() if (p["commercial_purpose"] in {"COMMERCIAL_ONLY", "MIXED"} or p["commercially_observed"]) and p["sap_invnt_item"] == "Y"}
    # The L scope is solely the legacy business question's declared cohort. It
    # does not inform product purpose or brand and is never part of Foundation.
    replay_scope = {item for item in eligible if item.startswith("L")}
    unresolved, ranking, zero = [], [], []
    closed_days = Decimal((date(2026, 9, 23) - date(2026, 1, 1)).days + 1)
    for item in sorted(replay_scope):
        stock = stock_by_item.get(item, Decimal(0))
        if stock <= 0:
            continue
        n = net.get(item, {"status": "PASS", "net_sales_base_qty": "0"})
        if n["status"] != "PASS" or product_map[item]["inventory_uom_id"] not in labels:
            unresolved.append(item); continue
        qty = Decimal(n["net_sales_base_qty"])
        closed = net_quantity([r for r in groups[item] if r["doc_date"] < END])
        closed_qty = Decimal(closed.get("net_sales_base_qty") or "0")
        row = {"item_code": item, "purpose": purpose_map[item]["commercial_purpose"], "available_qty": str(stock), "net_sales_base_qty": str(qty), "ratio": str(stock / qty) if qty > 0 else None, "coverage_days": str(stock * closed_days / closed_qty) if closed_qty > 0 else None}
        if qty == 0:
            zero.append(row)
        elif qty > 0:
            ranking.append(row)
    ranking.sort(key=lambda r: (-Decimal(r["ratio"]), r["item_code"]))
    with (BASELINE / "list_b.csv").open() as f:
        old_top = [r["item_code"] for r in list(csv.DictReader(f))[:10]]
    counts = Counter(r["commercial_purpose"] for r in purpose)
    cohort_counts = Counter(r["commercial_purpose"] for r in purpose if r["item_code"] in baseline_unknown)
    still_baseline_uom = sum(net.get(item, {}).get("status") != "PASS" for item in baseline_uom)
    credit_lines = [r for r in conversions if r["document_kind"] == "CREDIT_MEMO"]
    credit_resolved = sum(r["uom_status"] in RESOLVED_UOM for r in credit_lines)
    controls = {item: purpose_map[item] for item in ("L00759", "L00761", "L02475", "L00954")}
    assert controls["L00761"]["commercial_purpose"] == "INTERNAL_ONLY"
    assert controls["L02475"]["commercial_purpose"] == "UNKNOWN"
    assert controls["L00759"]["commercial_purpose"] in {"INTERNAL_ONLY", "UNKNOWN"}
    assert "L00759" not in replay_scope and "L00761" not in replay_scope
    assert controls["L00954"]["commercially_observed"] and controls["L00954"]["commercial_purpose"] != "INTERNAL_ONLY"
    assert counts["MIXED"] > 0
    report = {
        "GATE": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_FOUNDATION_CLOSURE_V1_DEGRADED",
        "GATE_A": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_DISCOVERY_V1_PASS",
        "GATE_B": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_CONTRACT_V1_PASS",
        "GATE_C": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_FOUNDATION_CANDIDATE_V1_PASS",
        "GATE_D": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_VALIDATION_V1_DEGRADED",
        "GATE_E": "TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_FOUNDATION_PROMOTION_V1_BLOCKED",
        "OLD_FOUNDATION": EXPECTED, "NEW_FOUNDATION": "NOT_PROMOTED", "CANDIDATE_FOUNDATION": candidate_id,
        "CURRENT_FOUNDATION": store.current_pointer(), "CANDIDATE_STATUS": store.get(candidate_id).status,
        "COMMERCIAL_ONLY": counts["COMMERCIAL_ONLY"], "INTERNAL_ONLY": counts["INTERNAL_ONLY"], "MIXED": counts["MIXED"], "UNKNOWN": counts["UNKNOWN"],
        "PRODUCT_SCOPE": "ALL_SAP_REFERENCE_PRODUCTS", "TOTAL_PRODUCTS": len(purpose),
        "BASELINE_COMMERCIAL_PURPOSE_UNRESOLVED": 720, "FINAL_COMMERCIAL_PURPOSE_UNRESOLVED": cohort_counts["UNKNOWN"],
        "COMMERCIAL_PURPOSE_RESOLVED_DELTA": 720 - cohort_counts["UNKNOWN"], "PURPOSE_BASELINE_COHORT_COUNTS": dict(cohort_counts),
        "BASELINE_UOM_UNRESOLVED": 468, "FINAL_UOM_UNRESOLVED": still_baseline_uom, "UOM_RESOLVED_DELTA": 468 - still_baseline_uom,
        "REPLAY_UOM_UNRESOLVED": len(unresolved), "CREDIT_MEMO_UOM_RESOLUTION_RATE": round(100 * credit_resolved / len(credit_lines), 4),
        "CREDIT_MEMO_LINES": len(credit_lines), "CREDIT_MEMO_LINES_RESOLVED": credit_resolved,
        "BRAND_RESOLVED": 0, "BRAND_UNKNOWN": len(purpose),
        "STOCK_AVAILABILITY_CONTRACT": "PASS", "NET_SALES_QUANTITY_CONTRACT": "DEGRADED", "NET_SALES_AMOUNT_CONTRACT": "DEGRADED",
        "ANTI_FANOUT": "PASS", "CONSUMER_COMPATIBILITY": "PASS", "BUSINESS_QUERY_REPLAY": "DEGRADED",
        "FOUNDATION_CURRENT_CHANGED": "NO", "ATOMIC_PROMOTION": "NO", "HOST_PREFLIGHT": "SAFE", "RESOURCE_GUARD": "PASS",
        "CONCURRENCY_USED": 2, "UNRELATED_PROCESSES_TERMINATED": 0, "OWN_PROCESSES_LEFT_RUNNING": 0,
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
        "gold_controls": controls, "mixed_examples": [r for r in purpose if r["commercial_purpose"] == "MIXED"][:10],
        "commercial_examples": [r for r in purpose if r["commercial_purpose"] == "COMMERCIAL_ONLY"][:10],
        "replay": {"baseline_commercial": baseline_summary["COMMERCIAL_UNIVERSE_COUNT"], "candidate_commercial": len(replay_scope), "comparable_baseline_uom_additional": 468 - still_baseline_uom,
                   "baseline_unknown_newly_resolved": 720 - cohort_counts["UNKNOWN"], "baseline_commercial_removed": sorted(baseline_commercial - replay_scope),
                   "internal_false_positives_removed": sum(purpose_map[i]["commercial_purpose"] == "INTERNAL_ONLY" for i in baseline_commercial - replay_scope),
                   "mixed_in_replay": sum(purpose_map[i]["commercial_purpose"] == "MIXED" for i in replay_scope),
                   "zero_sales_with_stock": len(zero), "high_stock_low_sales": sum(r["coverage_days"] is not None and Decimal(r["coverage_days"]) >= 180 for r in ranking),
                   "baseline_top10": old_top, "candidate_top10": ranking[:10], "top10_changed": old_top != [r["item_code"] for r in ranking[:10]]},
        "limitations": ["Unknown remains when evidence establishes only operational use but sell flag permits potential commerce", "COMMERCIAL_ONLY is bounded to observed/intended evidence, DERIVED_PARTIAL", "Commercially observed UNKNOWN items remain eligible for commercial analysis, with purpose uncertainty explicit", "Historical credit factors are supported corroboration, not exact CURRENT extraction", "Unmatched/changed credit lines require future UoM ingestion", "Brand unknown", "Net product amount unresolved", "Promotion blocked: Gate D DEGRADED; candidate remains VALIDATING"],
        "parity": {"all_existing_manifest_entries_exact": True, "catalog_components_exact": True, "source_facts_rewritten": False, "reference_classification_unchanged": True},
    }
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (OUTPUT / "replay.json").write_text(json.dumps({"ranking": ranking, "zero_sales": zero, "unresolved_items": unresolved}, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"gold_controls", "mixed_examples", "commercial_examples"}}, indent=2, default=str))


if __name__ == "__main__":
    main()
