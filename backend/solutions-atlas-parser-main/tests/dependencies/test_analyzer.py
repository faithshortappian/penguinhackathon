"""Tests for DependencyAnalyzer."""

import pytest

from appian_parser.dependencies.analyzer import DependencyAnalyzer
from appian_parser.output.json_dumper import ParsedObject


@pytest.fixture
def analyzer():
    return DependencyAnalyzer()


@pytest.fixture
def objects_with_deps():
    """Objects with known dependency relationships."""
    return [
        ParsedObject(
            uuid='_a-00000001-0000-0000-0000-000000000001_1',
            name='MainInterface',
            object_type='Interface',
            data={
                'uuid': '_a-00000001-0000-0000-0000-000000000001_1',
                'name': 'MainInterface',
                'sail_code': 'rule!HelperRule(cons!MY_CONSTANT)',
            },
        ),
        ParsedObject(
            uuid='_a-00000002-0000-0000-0000-000000000002_2',
            name='HelperRule',
            object_type='Expression Rule',
            data={
                'uuid': '_a-00000002-0000-0000-0000-000000000002_2',
                'name': 'HelperRule',
                'sail_code': 'type!MyCDT()',
            },
        ),
        ParsedObject(
            uuid='_a-00000003-0000-0000-0000-000000000003_3',
            name='MY_CONSTANT',
            object_type='Constant',
            data={
                'uuid': '_a-00000003-0000-0000-0000-000000000003_3',
                'name': 'MY_CONSTANT',
                'value': '42',
            },
        ),
        ParsedObject(
            uuid='_a-00000004-0000-0000-0000-000000000004_4',
            name='MyCDT',
            object_type='CDT',
            data={
                'uuid': '_a-00000004-0000-0000-0000-000000000004_4',
                'name': 'MyCDT',
            },
        ),
    ]


class TestDependencyAnalyzer:
    """Tests for dependency extraction."""

    def test_analyze_returns_dependencies(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        assert len(deps) > 0

    def test_extracts_rule_call(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        rule_deps = [d for d in deps if d.dependency_type == 'CALLS' and d.target_name == 'HelperRule']
        assert len(rule_deps) == 1
        assert rule_deps[0].source_name == 'MainInterface'

    def test_extracts_constant_usage(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        const_deps = [d for d in deps if d.dependency_type == 'USES_CONSTANT']
        assert len(const_deps) == 1
        assert const_deps[0].target_name == 'MY_CONSTANT'

    def test_extracts_cdt_usage(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        cdt_deps = [d for d in deps if d.dependency_type == 'USES_CDT']
        assert len(cdt_deps) == 1
        assert cdt_deps[0].target_name == 'MyCDT'

    def test_no_self_dependencies(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        for d in deps:
            assert d.source_uuid != d.target_uuid

    def test_all_dependencies_resolved(self, analyzer, objects_with_deps):
        deps = analyzer.analyze(objects_with_deps)
        for d in deps:
            assert d.is_resolved

    def test_structural_uuid_fields(self, analyzer):
        """Test that structural UUID fields (e.g., subprocess_uuid) are extracted."""
        objects = [
            ParsedObject(
                uuid='_a-pm-0001-0000-0000-000000000001_1',
                name='MainProcess',
                object_type='Process Model',
                data={
                    'uuid': '_a-pm-0001-0000-0000-000000000001_1',
                    'name': 'MainProcess',
                    'nodes': [
                        {
                            'subprocess_uuid': '_a-pm-0002-0000-0000-000000000002_2',
                            'interface_uuid': '_a-if-0003-0000-0000-000000000003_3',
                        },
                    ],
                },
            ),
            ParsedObject(
                uuid='_a-pm-0002-0000-0000-000000000002_2',
                name='SubProcess',
                object_type='Process Model',
                data={'uuid': '_a-pm-0002-0000-0000-000000000002_2', 'name': 'SubProcess'},
            ),
            ParsedObject(
                uuid='_a-if-0003-0000-0000-000000000003_3',
                name='NodeInterface',
                object_type='Interface',
                data={'uuid': '_a-if-0003-0000-0000-000000000003_3', 'name': 'NodeInterface'},
            ),
        ]
        deps = analyzer.analyze(objects)
        target_names = {d.target_name for d in deps}
        assert 'SubProcess' in target_names
        assert 'NodeInterface' in target_names

    def test_empty_objects_returns_empty(self, analyzer):
        assert analyzer.analyze([]) == []

    def test_dependency_is_frozen(self, analyzer, objects_with_deps):
        """Dependency dataclass should be immutable."""
        deps = analyzer.analyze(objects_with_deps)
        if deps:
            with pytest.raises(AttributeError):
                deps[0].source_name = 'changed'
