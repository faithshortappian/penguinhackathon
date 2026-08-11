"""Test fixtures for enrichment tests."""

import pytest
from appian_parser.domain.models import ParsedObject
from appian_parser.dependencies.analyzer import Dependency


@pytest.fixture
def sample_parsed_object():
    """Sample parsed object for testing."""
    return ParsedObject(
        uuid='test-uuid-001',
        name='Test Object',
        object_type='Expression Rule',
        data={
            'uuid': 'test-uuid-001',
            'name': 'Test Object',
            'description': 'Test description',
        },
        diff_hash='test-hash',
        source_file='test.xml',
    )


@pytest.fixture
def sample_dependency():
    """Sample dependency for testing."""
    return Dependency(
        source_uuid='test-uuid-001',
        source_name='Source Object',
        source_type='Expression Rule',
        target_uuid='test-uuid-002',
        target_name='Target Object',
        target_type='Constant',
        dependency_type='CALLS',
        reference_context='expression',
        is_resolved=True,
    )


@pytest.fixture
def sample_process_model():
    """Sample process model for testing."""
    return ParsedObject(
        uuid='test-pm-001',
        name='Test Process',
        object_type='Process Model',
        data={
            'uuid': 'test-pm-001',
            'name': 'Test Process',
            'nodes': [
                {'id': 'node1', 'type': 'START_EVENT', 'name': 'Start'},
                {'id': 'node2', 'type': 'USER_INPUT_TASK', 'name': 'User Task'},
                {'id': 'node3', 'type': 'END_EVENT', 'name': 'End'},
            ],
            'flows': [
                {'from': 'node1', 'to': 'node2'},
                {'from': 'node2', 'to': 'node3'},
            ],
        },
        diff_hash='test-hash',
        source_file='test-pm.xml',
    )


@pytest.fixture
def sample_interface():
    """Sample interface for testing."""
    return ParsedObject(
        uuid='test-interface-001',
        name='Test Interface',
        object_type='Interface',
        data={
            'uuid': 'test-interface-001',
            'name': 'Test Interface',
            'expression': 'a!formLayout(contents: {a!textField()})',
        },
        diff_hash='test-hash',
        source_file='test-interface.xml',
    )
