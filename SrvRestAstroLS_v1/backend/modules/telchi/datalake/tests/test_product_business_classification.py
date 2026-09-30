from datetime import date

from modules.telchi.datalake.product_business_classification import (
    FRACTIONATED_PRODUCT,
    LAB_FINISHED_PRODUCT,
    OTHER_INPUT,
    PACKAGING,
    RAW_MATERIAL,
    SEMI_FINISHED,
    UNKNOWN,
    ProductFacts,
    PurchaseLine,
    classify_product,
    rank_purchase_frequency,
    unknown_items_can_change_winner,
)


def facts(**changes):
    values = dict(
        item_code="X", item_name="GENERIC", item_group_code=None,
        item_group_name=None, inventory_item=True, sell_item=False,
        purchase_item=True, active=True, is_bom_parent=False,
        is_bom_component=False, is_produced=False,
    )
    values.update(changes)
    return ProductFacts(**values)


def test_bom_leaf_alone_is_not_raw_material():
    result = classify_product(facts(is_bom_component=True))
    assert result.product_business_type == UNKNOWN


def test_combined_input_group_and_bom_component_is_raw_material():
    result = classify_product(facts(item_group_code=131, item_group_name="MATERIAL LABORATORIO", is_bom_component=True))
    assert result.product_business_type == RAW_MATERIAL
    assert result.basis == "COMBINED"
    assert result.status == "VALIDATED"


def test_packaging_group_precedes_bom_leaf_and_production():
    result = classify_product(facts(item_name="FRASCO BOCA ANCHA", item_group_code=130, is_bom_component=True, is_produced=True))
    assert result.product_business_type == PACKAGING
    assert result.confidence == 1.0


def test_name_only_packaging_is_provisional_not_exact():
    result = classify_product(facts(item_name="ETIQUETA ESPECIAL"))
    assert result.product_business_type == PACKAGING
    assert result.status == "PROVISIONAL"
    assert result.name_only
    assert result.confidence < 1.0


def test_fractionated_uses_explicit_group_not_name():
    result = classify_product(facts(item_name="ACEITE", item_group_code=127, item_group_name="FRACCIONADO x L.", sell_item=True))
    assert result.product_business_type == FRACTIONATED_PRODUCT
    assert result.basis == "ITEM_GROUP"


def test_bulk_fractionated_group_bom_input_is_raw_not_commercial_fraction():
    result = classify_product(facts(item_name="AZUFRE", item_group_code=126, item_group_name="FRACCIONADO x Kg.", sell_item=True, is_bom_component=True))
    assert result.product_business_type == RAW_MATERIAL
    assert result.basis == "COMBINED"


def test_produced_sale_and_intermediate_are_distinct():
    assert classify_product(facts(is_produced=True, sell_item=True)).product_business_type == LAB_FINISHED_PRODUCT
    assert classify_product(facts(is_bom_parent=True, sell_item=False)).product_business_type == SEMI_FINISHED


def test_residual_input_is_not_raw_material():
    result = classify_product(facts(item_group_code=129, item_group_name="INSUMO"))
    assert result.product_business_type == OTHER_INPUT


def line(doc, card="C1", item="R1", category=RAW_MATERIAL, kind="SALES", day=1):
    return PurchaseLine("SAP", kind, doc, card, date(2026, 1, day), item, category)


def test_frequency_counts_distinct_documents_not_lines_and_groups_by_cardcode():
    ranked = rank_purchase_frequency([line("1"), line("1", item="R2"), line("2"), line("3", card="C2")])
    assert ranked[0] == {"rank": 1, "card_code": "C1", "purchase_documents": 2, "purchase_days": 1, "distinct_raw_material_skus": 2}
    assert ranked[1]["card_code"] == "C2"


def test_credit_memos_and_non_raw_categories_do_not_add_purchase_occasions():
    ranked = rank_purchase_frequency([
        line("1"), line("CM1", kind="CREDIT_MEMO"),
        line("2", category=FRACTIONATED_PRODUCT), line("3", category=PACKAGING),
        line("4", category=UNKNOWN),
    ])
    assert ranked[0]["purchase_documents"] == 1


def test_ties_share_rank_and_order_is_deterministic():
    ranked = rank_purchase_frequency([line("1", card="C2"), line("2", card="C1")])
    assert [(r["rank"], r["card_code"]) for r in ranked] == [(1, "C1"), (1, "C2")]


def test_unknown_sensitivity_bound():
    assert unknown_items_can_change_winner({"A": 10, "B": 4}, {"B": 7})
    assert not unknown_items_can_change_winner({"A": 10, "B": 4}, {"B": 5})
