from modules.telchi.datalake.material_supply import (
    BomLine,
    ConversionStatus,
    Density,
    calculate_coverage,
    convert,
    coverage_band,
    expand_bom,
    supply_risk,
)


def test_positive_same_dimension_conversions():
    assert convert(2, "KG", "G").target_value == 2000
    assert convert(500, "G", "KG").target_value == 0.5
    assert convert(2, "L", "ML").target_value == 2000
    assert convert(500, "ML", "L").target_value == 0.5
    assert convert(3, "COUNT", "UNIT").target_value == 3


def test_cross_dimension_requires_validated_density():
    blocked = convert(1, "KG", "L")
    assert blocked.status is ConversionStatus.DENSITY_REQUIRED
    assert blocked.target_value is None
    valid = convert(2, "KG", "L", density=Density(0.8, True, "TELCHI_SPEC:fixture"))
    assert valid.status is ConversionStatus.DENSITY_VALIDATED
    assert valid.target_value == 2.5
    assert calculate_coverage(10, "KG", 2, "L").days is None
    assert calculate_coverage(10, "KG", 2, "L", density=Density(0.8, True)).days == 6.25


def test_unknown_uom_fails_closed_and_trementina_fixture():
    assert convert(1, "MYSTERY", "KG").status is ConversionStatus.UNKNOWN_UOM
    assert convert(float("inf"), "KG", "G").status is ConversionStatus.INVALID_VALUE
    result = calculate_coverage(100, "KG", 10, "L")
    assert result.days is None
    assert result.status == "DENSITY_REQUIRED"
    assert result.basis == "UNRESOLVED"


def test_bom_multilevel_factor_cycle_guard_and_diamond_paths():
    lines = [
        BomLine("FINAL", "MID_A", 2, "UNIT", 1, "UNIT", "F-A"),
        BomLine("FINAL", "MID_B", 3, "UNIT", 1, "UNIT", "F-B"),
        BomLine("MID_A", "RAW", 4, "KG", 1, "UNIT", "A-R"),
        BomLine("MID_B", "RAW", 5, "KG", 1, "UNIT", "B-R"),
        BomLine("RAW", "FINAL", 1, "UNIT", 1, "KG", "R-F-CYCLE"),
    ]
    result = expand_bom("FINAL", lines)
    raw_paths = [p for p in result.paths if p.component_item == "RAW"]
    assert len(raw_paths) == 2
    assert sorted(p.factor for p in raw_paths) == [8, 15]
    assert result.cycles
    assert not result.truncated


def test_bom_depth_and_path_limits_are_bounded():
    lines = [BomLine("A", "B", 1, "UNIT", 1, "UNIT", "1"),
             BomLine("B", "C", 1, "UNIT", 1, "UNIT", "2")]
    assert expand_bom("A", lines, max_depth=1).truncated
    assert expand_bom("A", lines, max_paths=1).truncated


def test_coverage_bands_and_supply_risk_are_explicit():
    assert [coverage_band(x) for x in (0, 10, 20, 40, 60)] == [
        "QUIEBRE", "CRITICO", "ALTO", "ATENCION", "OK"
    ]
    assert supply_risk(20, 40, open_po_usable_before_stockout=False) == "RISK"
    assert supply_risk(50, 10, open_po_usable_before_stockout=False) == "MANAGEABLE"
    assert supply_risk(20, 40, open_po_usable_before_stockout=True) == "MITIGATED"
    assert supply_risk(20, None) == "UNKNOWN"
    assert supply_risk(20, 40, open_po_usable_before_stockout=None) == "INBOUND_DESTINATION_UNCERTAIN"
