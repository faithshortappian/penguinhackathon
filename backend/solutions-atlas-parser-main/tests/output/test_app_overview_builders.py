"""Tests for app overview sub-builders: description, domains, capabilities, and name utils."""

import pytest
from appian_parser.domain.models import ParsedObject
from appian_parser.domain.name_utils import (
    humanize_object_name,
    humanize_record_name,
    clean_action_name,
    extract_domain_term,
    collect_page_names,
    join_natural,
)
from appian_parser.output.app_description_builder import derive_description
from appian_parser.output.app_domain_builder import extract_domains
from appian_parser.output.app_capability_builder import extract_capabilities


# ── Helpers ──────────────────────────────────────────────────────────

def _obj(uuid='u1', name='Test', obj_type='Expression Rule', **data_overrides):
    data = {'description': '', **data_overrides}
    return ParsedObject(uuid=uuid, name=name, object_type=obj_type, data=data)


def _app(name='My App', prefix='AS_APP', description=''):
    return _obj(name=name, obj_type='Application',
                prefix=prefix, description=description)


def _record(name):
    return _obj(name=name, obj_type='Record Type')


def _site(name, pages=None):
    return _obj(name=name, obj_type='Site', pages=pages or [])


# ── name_utils ───────────────────────────────────────────────────────

class TestHumanizeObjectName:
    def test_strips_prefix(self):
        assert humanize_object_name('AS_GSS_BL_ValidateCase') == 'validate case'

    def test_camel_case(self):
        assert humanize_object_name('AS_CO_UT_isBlank') == 'is blank'

    def test_no_prefix(self):
        assert humanize_object_name('SimpleName') == 'simple name'


class TestHumanizeRecordName:
    def test_strips_prefix_and_suffix(self):
        assert humanize_record_name('AS_PD_Collection_RecordType') == 'Collection'

    def test_strips_syncedrecord(self):
        assert humanize_record_name('AS_GSS_Vendor_SYNCEDRECORD') == 'Vendor'

    def test_camel_case_split(self):
        assert humanize_record_name('AS_AIDB_AiDocInsights_RecordType') == 'Ai Doc Insights'

    def test_plain_name(self):
        assert humanize_record_name('AS AM Award') == 'AS AM Award'


class TestCleanActionName:
    def test_extracts_bundle_key(self):
        expr = 'rule!AS_GSS_UT_displayDynamicLabel(bundleKey: "btn_ClaimTask")'
        assert clean_action_name(expr) == 'Claim Task'

    def test_strips_lbl_prefix(self):
        expr = 'rule!X(bundleKey: "lbl_CreateEvaluation")'
        assert clean_action_name(expr) == 'Create Evaluation'

    def test_plain_text_passthrough(self):
        assert clean_action_name('Create a vendor manually') == 'Create a vendor manually'

    def test_skips_unparseable_sail(self):
        assert clean_action_name('rule!SomeRule(x: 1)') == ''

    def test_empty(self):
        assert clean_action_name('') == ''


class TestExtractDomainTerm:
    def test_record_type(self):
        assert extract_domain_term('AS_PD_Collection_RecordType') == 'collection'

    def test_strips_leading_single_letters(self):
        assert extract_domain_term('AS_GSM_A_Disaster_Response_RECORD') == 'disaster response'

    def test_camel_case(self):
        assert extract_domain_term('AS_AIDB_AiDocInsights_RecordType') == 'ai doc insights'


class TestCollectPageNames:
    def test_flat(self):
        pages = [{'static_name': 'Home'}, {'static_name': 'Settings'}]
        assert collect_page_names(pages) == ['Home', 'Settings']

    def test_nested(self):
        pages = [{'static_name': 'Parent', 'children': [{'static_name': 'Child'}]}]
        assert collect_page_names(pages) == ['Parent', 'Child']

    def test_empty(self):
        assert collect_page_names([]) == []

    def test_skips_empty_names(self):
        pages = [{'static_name': ''}, {'static_name': 'Real'}]
        assert collect_page_names(pages) == ['Real']


class TestJoinNatural:
    def test_single(self):
        assert join_natural(['one']) == 'one'

    def test_two(self):
        assert join_natural(['a', 'b']) == 'a and b'

    def test_three(self):
        assert join_natural(['a', 'b', 'c']) == 'a, b and c'

    def test_truncation(self):
        result = join_natural(['a', 'b', 'c', 'd'], limit=2)
        assert result == 'a, b + 2 more'

    def test_empty(self):
        assert join_natural([]) == ''


# ── Description builder ──────────────────────────────────────────────

class TestDeriveDescription:
    def test_single_app_with_description(self):
        objs = [_app(description='Manages vendor data')]
        desc = derive_description([], objs)
        assert 'Manages vendor data' in desc

    def test_includes_sites(self):
        objs = [_site('My Portal', pages=[{'static_name': 'Home'}])]
        desc = derive_description([], objs)
        assert 'My Portal' in desc
        assert '1 pages' in desc

    def test_includes_record_types_single_app(self):
        objs = [_record('AS_APP_Vendor_RecordType')]
        desc = derive_description([], objs)
        assert 'vendor' in desc.lower()

    def test_multi_prefix_shows_breakdown(self):
        objs = [_app(prefix='AS_A')] + [
            _obj(name=f'AS_A_Rule{i}') for i in range(10)
        ] + [
            _obj(name=f'AS_B_Rule{i}') for i in range(10)
        ]
        desc = derive_description([], objs)
        assert 'Contains objects from:' in desc

    def test_empty(self):
        assert derive_description([], []) == ''


# ── Domain builder ───────────────────────────────────────────────────

class TestExtractDomains:
    def test_extracts_from_record_types(self):
        objs = [_record('AS_APP_Vendor_RecordType'), _record('AS_APP_Award_RecordType')]
        domains = extract_domains([], objs)
        assert 'vendor' in domains
        assert 'award' in domains

    def test_filters_stopwords(self):
        objs = [_record('AS_APP_Dynamic_Record')]
        domains = extract_domains([], objs)
        assert 'dynamic record' not in domains

    def test_extracts_from_pages(self):
        objs = [_site('Portal', pages=[{'static_name': 'Dashboard'}])]
        domains = extract_domains([], objs)
        assert 'dashboard' in domains

    def test_skips_unresolved_translations(self):
        objs = [_site('Portal', pages=[
            {'static_name': '#"urn:appian:translation-string:v1:abc123"'}
        ])]
        domains = extract_domains([], objs)
        assert len(domains) == 0

    def test_capped_at_max(self):
        objs = [_record(f'AS_APP_Type{i}_RecordType') for i in range(50)]
        domains = extract_domains([], objs)
        assert len(domains) <= 25

    def test_filters_known_prefixes(self):
        objs = [_app(prefix='AS_GSS'), _record('AS_GSS_Vendor_RecordType')]
        domains = extract_domains([], objs)
        # 'gss' should be filtered out
        assert 'gss' not in domains
        assert 'vendor' in domains


# ── Capability builder ───────────────────────────────────────────────

class TestExtractCapabilities:
    def test_groups_actions_by_record_type(self):
        entries = [
            {'bundle_type': 'action', 'root_name': 'RT - Create', 'parent_name': 'AS_APP_Case_RecordType', 'key_objects': []},
            {'bundle_type': 'action', 'root_name': 'RT - Update', 'parent_name': 'AS_APP_Case_RecordType', 'key_objects': []},
        ]
        caps = extract_capabilities(entries)
        record_caps = [c for c in caps if c['type'] == 'record actions']
        assert len(record_caps) == 1
        assert record_caps[0]['record_type'] == 'Case'
        assert record_caps[0]['action_count'] == 2
        assert 'Create' in record_caps[0]['actions']
        assert 'Update' in record_caps[0]['actions']

    def test_includes_sites(self):
        entries = [{'bundle_type': 'site', 'root_name': 'My Portal', 'key_objects': []}]
        caps = extract_capabilities(entries)
        site_caps = [c for c in caps if c['type'] == 'site']
        assert len(site_caps) == 1
        assert site_caps[0]['name'] == 'My Portal'

    def test_includes_web_apis(self):
        entries = [
            {'bundle_type': 'web_api', 'root_name': 'AS_APP_WA_GetData', 'key_objects': []},
            {'bundle_type': 'web_api', 'root_name': 'AS_APP_WA_PostData', 'key_objects': []},
        ]
        caps = extract_capabilities(entries)
        api_caps = [c for c in caps if c['type'] == 'web apis']
        assert len(api_caps) == 1
        assert api_caps[0]['count'] == 2

    def test_includes_processes(self):
        entries = [
            {'bundle_type': 'process', 'root_name': 'AS_APP_PM_HandleApproval', 'key_objects': []},
        ]
        caps = extract_capabilities(entries)
        proc_caps = [c for c in caps if c['type'] == 'processes']
        assert len(proc_caps) == 1
        assert proc_caps[0]['count'] == 1

    def test_cleans_action_names_from_sail(self):
        entries = [{
            'bundle_type': 'action',
            'root_name': 'RT - rule!X(bundleKey: "btn_ClaimTask")',
            'parent_name': 'AS_APP_Case_RecordType',
            'key_objects': [],
        }]
        caps = extract_capabilities(entries)
        record_caps = [c for c in caps if c['type'] == 'record actions']
        assert 'Claim Task' in record_caps[0]['actions']

    def test_merges_same_record_type(self):
        entries = [
            {'bundle_type': 'action', 'root_name': 'RT - Create', 'parent_name': 'AS_APP_Case_RecordType', 'key_objects': []},
            {'bundle_type': 'action', 'root_name': 'RT - Delete', 'parent_name': 'AS_APP_Case_RecordType', 'key_objects': []},
        ]
        caps = extract_capabilities(entries)
        record_caps = [c for c in caps if c['type'] == 'record actions']
        assert len(record_caps) == 1
        assert record_caps[0]['action_count'] == 2

    def test_empty(self):
        assert extract_capabilities([]) == []

    def test_dashboards(self):
        entries = [{'bundle_type': 'dashboard', 'root_name': 'Admin Panel', 'key_objects': []}]
        caps = extract_capabilities(entries)
        dash_caps = [c for c in caps if c['type'] == 'dashboard']
        assert len(dash_caps) == 1
        assert dash_caps[0]['name'] == 'Admin Panel'

from appian_parser.output.app_cross_app_builder import extract_cross_app_dependencies


class TestCrossAppDependencies:
    def test_extracts_entry_points(self):
        objs = [_obj(name='AS_GSS_ENTRYPOINT_GETDATA_getSlgToggleValue')]
        result = extract_cross_app_dependencies(objs, [])
        assert len(result['entry_points']) == 1
        ep = result['entry_points'][0]
        assert ep['prefix'] == 'AS_GSS'
        assert ep['operation_type'] == 'GETDATA'
        assert ep['function'] == 'getSlgToggleValue'

    def test_extracts_app_references(self):
        objs = [_obj(name='AS_GCW_APPREF_GSS_GETDATA_getSlgToggleValue')]
        result = extract_cross_app_dependencies(objs, [])
        assert len(result['app_references']) == 1
        ref = result['app_references'][0]
        assert ref['source_prefix'] == 'AS_GCW'
        assert ref['target_app'] == 'GSS'
        assert ref['operation_type'] == 'GETDATA'
        assert ref['function'] == 'getSlgToggleValue'

    def test_aggregates_edges(self):
        objs = [
            _obj(name='AS_GCW_APPREF_GSS_GETDATA_getData1'),
            _obj(name='AS_GCW_APPREF_GSS_DISPLAY_showThing'),
            _obj(name='AS_GCW_APPREF_RM_GETDATA_getReqs'),
        ]
        result = extract_cross_app_dependencies(objs, [])
        edges = result['dependency_edges']
        assert len(edges) == 2
        # Sorted by count desc
        assert edges[0]['from'] == 'AS_GCW'
        assert edges[0]['to'] == 'GSS'
        assert edges[0]['reference_count'] == 2

    def test_empty(self):
        result = extract_cross_app_dependencies([], [])
        assert result['entry_points'] == []
        assert result['app_references'] == []
        assert result['dependency_edges'] == []
        assert result['shared_library_usage'] == []

    def test_ignores_non_entrypoint_objects(self):
        objs = [_obj(name='AS_GSS_BL_ValidateCase')]
        result = extract_cross_app_dependencies(objs, [])
        assert len(result['entry_points']) == 0
        assert len(result['app_references']) == 0

    def test_startprocess_entrypoint(self):
        objs = [_obj(name='AS_AIDB_ENTRYPOINT_STARTPROCESS_generateDocument_v1')]
        result = extract_cross_app_dependencies(objs, [])
        ep = result['entry_points'][0]
        assert ep['operation_type'] == 'STARTPROCESS'
        assert ep['function'] == 'generateDocument_v1'
