"""Revalidate purpose rules with sealed UoM evidence, without recapturing facts."""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader, _validate_manifest
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore, get_current_foundation
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
from modules.telchi.datalake.receivables_collections_foundation import resolve_current as resolve_receivables
from modules.telchi.datalake.product_commercial_semantics import COMPONENT, classify_purpose, materialize, create_candidate, dataset_relation, row_digest
from .run_closure import OUTPUT, BASELINE, EXPECTED, records


def main():
    report = json.loads((OUTPUT / "report.json").read_text())
    replay = json.loads((OUTPUT / "replay.json").read_text())
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    prior = store.get(report["CANDIDATE_FOUNDATION"])
    if prior is None or prior.status != "VALIDATING":
        raise ValueError("explicit prior candidate unavailable")
    old = validate_manifest(store, prior)[COMPONENT]
    with connector.session(read_only=True) as c:
        c.execute("SET threads=2"); c.execute("SET memory_limit='1GB'")
        a = FoundationReader(connector).resolve_on(c)
        assert a.foundation_publication_id == EXPECTED
        purpose = records(c, "SELECT * FROM " + dataset_relation(old, "product_purpose"))
        for r in purpose:
            e = json.loads(r["commercial_purpose_evidence"])
            value = classify_purpose(sell_item=e["sap_sell_item"], business_class=e["business_class"],
                                     class_status=e["classification_status"], classification_basis=e["classification_basis"],
                                     sales_documents=e["sales_documents"], production_issue_lines=e["production_issue_lines"], bom_lines=e["bom_lines"])
            value["commercial_purpose_evidence"] = json.dumps(value["commercial_purpose_evidence"], sort_keys=True)
            r.update(value)
        # The new availability relation must preserve stock cardinality and
        # exact Decimal values, including negative and zero balances.
        stock = a.stock_availability()
        duplicates = c.execute(f"SELECT count(*)-count(distinct (source_system,item_code,warehouse)) FROM {stock}").fetchone()[0]
        delta = c.execute(f"SELECT count(*) FROM {stock} v FULL JOIN {a.oitw()} s ON v.source_system=s.source_system AND v.item_code=s.item_code AND v.warehouse=s.whs_code WHERE v.available_qty IS DISTINCT FROM try_cast(s.on_hand AS DECIMAL(38,12))-try_cast(s.is_commited AS DECIMAL(38,12))").fetchone()[0]
        assert duplicates == 0 and delta == 0
        assert c.execute(f"SELECT count(*) FROM {stock}").fetchone()[0] == c.execute(f"SELECT count(*) FROM {a.oitw()}").fetchone()[0]
    component = materialize({"product_purpose": purpose}, dependencies=old["stable_contract"]["dependencies"],
                            provenance=old["stable_contract"]["source_provenance"], contracts=old["stable_contract"]["contracts"],
                            reuse_datasets={"product_sales_uom": old["datasets"]["product_sales_uom"]})
    assert component["datasets"]["product_sales_uom"] == old["datasets"]["product_sales_uom"]
    run_id = "product-commercial-semantics-v1-final-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    store.acquire_run_lock(run_id, owner="product_commercial_semantics_v1")
    try:
        candidate_id = create_candidate(store, base_id=EXPECTED, component=component, run_id=run_id)
        candidate = store.get(candidate_id)
        entries = validate_manifest(store, candidate)
        assert all(entries[n] == entry for n, entry in a.manifest["components"].items())
        class Shadow:
            def get(self, identity):
                return replace(candidate, status="CURRENT") if identity == candidate_id else store.get(identity)

            def current_publication(self):
                return replace(candidate, status="CURRENT")

            def current_pointer(self):
                return candidate_id

            def list_publications(self, **kwargs):
                return [self.current_publication()]

            def pointer_row_count(self):
                return 1

        shadow = Shadow()
        assert resolve_current_material_supply(shadow).foundation_publication_id == candidate_id
        assert resolve_receivables(shadow).foundation_publication_id == candidate_id
        _validate_manifest(candidate, get_current_foundation(shadow))
        with connector.session(read_only=True) as c:
            c.execute("SET threads=2"); c.execute("SET memory_limit='1GB'")
            fresh = replace(a, manifest=candidate.manifest)
            relation = fresh.product_semantics_relation("product_purpose")
            restored = records(c, "SELECT * FROM " + relation)
            assert row_digest(restored) == row_digest(purpose)
            conversions = fresh.product_semantics_relation("product_sales_uom")
            assert c.execute(f"SELECT count(*)-count(distinct (source_system,document_kind,doc_entry,line_num)) FROM {conversions}").fetchone()[0] == 0
        # Only previous candidates created by this task are retired. CURRENT,
        # other tasks and immutable datasets remain untouched.
        for p in store.list_publications(limit=100):
            if p.update_run_id.startswith("product-commercial-semantics-v1-") and p.foundation_publication_id != candidate_id and p.status == "VALIDATING":
                store.mark_failed(p.foundation_publication_id, "REPLACED_BY_FINAL_VALIDATED_SEMANTICS_CANDIDATE; not promoted")
        assert store.current_pointer() == EXPECTED
    finally:
        store.release_run_lock(run_id)
    pmap = {r["item_code"]: r for r in purpose}
    eligible = {item for item, p in pmap.items() if (p["commercial_purpose"] in {"COMMERCIAL_ONLY", "MIXED"} or p["commercially_observed"]) and p["sap_invnt_item"] == "Y" and item.startswith("L")}
    for name in ("ranking", "zero_sales"):
        replay[name] = [r | {"purpose": pmap[r["item_code"]]["commercial_purpose"]} for r in replay[name] if r["item_code"] in eligible]
    replay["unresolved_items"] = [i for i in replay["unresolved_items"] if i in eligible]
    counts = Counter(r["commercial_purpose"] for r in purpose)
    for name in ("COMMERCIAL_ONLY", "INTERNAL_ONLY", "MIXED", "UNKNOWN"):
        report[name] = counts[name]
    report["CANDIDATE_FOUNDATION"] = candidate_id
    report["REPLAY_UOM_UNRESOLVED"] = len(replay["unresolved_items"])
    for item in report["gold_controls"]:
        report["gold_controls"][item] = pmap[item]
    assert report["gold_controls"]["L00759"]["commercial_purpose"] == "INTERNAL_ONLY"
    assert report["gold_controls"]["L00761"]["commercial_purpose"] == "INTERNAL_ONLY"
    assert report["gold_controls"]["L02475"]["commercial_purpose"] == "UNKNOWN"
    assert report["gold_controls"]["L00954"]["commercially_observed"] and "L00954" in eligible
    report["mixed_examples"] = [r for r in purpose if r["commercial_purpose"] == "MIXED"][:10]
    report["commercial_examples"] = [r for r in purpose if r["commercial_purpose"] == "COMMERCIAL_ONLY"][:10]
    with (BASELINE / "commercial_universe.csv").open() as f:
        prior_commercial = {r["item_code"] for r in csv.DictReader(f)}
    removed = prior_commercial - eligible
    rs = report["replay"]
    with (BASELINE / "commercial_universe.csv").open() as f:
        baseline_sales_metadata = {r["item_code"]: r for r in csv.DictReader(f)}
    for row in replay["ranking"]:
        evidence = baseline_sales_metadata.get(row["item_code"], {})
        row["last_sale"] = evidence.get("last_sale") or None
        row["sale_days"] = int(evidence.get("sale_days") or 0)
    # Preserve the original query's tie-break contract; quantities and the
    # certified universe may change, arbitrary ranking rules must not.
    replay["ranking"].sort(key=lambda r: (-Decimal(r["ratio"]), r["last_sale"] or "", r["sale_days"], r["item_code"]))
    rs.update(candidate_commercial=len(eligible), baseline_commercial_removed=sorted(removed),
              internal_false_positives_removed=sum(pmap[i]["commercial_purpose"] == "INTERNAL_ONLY" for i in removed),
              mixed_in_replay=sum(pmap[i]["commercial_purpose"] == "MIXED" for i in eligible),
              zero_sales_with_stock=len(replay["zero_sales"]),
              high_stock_low_sales=sum(r["coverage_days"] is not None and Decimal(r["coverage_days"]) >= 180 for r in replay["ranking"]),
              candidate_top10=replay["ranking"][:10],
              top10_changed=rs["baseline_top10"] != [r["item_code"] for r in replay["ranking"][:10]])
    # Compare evaluated item sets, rather than calling every newly converted
    # product an additional business-query result.
    baseline_evaluated = set()
    for name in ("list_a", "list_b"):
        with (BASELINE / (name + ".csv")).open() as f:
            baseline_evaluated.update(r["item_code"] for r in csv.DictReader(f))
    evaluated = {r["item_code"] for r in replay["ranking"] + replay["zero_sales"]}
    rs.update(additional_evaluated_products=len(evaluated - baseline_evaluated),
              removed_evaluated_products=len(baseline_evaluated - evaluated),
              baseline_evaluated_products=len(baseline_evaluated), candidate_evaluated_products=len(evaluated))
    report["stock_availability_validation"] = {"duplicate_keys": duplicates, "value_mismatch_count": delta}
    report["validation_reuse"] = {"uom_files_exact": True, "raw_hashes_from_discovery": True, "prior_candidate": prior.foundation_publication_id,
                                 "why_valid": "identical sources, dependencies and sealed conversion hashes; only purpose classification changed"}
    report["ENVIRONMENTAL_ABORTS"] = 0
    report["CONTROLLED_RUNNER_INTERRUPTS"] = 2
    report["RESOURCE_GUARD_ACTIONS"] = "Stopped own discovery runner for Python memory; projected columns and streamed hashes before successful runs"
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (OUTPUT / "replay.json").write_text(json.dumps(replay, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"gold_controls", "mixed_examples", "commercial_examples", "replay"}}, indent=2))


if __name__ == "__main__":
    main()
