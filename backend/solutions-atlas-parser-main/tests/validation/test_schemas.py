"""Schema validation — verify all output files conform to v3 spec."""

import json
import os
import pytest
from tests.validation.conftest import load_json


class TestObjectFileSchema:
    def test_required_fields(self, legacy_output):
        obj_dir = f"{legacy_output}/objects"
        for fname in os.listdir(obj_dir)[:50]:  # sample 50
            obj = load_json(f"{obj_dir}/{fname}")
            assert 'uuid' in obj, f"Missing uuid in {fname}"
            assert 'name' in obj
            assert 'type' in obj
            assert 'description' in obj
            assert 'diff_hash' in obj
            assert 'bundles' in obj and isinstance(obj['bundles'], list)
            assert 'is_hub' in obj and isinstance(obj['is_hub'], bool)
            assert 'is_orphan' in obj and isinstance(obj['is_orphan'], bool)
            assert 'inbound_count' in obj and isinstance(obj['inbound_count'], int)
            assert 'outbound_count' in obj and isinstance(obj['outbound_count'], int)
            assert 'calls' in obj and isinstance(obj['calls'], list)
            assert 'called_by' in obj and isinstance(obj['called_by'], list)
            assert 'type_specific' in obj and isinstance(obj['type_specific'], dict)

    def test_uuid_matches_filename(self, legacy_output):
        obj_dir = f"{legacy_output}/objects"
        for fname in os.listdir(obj_dir)[:50]:
            obj = load_json(f"{obj_dir}/{fname}")
            assert fname == f"{obj['uuid']}.json"

    def test_no_version_history_in_legacy(self, legacy_output):
        obj_dir = f"{legacy_output}/objects"
        for fname in os.listdir(obj_dir)[:50]:
            obj = load_json(f"{obj_dir}/{fname}")
            assert 'version_history' not in obj

    def test_calls_entry_structure(self, legacy_output):
        obj_dir = f"{legacy_output}/objects"
        for fname in os.listdir(obj_dir)[:50]:
            obj = load_json(f"{obj_dir}/{fname}")
            for call in obj['calls']:
                assert 'uuid' in call
                assert 'name' in call
                assert 'type' in call
                assert 'dep_type' in call


class TestCodeFileSchema:
    def test_required_fields(self, legacy_output):
        code_dir = f"{legacy_output}/code"
        for fname in os.listdir(code_dir)[:50]:
            code = load_json(f"{code_dir}/{fname}")
            assert 'uuid' in code
            assert 'name' in code
            assert 'type' in code
            assert 'sail_code' in code
            assert len(code['sail_code']) > 0

    def test_uuid_matches_filename(self, legacy_output):
        code_dir = f"{legacy_output}/code"
        for fname in os.listdir(code_dir)[:20]:
            code = load_json(f"{code_dir}/{fname}")
            assert fname == f"{code['uuid']}.json"


class TestBundleFileSchema:
    def test_required_fields(self, legacy_output):
        bundle_dir = f"{legacy_output}/bundles"
        for fname in os.listdir(bundle_dir)[:30]:
            b = load_json(f"{bundle_dir}/{fname}")
            meta = b.get('_metadata', {})
            assert 'bundle_id' in meta
            assert 'bundle_type' in meta
            assert meta['bundle_type'] in ('action', 'process', 'page', 'site', 'dashboard', 'web_api')
            assert 'root_name' in meta
            assert 'object_count' in meta
            assert 'entry_point' in b
            assert 'members' in b and isinstance(b['members'], list)
            assert 'key_objects' in b and isinstance(b['key_objects'], list)

    def test_members_structure(self, legacy_output):
        bundle_dir = f"{legacy_output}/bundles"
        for fname in os.listdir(bundle_dir)[:20]:
            b = load_json(f"{bundle_dir}/{fname}")
            for m in b['members']:
                assert 'uuid' in m
                assert 'name' in m
                assert 'type' in m

    def test_object_count_matches_members(self, legacy_output):
        bundle_dir = f"{legacy_output}/bundles"
        for fname in os.listdir(bundle_dir)[:20]:
            b = load_json(f"{bundle_dir}/{fname}")
            assert b['_metadata']['object_count'] == len(b['members'])


class TestGraphSchema:
    def test_structure(self, legacy_output):
        g = load_json(f"{legacy_output}/graph.json")
        meta = g['_metadata']
        assert meta['node_count'] == len(g['nodes'])
        assert meta['edge_count'] == len(g['edges'])
        assert 'hub_threshold' in meta

    def test_node_fields(self, legacy_output):
        g = load_json(f"{legacy_output}/graph.json")
        for node in g['nodes'][:50]:
            assert 'id' in node
            assert 'name' in node
            assert 'type' in node
            assert 'bundles' in node
            assert 'inbound_count' in node
            assert 'outbound_count' in node
            assert 'is_hub' in node
            assert 'is_orphan' in node
            assert 'description' not in node  # excluded by design

    def test_edge_fields(self, legacy_output):
        g = load_json(f"{legacy_output}/graph.json")
        for edge in g['edges'][:50]:
            assert 'from' in edge
            assert 'to' in edge
            assert 'type' in edge


class TestSearchIndexSchema:
    def test_entry_fields(self, legacy_output):
        idx = load_json(f"{legacy_output}/search_index.json")
        for name, entry in list(idx.items())[:50]:
            assert 'uuid' in entry
            assert 'type' in entry
            assert 'description' in entry
            assert 'bundle_count' in entry
            assert 'deps_out' in entry
            assert 'deps_in' in entry


class TestOrphanIndexSchema:
    def test_structure(self, legacy_output):
        oi = load_json(f"{legacy_output}/orphans_index.json")
        assert 'total_orphans' in oi['_metadata']
        assert 'by_type' in oi
        assert 'orphans' in oi
        assert oi['_metadata']['total_orphans'] == len(oi['orphans'])
        assert sum(oi['by_type'].values()) == oi['_metadata']['total_orphans']
