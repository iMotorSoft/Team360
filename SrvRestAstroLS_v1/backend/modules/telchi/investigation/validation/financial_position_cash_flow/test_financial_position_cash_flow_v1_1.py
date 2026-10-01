from modules.telchi.investigation.validation.financial_position_cash_flow.financial_position_cash_flow_v1_1 import (
    classify_hash_account,
    corrected_component,
    hash_balance_decomposition,
    movement_currency_amount,
    residual_source,
    v1_1_position,
)


def test_hash_with_fc_uses_transaction_currency_not_account_currency():
    row = {"ACCOUNT_CURRENCY": "##", "LC_NET": 696.4, "SC_NET": 100, "FC_NET": 100, "FCCURRENCY": "USD"}
    assert movement_currency_amount(row) == ("USD", 100.0, "JDT1_FC")


def test_hash_without_fc_is_local_movement():
    row = {"ACCOUNT_CURRENCY": "##", "LC_NET": 38, "SC_NET": 5.45, "FC_NET": 0, "FCCURRENCY": None}
    assert movement_currency_amount(row) == ("BS", 38.0, "JDT1_LC_NO_FC")


def test_fixed_usd_revaluation_uses_system_base_when_fc_absent():
    row = {"ACCOUNT_CURRENCY": "USD", "LC_NET": 69.64, "SC_NET": 10, "FC_NET": 0, "FCCURRENCY": None}
    assert movement_currency_amount(row) == ("USD", 10.0, "FIXED_ACCOUNT_SC_NO_FC")


def test_hash_profiles_remain_empirical():
    assert classify_hash_account({"FC_LINES": 0, "LC_ONLY_LINES": 3, "LC_NET": 10, "SC_NET": 1}) == "BS_ONLY_IN_PRACTICE"
    assert classify_hash_account({"FC_LINES": 2, "LC_ONLY_LINES": 0, "FC_MIN": "USD", "FC_MAX": "USD"}) == "USD_ONLY_IN_PRACTICE"
    assert classify_hash_account({"FC_LINES": 2, "LC_ONLY_LINES": 4, "FC_MIN": "USD", "FC_MAX": "USD"}) == "MIXED"


def test_residual_sources_are_object_driven():
    assert residual_source("25", True) == "ODPS"
    assert residual_source("-3", False) == "PERIOD_CLOSE"
    assert residual_source("-2", False) == "PERIOD_OPEN"
    assert residual_source("30", False) == "JE_MANUAL"


def test_card_fee_is_split_from_internal_principal():
    category, internal, other = corrected_component("ODPS", -875.74, 875.74)
    assert category == "BANK_FEE"
    assert internal == 0
    assert other == -875.74


def test_period_carryover_is_not_internal_cash():
    assert corrected_component("PERIOD_CLOSE", -1000, 0) == ("PERIOD_CARRYFORWARD", 0.0, -1000)
    assert corrected_component("PERIOD_OPEN", 1000, 0) == ("PERIOD_CARRYFORWARD", 0.0, 1000)


def test_manual_pair_nets_and_non_pair_stays_adjustment():
    assert corrected_component("JE_MANUAL", 0, 0) == ("INTERNAL_OTHER", 0, 0.0)
    assert corrected_component("JE_MANUAL", -174.5, 0) == ("MANUAL_ADJUSTMENT", 0.0, -174.5)


def test_hash_balance_is_decomposed_without_nominal_sc_conversion():
    v1 = {"treasury": {"positions": [
        {"account": "1111015", "name": "Banco MN", "currency": "##", "classification": "BANK", "balance": 100},
        {"account": "1111016", "name": "BANK OF AMERICA USA", "currency": "##", "classification": "BANK", "balance": 696.4},
    ]}}
    result = hash_balance_decomposition(v1)
    assert result["components_lc_carrying_amount"] == {"BS": 100.0, "SC_ONLY": 696.4}
    assert result["v1_hash_carrying_amount"] == 796.4


def test_position_only_adds_proven_bs_component():
    v1 = {"financial_position": [
        {"currency": "BS", "treasury": 1000, "ar_open": 500, "ap_open": 200, "net_operating": 1300},
        {"currency": "USD", "treasury": 50, "ar_open": 0, "ap_open": 10, "net_operating": 40},
    ]}
    decomposition = {"components_lc_carrying_amount": {"BS": 100, "SC_ONLY": 696.4}}
    result = v1_1_position(v1, decomposition)
    assert result[0]["treasury"] == 1100
    assert result[0]["net_operating"] == 1400
    assert result[-1]["currency"] == "SC_ONLY"
    assert result[-1]["treasury_lc_carrying_amount"] == 696.4
