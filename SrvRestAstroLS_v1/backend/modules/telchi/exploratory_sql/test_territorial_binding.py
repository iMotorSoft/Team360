from .authorized_foundation import EffectiveScope, ResearchBinding, SourcePolicy, DiscoveredSource
from .contracts import Column


def test_authorized_territorial_binding_exposes_published_crosswalk_relation():
    scope = EffectiveScope('u', 'org', 'w', frozenset({'sales.read'}))
    sources = (
        DiscoveredSource('sales_line', 'sales_line',
                         (Column('whs_code', 'VARCHAR'), Column('line_total', 'DECIMAL(38,6)')),
                         ()),
        DiscoveredSource('warehouse_business_location', 'warehouse_business_location',
                         (Column('warehouse_code', 'VARCHAR'), Column('business_location_code', 'VARCHAR'),
                          Column('mapping_status', 'VARCHAR'), Column('mapping_source', 'VARCHAR')),
                         ()),
    )
    policies = tuple(SourcePolicy(name, 'sales.read', 'org', 'w', None, True)
                     for name in ('sales_line', 'warehouse_business_location'))
    binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope,
                              publication='foundation-current', snapshot=1408,
                              sources=sources, policies=policies, investigation_id='territorial')
    try:
        assert binding.context.catalog.known_relations[0].left_table == 'sales_line'
        assert binding.context.catalog.known_relations[0].left_column == 'whs_code'
        assert binding.context.catalog.known_relations[0].right_table == 'warehouse_business_location'
        assert binding.context.catalog.known_relations[0].right_column == 'warehouse_code'
    finally:
        binding.close()


def test_territorial_crosswalk_is_not_available_without_exact_source_policy():
    scope = EffectiveScope('u', 'org', 'w', frozenset({'sales.read'}))
    sources = (DiscoveredSource('warehouse_business_location', 'cw',
                                (Column('warehouse_code', 'VARCHAR'),), ()),)
    binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope,
                              publication='foundation-current', snapshot=1408,
                              sources=sources,
                              policies=(SourcePolicy('ref_business_locations', 'sales.read',
                                                     'org', 'w', None, True),),
                              investigation_id='territorial-denied')
    try:
        assert not binding.context.catalog.tables
    finally:
        binding.close()
