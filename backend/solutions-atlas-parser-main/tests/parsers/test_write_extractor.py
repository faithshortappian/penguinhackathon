"""Tests for the shared write_extractor (RECORD + CDT write extraction)."""

from appian_parser.domain.models import ParsedObject
from appian_parser.parsers.write_extractor import (
    DSE_WRITE_NODE_TYPES,
    RECORD_WRITE_NODE_TYPE,
    build_cdt_table_index,
    extract_node_writes,
    extract_record_writes,
    extract_cdt_writes,
)


class TestRecordWrites:
    def test_extracts_record_type_identity_from_input(self):
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [{'input_expression': 'recordType!{ddf6d201-aaaa}AS_GSS_AwardDecision'}],
            'outputs': [],
        }
        writes = extract_record_writes(node)
        assert len(writes) == 1
        w = writes[0]
        assert w['mechanism'] == 'RECORD'
        assert w['record_type_uuid'] == 'ddf6d201-aaaa'
        assert w['record_type_name'] == 'AS_GSS_AwardDecision'
        assert w['operation'] == 'WRITE'
        assert w['via'] == RECORD_WRITE_NODE_TYPE
        assert 'table' not in w  # resolved downstream via record_type_map.json

    def test_extracts_from_output_save_into(self):
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [],
            'outputs': [{'save_into': 'recordType!{uuid-2}AS_GSS_Request'}],
        }
        writes = extract_record_writes(node)
        assert writes[0]['record_type_name'] == 'AS_GSS_Request'

    def test_dedups_repeated_record_type(self):
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [
                {'input_expression': 'recordType!{u1}A'},
                {'input_expression': 'recordType!{u1}A'},
            ],
            'outputs': [],
        }
        assert len(extract_record_writes(node)) == 1

    def test_non_write_node_returns_empty(self):
        node = {'node_type': 'internal.database601', 'inputs': [
            {'input_expression': 'recordType!{u1}A'}]}
        assert extract_record_writes(node) == []
        assert extract_node_writes(node) == []

    def test_extracts_record_type_from_canonical_urn(self):
        # Real Write Records node shape: RecordType input carries a record-type URN
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [
                {'input_name': 'Records', 'input_expression': '=pv!evaluationVendor'},
                {'input_name': 'RecordType',
                 'input_expression': '=#"urn:appian:record-type:v1:b6081510-0d11-4d51-8eba-966610b168db"'},
            ],
            'outputs': [],
        }
        writes = extract_record_writes(node)
        assert len(writes) == 1
        assert writes[0]['record_type_uuid'] == 'b6081510-0d11-4d51-8eba-966610b168db'
        assert writes[0]['mechanism'] == 'RECORD'
        assert 'record_type_name' not in writes[0]  # name resolved downstream

    def test_extracts_multiple_record_types_from_urn_list(self):
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [{'input_name': 'RecordType', 'input_expression':
                        '={#"urn:appian:record-type:v1:9c497e08-f4c6-4fbd-bf14-5638dc226230", '
                        '#"urn:appian:record-type:v1:9a04b944-b726-41f5-9b37-8ec71b6cc370"}'}],
            'outputs': [],
        }
        uuids = {w['record_type_uuid'] for w in extract_record_writes(node)}
        assert uuids == {'9c497e08-f4c6-4fbd-bf14-5638dc226230',
                         '9a04b944-b726-41f5-9b37-8ec71b6cc370'}

    def test_extracts_resolved_name_form(self):
        # The form the reference resolver actually produces in PM node inputs.
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [
                {'input_name': 'Records', 'input_expression': '=pv!evaluationVendor'},
                {'input_name': 'RecordType',
                 'input_expression': '=recordType!AS_GSS_EvaluationVendor_SYNCEDRECORD'},
            ],
            'outputs': [],
        }
        writes = extract_record_writes(node)
        assert len(writes) == 1
        assert writes[0]['record_type_name'] == 'AS_GSS_EvaluationVendor_SYNCEDRECORD'
        assert writes[0]['mechanism'] == 'RECORD'
        assert 'record_type_uuid' not in writes[0]  # uuid resolved downstream

    def test_extracts_multiple_name_form_record_types(self):
        node = {
            'node_type': RECORD_WRITE_NODE_TYPE,
            'inputs': [{'input_name': 'RecordType', 'input_expression':
                        '={recordType!AS_GSS_EvaluationDocument_SYNCEDRECORD, '
                        'recordType!AS_GSS_TMG_Task_SYNCEDRECORD}'}],
            'outputs': [],
        }
        names = {w['record_type_name'] for w in extract_record_writes(node)}
        assert names == {'AS_GSS_EvaluationDocument_SYNCEDRECORD',
                         'AS_GSS_TMG_Task_SYNCEDRECORD'}


class TestCdtWrites:
    def _dse_node(self, cons_name="ISU_MSG_ENT_MESSAGE_TEXT",
                  nt="appian.system.smart-services.write-to-data-store"):
        return {
            'node_type': nt,
            'inputs': [
                {'input_name': 'DataStoreEntity', 'input_expression': f'=cons!{cons_name}'},
                {'input_name': 'messageTextCdt', 'input_expression': '=pv!messageTextCdt'},
            ],
            'outputs': [],
        }

    def test_resolves_full_chain_cons_to_table(self):
        node = self._dse_node()
        writes = extract_cdt_writes(
            node,
            constant_entity_index={'ISU_MSG_ENT_MESSAGE_TEXT': 'ent-uuid-1'},
            entity_cdt_index={'ent-uuid-1': '{urn:isu}ISU_T_MSG_MessageText'},
            cdt_table_index={'{urn:isu}ISU_T_MSG_MessageText': 'ISU_T_MSG_MESSAGE_TEXT'},
        )
        assert len(writes) == 1
        w = writes[0]
        assert w['mechanism'] == 'CDT'
        assert w['data_store_entity'] == 'ISU_MSG_ENT_MESSAGE_TEXT'
        assert w['data_store_entity_uuid'] == 'ent-uuid-1'
        assert w['cdt_type'] == '{urn:isu}ISU_T_MSG_MessageText'
        assert w['table'] == 'ISU_T_MSG_MESSAGE_TEXT'

    def test_degrades_when_chain_unresolved(self):
        # Unknown constant → still emits the entity name, no table
        node = self._dse_node(cons_name='UNKNOWN_DSE')
        writes = extract_cdt_writes(node)
        assert len(writes) == 1
        assert writes[0]['data_store_entity'] == 'UNKNOWN_DSE'
        assert 'table' not in writes[0]
        assert 'cdt_type' not in writes[0]

    def test_dispatch_via_extract_node_writes(self):
        for nt in DSE_WRITE_NODE_TYPES:
            node = self._dse_node(nt=nt)
            writes = extract_node_writes(
                node,
                constant_entity_index={'ISU_MSG_ENT_MESSAGE_TEXT': 'e1'},
                entity_cdt_index={'e1': '{n}C'},
                cdt_table_index={'{n}C': 'C_TBL'},
            )
            assert writes[0]['mechanism'] == 'CDT'
            assert writes[0]['table'] == 'C_TBL'


class TestBuildCdtTableIndex:
    def test_indexes_cdt_objects_with_tables(self):
        objs = [
            ParsedObject(uuid='{urn:a}Eval', name='Eval', object_type='CDT',
                         data={'uuid': '{urn:a}Eval', 'table': 'EVAL_TBL'}, diff_hash='h'),
            ParsedObject(uuid='{urn:a}NoTable', name='NoTable', object_type='CDT',
                         data={'uuid': '{urn:a}NoTable', 'table': None}, diff_hash='h'),
            ParsedObject(uuid='_r1', name='R', object_type='Record Type',
                         data={'uuid': '_r1'}, diff_hash='h'),
        ]
        index = build_cdt_table_index(objs)
        assert index == {'{urn:a}Eval': 'EVAL_TBL'}
