"""Tests for DependencyDepthCalculator class."""

import pytest
from appian_parser.enrichment.depth_calculator import DependencyDepthCalculator
from appian_parser.domain.models import ParsedObject
from appian_parser.dependencies.analyzer import Dependency


class TestDependencyDepthCalculator:
    """Tests for DependencyDepthCalculator class."""
    
    def test_initialization(self):
        """Test calculator can be initialized."""
        obj = ParsedObject(
            uuid='test-1',
            name='Test',
            object_type='Interface',
            data={},
            diff_hash='hash',
            source_file='test.xml'
        )
        calc = DependencyDepthCalculator([obj], [])
        assert calc is not None
    
    def test_calculate_depths_single_object(self):
        """Test depth calculation for single object."""
        obj = ParsedObject(
            uuid='test-1',
            name='Test Interface',
            object_type='Interface',
            data={},
            diff_hash='hash',
            source_file='test.xml'
        )
        
        calc = DependencyDepthCalculator([obj], [])
        depths = calc.calculate_depths()
        
        assert 'test-1' in depths
        assert depths['test-1'] == 0  # Entry point
    
    def test_calculate_depths_chain(self):
        """Test depth calculation for dependency chain."""
        obj1 = ParsedObject(
            uuid='interface-1',
            name='Interface',
            object_type='Interface',
            data={},
            diff_hash='hash',
            source_file='test.xml'
        )
        obj2 = ParsedObject(
            uuid='rule-1',
            name='Rule',
            object_type='Expression Rule',
            data={},
            diff_hash='hash',
            source_file='test.xml'
        )
        obj3 = ParsedObject(
            uuid='constant-1',
            name='Constant',
            object_type='Constant',
            data={},
            diff_hash='hash',
            source_file='test.xml'
        )
        
        dep1 = Dependency(
            source_uuid='interface-1',
            source_name='Interface',
            source_type='Interface',
            target_uuid='rule-1',
            target_name='Rule',
            target_type='Expression Rule',
            dependency_type='CALLS',
            reference_context='expression',
            is_resolved=True
        )
        dep2 = Dependency(
            source_uuid='rule-1',
            source_name='Rule',
            source_type='Expression Rule',
            target_uuid='constant-1',
            target_name='Constant',
            target_type='Constant',
            dependency_type='CALLS',
            reference_context='expression',
            is_resolved=True
        )
        
        calc = DependencyDepthCalculator([obj1, obj2, obj3], [dep1, dep2])
        depths = calc.calculate_depths()
        
        assert depths['interface-1'] == 0
        assert depths['rule-1'] == 1
        assert depths['constant-1'] == 2
