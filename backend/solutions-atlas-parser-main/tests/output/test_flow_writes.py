"""Tests that the v3 bundle structure builder emits per-node writes and
gateway conditions, and no longer flattens write nodes to SCRIPT_TASK."""

from appian_parser.domain.models import ParsedObject
from appian_parser.output.bundle_structure_builder import BundleStructureBuilder
from appian_parser.parsers.write_extractor import RECORD_WRITE_NODE_TYPE


def _pm_with_write_and_gateway() -> ParsedObject:
    nodes = [
        {'node_id': 'n1', 'gui_id': '1', 'node_name': 'Start',
         'node_type_name': 'Start Event', 'node_type': 'start',
         'inputs': [], 'outputs': [], 'gateway_conditions': []},
        {'node_id': 'n2', 'gui_id': '2', 'node_name': 'Decide',
         'node_type_name': 'XOR Gateway', 'node_type': 'xor',
         'inputs': [], 'outputs': [],
         'gateway_conditions': [
             {'target_gui_id': '3', 'label': 'Approved', 'condition': 'pv!ok', 'is_default': False},
             {'target_gui_id': '4', 'label': None, 'condition': None, 'is_default': True},
         ]},
        {'node_id': 'n3', 'gui_id': '3', 'node_name': 'Write Award',
         'node_type_name': 'Write Records', 'node_type': RECORD_WRITE_NODE_TYPE,
         'inputs': [{'input_expression': 'recordType!{u1}AS_GSS_AwardDecision'}],
         'outputs': [], 'gateway_conditions': []},
        {'node_id': 'n4', 'gui_id': '4', 'node_name': 'End',
         'node_type_name': 'End Event', 'node_type': 'end',
         'inputs': [], 'outputs': [], 'gateway_conditions': []},
    ]
    flows = [
        {'from_node_id': 'n1', 'to_node_id': 'n2', 'flow_label': None},
        {'from_node_id': 'n2', 'to_node_id': 'n3', 'flow_label': 'Approved'},
        {'from_node_id': 'n2', 'to_node_id': 'n4', 'flow_label': None},
    ]
    return ParsedObject(uuid='_pm1', name='AwardFlow', object_type='Process Model',
                        data={'nodes': nodes, 'flows': flows}, diff_hash='h')


def _nodes_by_name(graph):
    return {n['name']: n for n in graph['nodes']}


def test_write_node_emits_writes_and_distinct_type():
    pm = _pm_with_write_and_gateway()
    graph = BundleStructureBuilder()._build_flow_graph(pm, {pm.uuid: pm}, {})
    by_name = _nodes_by_name(graph)

    write_node = by_name['Write Award']
    assert write_node['type'] == 'WRITE_RECORDS'  # not flattened to SCRIPT_TASK
    assert 'writes' in write_node
    assert write_node['writes'][0]['record_type_name'] == 'AS_GSS_AwardDecision'
    assert write_node['writes'][0]['mechanism'] == 'RECORD'


def test_gateway_conditions_surfaced_with_resolved_targets():
    pm = _pm_with_write_and_gateway()
    graph = BundleStructureBuilder()._build_flow_graph(pm, {pm.uuid: pm}, {})
    gw = _nodes_by_name(graph)['Decide']

    assert 'gateway_conditions' in gw
    conds = gw['gateway_conditions']
    approved = next(c for c in conds if c['label'] == 'Approved')
    assert approved['condition'] == 'pv!ok'
    assert approved['to'] == 'Write Award'   # target_gui_id '3' resolved to node name
    assert any(c['is_default'] for c in conds)


def test_non_write_nodes_have_no_writes_key():
    pm = _pm_with_write_and_gateway()
    graph = BundleStructureBuilder()._build_flow_graph(pm, {pm.uuid: pm}, {})
    assert 'writes' not in _nodes_by_name(graph)['Start']
