"""Semantic boundaries and exact candidate isolation, without SAP services."""
from decimal import Decimal
import json
from pathlib import Path

import pytest

from modules.telchi.datalake.product_commercial_semantics import (
    available_stock, classify_purpose, convert_quantity, net_quantity,
    materialize, read_component, dataset_relation, row_digest,
)


def classify(**overrides):
    args = dict(sell_item="Y", business_class="RAW_MATERIAL", class_status="VALIDATED",
                classification_basis="SOURCE_NATIVE", sales_documents=0,
                production_issue_lines=0, bom_lines=0)
    return classify_purpose(**(args | overrides))


@pytest.mark.parametrize("args,expected", [
    ({}, "UNKNOWN"),
    ({"production_issue_lines": 3}, "UNKNOWN"),
    ({"sales_documents": 2, "production_issue_lines": 3}, "MIXED"),
    ({"sales_documents": 1, "production_issue_lines": 3}, "UNKNOWN"),
    ({"sell_item": "N", "production_issue_lines": 3}, "INTERNAL_ONLY"),
    ({"sell_item": "N"}, "UNKNOWN"),
    ({"bom_lines": 8}, "UNKNOWN"),
    ({"sell_item": "N", "bom_lines": 8, "business_class": "PACKAGING"}, "INTERNAL_ONLY"),
    ({"sales_documents": 2, "business_class": "PACKAGING"}, "COMMERCIAL_ONLY"),
    ({"sales_documents": 2, "business_class": "PACKAGING", "production_issue_lines": 2}, "MIXED"),
    ({"sales_documents": 2, "bom_lines": 8}, "UNKNOWN"),
    ({"sales_documents": 1, "business_class": "LAB_FINISHED_PRODUCT"}, "COMMERCIAL_ONLY"),
    ({"sales_documents": 1, "business_class": "LAB_FINISHED_PRODUCT", "classification_basis": "NAME_BASED"}, "UNKNOWN"),
    ({"sales_documents": 0, "business_class": "LAB_FINISHED_PRODUCT", "production_issue_lines": 2}, "UNKNOWN"),
])
def test_purpose_positive_and_contrary_evidence(args, expected):
    result = classify(**args)
    assert result["commercial_purpose"] == expected
    assert result["commercial_purpose_evidence"]["sales_documents"] == args.get("sales_documents", 0)
    assert result["commercial_purpose_provenance"] != "SOURCE_NATIVE"


def test_non_sellable_flag_does_not_erase_real_mixed_usage():
    result = classify(sell_item="N", sales_documents=2, production_issue_lines=2)
    assert result["commercial_purpose"] == "MIXED"
    assert result["commercial_purpose_confidence"] == "HIGH"


@pytest.mark.parametrize("proof,state", [("EXACT_LINEAGE", "UOM_RESOLVED_EXACT"), ("MATCHED_HISTORICAL_SOURCE", "UOM_RESOLVED_SUPPORTED"), ("BASE_INVOICE_LINK", "UOM_UNRESOLVED"), (None, "UOM_UNRESOLVED")])
def test_source_invoice_and_credit_conversion(proof, state):
    result = convert_quantity("2.5", inventory_uom_id="item-uom", source_uom="PACK", factor="12", proof=proof)
    assert result["uom_status"] == state
    assert result["base_qty"] == ("30.0" if state.startswith("UOM_RESOLVED") else None)


@pytest.mark.parametrize("factor", [None, "0", "-1", "NaN", "Infinity", "bad"])
def test_invalid_conversion_never_guesses(factor):
    assert convert_quantity("3", inventory_uom_id="u", source_uom="KG", factor=factor, proof="EXACT_LINEAGE")["base_qty"] is None


def test_incompatible_mass_volume_without_density():
    r = convert_quantity("3", inventory_uom_id="LT", source_uom="KG", factor=None, proof=None, incompatible=True)
    assert r["uom_status"] == "UOM_INCOMPATIBLE"
    assert r["base_qty"] is None


def line(kind, doc, qty, uom="KG", status="UOM_RESOLVED_EXACT"):
    return dict(source_system="SAP_HANA", item_code="X", inventory_uom_id=uom,
                document_kind=kind, doc_entry=doc, line_num="0", base_qty=qty, uom_status=status)


def test_net_quantity_with_credit_is_exact_decimal():
    result = net_quantity([line("INVOICE", "1", "12.1"), line("CREDIT_MEMO", "2", "2.2")])
    assert result["invoice_base_qty"] == "12.1"
    assert result["credit_memo_base_qty"] == "2.2"
    assert result["net_sales_base_qty"] == "9.9"


def test_one_unresolved_credit_blocks_all_product_quantity():
    assert net_quantity([line("INVOICE", "1", "12"), line("CREDIT_MEMO", "2", None, status="UOM_UNRESOLVED")])["net_sales_base_qty"] is None


def test_units_never_sum():
    assert net_quantity([line("INVOICE", "1", "12"), line("INVOICE", "2", "2", uom="LT")])["status"] == "UOM_INCOMPATIBLE"


def test_fanout_rejected():
    with pytest.raises(ValueError, match="fanout"):
        net_quantity([line("INVOICE", "1", "12"), line("INVOICE", "1", "12")])


def test_stock_available_excludes_inbound_and_keeps_negative():
    assert available_stock("10.5", "3.1") == Decimal("7.4")
    assert available_stock("1", "2") == Decimal("-1")
    assert available_stock("invalid", "0") is None


GOLD = json.loads((Path(__file__).parent / "fixtures/product_commercial_semantics_gold_v1.json").read_text())


@pytest.mark.parametrize("case", GOLD["cases"], ids=lambda c: c["item_code"])
def test_real_foundation_gold(case):
    r = classify_purpose(**case["inputs"])
    assert r["commercial_purpose"] == case["expected_purpose"]
    assert r["commercial_purpose_provenance"] == case["expected_provenance"]
    if case["item_code"] == "L00954":
        assert r["commercially_observed"]
    if case["item_code"] == "L02475":
        assert r["operationally_observed"]
        assert not r["commercially_observed"]


def test_immutable_semantic_roundtrip_and_corruption(tmp_path, monkeypatch):
    import duckdb
    from modules.telchi.datalake import product_commercial_semantics as semantics
    from modules.telchi.runtime.config import DuckDBSafetyProfile

    # The producer's explicit profile does not consume the env temp override.
    # Keep this fixture fully isolated, including DuckDB's spill directory.
    monkeypatch.setattr(semantics, 'DuckDBSafetyProfile',
        lambda **kwargs: DuckDBSafetyProfile(temp_directory=tmp_path / 'duckdb-temp', **kwargs))

    datasets = {"product_purpose": [{"item_code": "A", **classify(sales_documents=2),
                                    "brand_name": "UNKNOWN", "brand_provenance": "UNRESOLVED"}],
                "product_sales_uom": [line("INVOICE", "1", "12")]}
    # Evidence is a serialized contract, not a new collection of native facts.
    datasets["product_purpose"][0]["commercial_purpose_evidence"] = json.dumps(datasets["product_purpose"][0]["commercial_purpose_evidence"], sort_keys=True)
    component = materialize(datasets, dependencies={"foundation_publication_id": "base"},
                            provenance={"source": "sealed"}, contracts={"temporal": {"stock": {"data_as_of": "2026-09-24"}}}, data_root=tmp_path)
    assert read_component(component, data_root=tmp_path) == datasets
    assert materialize(datasets, dependencies={"foundation_publication_id": "base"}, provenance={"source": "sealed"}, contracts={"temporal": {"stock": {"data_as_of": "2026-09-24"}}}, data_root=tmp_path) == component
    db = duckdb.connect(config={"threads": 1})
    try:
        relation = dataset_relation(component, "product_sales_uom", data_root=tmp_path)
        assert db.execute("SELECT count(*) FROM " + relation).fetchone()[0] == 1
    finally:
        db.close()
    path = Path(component["datasets"]["product_sales_uom"]["file_references"][0])
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        dataset_relation(component, "product_sales_uom", data_root=tmp_path)


def test_streamed_hash_equals_existing_canonical_hash():
    from modules.telchi.datalake.raw import digest
    assert row_digest([{"b": None, "a": "á"}, {"d": Decimal("1.2")}]) == digest([{"b": None, "a": "á"}, {"d": Decimal("1.2")}])


def test_conversion_preserves_source_decimal_precision():
    r = convert_quantity("123456789012345678901234567890.123456", inventory_uom_id="u", source_uom="UNIT", factor="2", proof="EXACT_LINEAGE")
    assert r["base_qty"] == "246913578024691357802469135780.246912"
    assert available_stock("123456789012345678901234567890.123456", "0.000001") == Decimal("123456789012345678901234567890.123455")
