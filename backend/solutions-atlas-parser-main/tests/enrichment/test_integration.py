"""Integration test for enrichment with realistic data."""

import pytest
from appian_parser.domain.models import ParsedObject
from appian_parser.dependencies.analyzer import Dependency
from appian_parser.enrichment import Enricher


def test_enrichment_end_to_end():
    """Test complete enrichment flow with realistic data."""
    
    # Create realistic test data
    interface = ParsedObject(
        uuid='interface-001',
        name='Employee Dashboard',
        object_type='Interface',
        data={
            'uuid': 'interface-001',
            'name': 'Employee Dashboard',
            'expression': '''
                a!formLayout(
                    contents: {
                        a!chartField(data: ...),
                        a!chartField(data: ...),
                        a!gridField(data: a!queryRecordType(...))
                    }
                )
            '''
        },
        diff_hash='hash1',
        source_file='interface.xml'
    )
    
    process_model = ParsedObject(
        uuid='pm-001',
        name='Employee Onboarding',
        object_type='Process Model',
        data={
            'uuid': 'pm-001',
            'name': 'Employee Onboarding',
            'nodes': [
                {'id': 'start', 'type': 'START_EVENT', 'name': 'Start'},
                {'id': 'gateway', 'type': 'XOR_GATEWAY', 'name': 'Approved?'},
                {'id': 'approve', 'type': 'USER_INPUT_TASK', 'name': 'Approve Request'},
                {'id': 'notify', 'type': 'INTEGRATION', 'name': 'Send Email', 'integration_name': 'Email Service'},
                {'id': 'end', 'type': 'END_EVENT', 'name': 'End'},
            ],
            'flows': [
                {'from': 'start', 'to': 'approve'},
                {'from': 'approve', 'to': 'gateway'},
                {'from': 'gateway', 'to': 'notify', 'condition': 'approved'},
                {'from': 'gateway', 'to': 'end', 'condition': 'rejected'},
                {'from': 'notify', 'to': 'end'},
            ],
            'complexity_score': 15.0
        },
        diff_hash='hash2',
        source_file='pm.xml'
    )
    
    rule = ParsedObject(
        uuid='rule-001',
        name='Calculate Salary',
        object_type='Expression Rule',
        data={
            'uuid': 'rule-001',
            'name': 'Calculate Salary',
        },
        diff_hash='hash3',
        source_file='rule.xml'
    )
    
    constant = ParsedObject(
        uuid='const-001',
        name='TAX_RATE',
        object_type='Constant',
        data={
            'uuid': 'const-001',
            'name': 'TAX_RATE',
            'value': '0.25'
        },
        diff_hash='hash4',
        source_file='const.xml'
    )
    
    # Create dependencies
    deps = [
        Dependency(
            source_uuid='interface-001',
            source_name='Employee Dashboard',
            source_type='Interface',
            target_uuid='rule-001',
            target_name='Calculate Salary',
            target_type='Expression Rule',
            dependency_type='CALLS',
            reference_context='expression',
            is_resolved=True
        ),
        Dependency(
            source_uuid='rule-001',
            source_name='Calculate Salary',
            source_type='Expression Rule',
            target_uuid='const-001',
            target_name='TAX_RATE',
            target_type='Constant',
            dependency_type='USES',
            reference_context='expression',
            is_resolved=True
        ),
    ]
    
    # Run enrichment
    enricher = Enricher()
    result = enricher.enrich_all([interface, process_model, rule, constant], deps)
    
    # Verify results
    assert 'object_enrichments' in result
    assert 'depths' in result
    
    # Check depths
    depths = result['depths']
    assert depths['interface-001'] == 0  # Entry point
    assert depths['rule-001'] == 1       # Called by interface
    assert depths['const-001'] == 2      # Called by rule
    
    # Check object enrichments
    enrichments = result['object_enrichments']
    assert len(enrichments) == 4
    
    # Find interface enrichment
    interface_enrich = next(e for e in enrichments if e['uuid'] == 'interface-001')
    assert 'dashboard' in interface_enrich['tags']  # Has charts, read-only
    
    # Test bundle enrichment
    bundle = enricher.enrich_bundle([process_model], deps)
    
    assert bundle.bundle_id == 'pm-001'
    assert 'conditional_workflow' in bundle.tags  # Has XOR gateway
    assert bundle.statistics.total_objects == 1
    assert bundle.statistics.total_nodes == 5
    assert bundle.statistics.integration_count == 1
    assert bundle.enriched_flow is not None
    
    # Check typed edges
    edges = bundle.enriched_flow.edges
    assert len(edges) == 5
    
    # Find conditional edge
    conditional_edge = next(e for e in edges if e.edge_type == 'conditional')
    assert conditional_edge.metadata['gateway_type'] == 'XOR_GATEWAY'
    assert conditional_edge.metadata['condition'] in ['approved', 'rejected']
    
    # Check critical paths
    paths = bundle.enriched_flow.critical_paths
    assert len(paths.longest_path) > 0
    assert len(paths.most_nodes_path) > 0
    
    print("✓ End-to-end enrichment test passed!")
    print(f"  - Depths calculated: {len(depths)}")
    print(f"  - Objects enriched: {len(enrichments)}")
    print(f"  - Bundle tags: {bundle.tags}")
    print(f"  - Typed edges: {len(edges)}")
    print(f"  - Critical path length: {len(paths.longest_path)}")


if __name__ == '__main__':
    test_enrichment_end_to_end()
