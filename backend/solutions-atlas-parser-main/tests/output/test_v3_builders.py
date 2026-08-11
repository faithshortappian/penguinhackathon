"""Tests for Phase 1 v3 builders."""

import pytest
from appian_parser.domain.models import ParsedObject, BuildArtifacts, MemberEntry, WriteStats
from appian_parser.output.object_file_builder import ObjectFileBuilder, extract_type_specific
from appian_parser.output.code_file_builder import CodeFileBuilder, extract_code
from appian_parser.output.graph_builder import GraphBuilder
from appian_parser.output.orphan_index_builder import OrphanIndexBuilder
from appian_parser.output.bundle_file_builder import BundleFileBuilder
from appian_parser.dependencies.analyzer import Dependency


# ── Fixtures ──────────────────────────────────────────────────────────

def _obj(uuid='_a-001', name='TestRule', obj_type='Expression Rule', **data_overrides):
    data = {'description': 'A test rule', 'inputs': [{'name': 'x', 'type': 'Text'}],
            'output_type': 'Boolean', 'test_cases': [], **data_overrides}
    return ParsedObject(uuid=uuid, name=name, object_type=obj_type, data=data, diff_hash='abc123')


def _dep(src_uuid, src_name, tgt_uuid, tgt_name, dep_type='CALLS',
         src_type='Expression Rule', tgt_type='Expression Rule'):
    return Dependency(
        source_uuid=src_uuid, source_name=src_name, source_type=src_type,
        target_uuid=tgt_uuid, target_name=tgt_name, target_type=tgt_type,
        dependency_type=dep_type, reference_context='sail_code', is_resolved=True,
    )


# ── ObjectFileBuilder ────────────────────────────────────────────────

class TestObjectFileBuilder:
    def test_basic_fields(self):
        obj = _obj()
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set())
        entry = result['_a-001']
        assert entry['uuid'] == '_a-001'
        assert entry['name'] == 'TestRule'
        assert entry['type'] == 'Expression Rule'
        assert entry['description'] == 'A test rule'
        assert entry['diff_hash'] == 'abc123'

    def test_type_specific_expression_rule(self):
        obj = _obj()
        result = extract_type_specific(obj)
        assert 'inputs' in result
        assert 'output_type' in result
        assert result['output_type'] == 'Boolean'

    def test_type_specific_interface(self):
        obj = _obj(obj_type='Interface', parameters=[{'name': 'p1', 'type': 'Text'}])
        result = extract_type_specific(obj)
        assert 'parameters' in result

    def test_type_specific_constant(self):
        obj = _obj(obj_type='Constant', value='hello', value_type='Text', scope='Application')
        result = extract_type_specific(obj)
        assert result['value'] == 'hello'
        assert result['value_type'] == 'Text'

    def test_hub_and_orphan_flags(self):
        obj = _obj()
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, hub_uuids={'_a-001'}, orphan_uuids={'_a-001'})
        assert result['_a-001']['is_hub'] is True
        assert result['_a-001']['is_orphan'] is True

    def test_calls_and_called_by(self):
        obj1 = _obj(uuid='_a-001', name='Caller')
        obj2 = _obj(uuid='_a-002', name='Callee')
        dep = _dep('_a-001', 'Caller', '_a-002', 'Callee')
        builder = ObjectFileBuilder()
        result = builder.build_all([obj1, obj2], [dep], {}, set(), set())
        assert len(result['_a-001']['calls']) == 1
        assert result['_a-001']['calls'][0]['name'] == 'Callee'
        assert len(result['_a-002']['called_by']) == 1
        assert result['_a-002']['called_by'][0]['name'] == 'Caller'
        assert result['_a-001']['outbound_count'] == 1
        assert result['_a-002']['inbound_count'] == 1

    def test_bundle_assignment(self):
        obj = _obj()
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {'_a-001': ['Bundle_A', 'Bundle_B']}, set(), set())
        assert result['_a-001']['bundles'] == ['Bundle_A', 'Bundle_B']

    def test_no_version_history_without_version(self):
        obj = _obj()
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set())
        assert 'version_history' not in result['_a-001']

    def test_version_history_baseline(self):
        obj = _obj()
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set(), version='1.0.0')
        vh = result['_a-001']['version_history']
        assert len(vh) == 1
        assert vh[0]['status'] == 'current'
        assert vh[0]['version'] == '1.0.0'

    def test_version_history_modified(self):
        obj = _obj(diff_hash='new_hash')
        obj.diff_hash = 'new_hash'
        prev = {'_a-001': {'version_history': [
            {'version': '1.0.0', 'status': 'current', 'diff_hash': 'old_hash'},
        ]}}
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set(), version='2.0.0', previous_object_files=prev)
        vh = result['_a-001']['version_history']
        assert len(vh) == 2
        assert vh[0]['status'] == 'current'
        assert vh[0]['version'] == '2.0.0'
        assert vh[1]['status'] == 'modified'
        assert vh[1]['version'] == '1.0.0'

    def test_version_history_daily_update_no_new_entry(self):
        obj = _obj()  # diff_hash='abc123'
        prev = {'_a-001': {'version_history': [
            {'version': '1.0.0', 'status': 'current', 'diff_hash': 'abc123'},
        ]}}
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set(), version='1.0.0', previous_object_files=prev)
        vh = result['_a-001']['version_history']
        assert len(vh) == 1  # no new entry, just replaced current
        assert vh[0]['status'] == 'current'

    def test_missing_description_defaults_empty(self):
        obj = ParsedObject(uuid='_a-001', name='X', object_type='Expression Rule', data={}, diff_hash='h')
        builder = ObjectFileBuilder()
        result = builder.build_all([obj], [], {}, set(), set())
        assert result['_a-001']['description'] == ''


# ── CodeFileBuilder ──────────────────────────────────────────────────

class TestCodeFileBuilder:
    def test_expression_rule_has_code(self):
        obj = _obj(definition='1 + 1')
        builder = CodeFileBuilder()
        result = builder.build_all([obj])
        assert '_a-001' in result
        assert result['_a-001']['sail_code'] == '1 + 1'
        assert result['_a-001']['name'] == 'TestRule'
        assert result['_a-001']['type'] == 'Expression Rule'

    def test_constant_has_no_code(self):
        obj = _obj(obj_type='Constant', value='hello')
        builder = CodeFileBuilder()
        result = builder.build_all([obj])
        assert '_a-001' not in result

    def test_group_has_no_code(self):
        obj = _obj(obj_type='Group')
        builder = CodeFileBuilder()
        result = builder.build_all([obj])
        assert '_a-001' not in result

    def test_interface_has_code(self):
        obj = _obj(obj_type='Interface', sail_code='a!textField()')
        builder = CodeFileBuilder()
        result = builder.build_all([obj])
        assert '_a-001' in result

    def test_process_model_concatenates_nodes(self):
        obj = _obj(obj_type='Process Model', nodes=[
            {'node_name': 'Start', 'form_expression': 'expr1', 'inputs': [], 'outputs': []},
            {'node_name': 'End', 'form_expression': 'expr2', 'inputs': [], 'outputs': []},
        ])
        builder = CodeFileBuilder()
        result = builder.build_all([obj])
        assert '_a-001' in result
        assert 'expr1' in result['_a-001']['sail_code']
        assert 'expr2' in result['_a-001']['sail_code']


# ── GraphBuilder ─────────────────────────────────────────────────────

class TestGraphBuilder:
    def test_basic_graph(self):
        obj1 = _obj(uuid='_a-001', name='A')
        obj2 = _obj(uuid='_a-002', name='B')
        dep = _dep('_a-001', 'A', '_a-002', 'B')
        builder = GraphBuilder()
        graph = builder.build([obj1, obj2], [dep], {'_a-001': ['bundle1']}, set())
        assert graph['_metadata']['node_count'] == 2
        assert graph['_metadata']['edge_count'] == 1
        assert len(graph['nodes']) == 2
        assert len(graph['edges']) == 1

    def test_edge_deduplication(self):
        obj1 = _obj(uuid='_a-001', name='A')
        obj2 = _obj(uuid='_a-002', name='B')
        dep1 = _dep('_a-001', 'A', '_a-002', 'B', dep_type='CALLS')
        dep2 = _dep('_a-001', 'A', '_a-002', 'B', dep_type='CALLS')  # duplicate
        builder = GraphBuilder()
        graph = builder.build([obj1, obj2], [dep1, dep2], {}, set())
        assert graph['_metadata']['edge_count'] == 1

    def test_hub_flag(self):
        obj = _obj(uuid='_a-001', name='Hub')
        builder = GraphBuilder()
        graph = builder.build([obj], [], {}, hub_uuids={'_a-001'})
        assert graph['nodes'][0]['is_hub'] is True

    def test_orphan_flag(self):
        obj = _obj(uuid='_a-001', name='Orphan')
        builder = GraphBuilder()
        graph = builder.build([obj], [], {}, set())  # no bundle assignments
        assert graph['nodes'][0]['is_orphan'] is True

    def test_no_description_in_nodes(self):
        obj = _obj()
        builder = GraphBuilder()
        graph = builder.build([obj], [], {}, set())
        assert 'description' not in graph['nodes'][0]


# ── OrphanIndexBuilder ───────────────────────────────────────────────

class TestOrphanIndexBuilder:
    def test_identifies_orphans(self):
        obj1 = _obj(uuid='_a-001', name='Bundled')
        obj2 = _obj(uuid='_a-002', name='Orphan')
        builder = OrphanIndexBuilder()
        result = builder.build([obj1, obj2], {'_a-001': ['bundle1']})
        assert result['_metadata']['total_orphans'] == 1
        assert result['orphans'][0]['name'] == 'Orphan'

    def test_by_type_counts(self):
        objs = [
            _obj(uuid='_a-001', name='O1', obj_type='Expression Rule'),
            _obj(uuid='_a-002', name='O2', obj_type='Expression Rule'),
            _obj(uuid='_a-003', name='O3', obj_type='Interface'),
        ]
        builder = OrphanIndexBuilder()
        result = builder.build(objs, {})
        assert result['by_type']['Expression Rule'] == 2
        assert result['by_type']['Interface'] == 1

    def test_no_orphans(self):
        obj = _obj()
        builder = OrphanIndexBuilder()
        result = builder.build([obj], {'_a-001': ['b1']})
        assert result['_metadata']['total_orphans'] == 0
        assert result['orphans'] == []
