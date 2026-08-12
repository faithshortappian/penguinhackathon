"""Tests for Phase 3 versioning components."""

import json
import os
import pytest

from appian_parser.domain.models import ParsedObject, DumpOptions
from appian_parser.versioning.config import AppConfig, VersionDetector, VersionInfo, ReleaseIndexBuilder
from appian_parser.versioning.parsed_state import ParsedStateStore
from appian_parser.output.versioned_writer import SmartWriter, VersionedWriter
from appian_parser.output.v3_manifest_builder import V3ManifestBuilder


def _obj(uuid='_a-001', name='TestRule', obj_type='Expression Rule', **data_kw):
    data = {'description': 'test', **data_kw}
    return ParsedObject(uuid=uuid, name=name, object_type=obj_type, data=data, diff_hash='abc123')


# ── AppConfig ────────────────────────────────────────────────────────

class TestAppConfig:
    def test_load(self, tmp_path):
        cfg = {'application_name': 'GSS', 'version_constant': 'AS_GSS_CO_APP_VERSION', 'max_retained_releases': 5}
        path = tmp_path / 'app_config.json'
        path.write_text(json.dumps(cfg))
        config = AppConfig.load(str(path))
        assert config.application_name == 'GSS'
        assert config.max_retained_releases == 5

    def test_load_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            AppConfig.load('/nonexistent/app_config.json')


# ── VersionDetector ──────────────────────────────────────────────────

class TestVersionDetector:
    def test_detect_from_objects(self):
        obj = _obj(name='AS_GSS_CO_APP_VERSION', obj_type='Constant', value='25.04.02.09.00')
        result = VersionDetector().detect([obj], 'AS_GSS_CO_APP_VERSION')
        assert result is not None
        assert result.raw == '25.04.02.09.00'
        assert result.appian_version == '25.04'
        assert result.solution_version == '02.09.00'
        assert result.sort_key == (25, 4, 2, 9, 0)

    def test_detect_not_found(self):
        obj = _obj(name='SomeOtherConstant', obj_type='Constant', value='1.0')
        assert VersionDetector().detect([obj], 'AS_GSS_CO_APP_VERSION') is None

    def test_parse_version(self):
        v = VersionDetector.parse_version('25.04.03.00.00')
        assert v.sort_key == (25, 4, 3, 0, 0)


# ── V3ManifestBuilder ───────────────────────────────────────────────

class TestV3ManifestBuilder:
    def test_baseline(self):
        obj = _obj()
        m = V3ManifestBuilder.build([obj], '1.0.0', '2026-01-01T00:00:00Z')
        assert m['_metadata']['version'] == '1.0.0'
        assert m['_metadata']['total_objects'] == 1
        assert m['objects']['_a-001']['last_changed_in'] == '1.0.0'

    def test_unchanged_carries_forward(self):
        obj = _obj()
        prev = {'objects': {'_a-001': {'diff_hash': 'abc123', 'last_changed_in': '1.0.0'}}}
        m = V3ManifestBuilder.build([obj], '2.0.0', '2026-01-01', previous_manifest=prev)
        assert m['objects']['_a-001']['last_changed_in'] == '1.0.0'

    def test_changed_gets_new_version(self):
        obj = _obj()
        obj.diff_hash = 'new_hash'
        prev = {'objects': {'_a-001': {'diff_hash': 'old_hash', 'last_changed_in': '1.0.0'}}}
        m = V3ManifestBuilder.build([obj], '2.0.0', '2026-01-01', previous_manifest=prev)
        assert m['objects']['_a-001']['last_changed_in'] == '2.0.0'


# ── ParsedStateStore ────────────────────────────────────────────────

class TestParsedStateStore:
    def test_roundtrip(self, tmp_path):
        obj = _obj()
        state = ParsedStateStore.build([obj], '1.0.0', '2026-01-01')
        path = str(tmp_path / 'parsed_state.json')
        with open(path, 'w') as f:
            json.dump(state, f)
        loaded, version = ParsedStateStore.load(path)
        assert version == '1.0.0'
        assert len(loaded) == 1
        assert loaded[0].uuid == '_a-001'
        assert loaded[0].name == 'TestRule'


# ── SmartWriter ──────────────────────────────────────────────────────

class TestSmartWriter:
    def test_write_new_file(self, tmp_path):
        w = SmartWriter()
        w.write_json(str(tmp_path / 'test.json'), {'key': 'value'})
        assert w.stats.files_written == 1
        assert w.stats.files_skipped == 0

    def test_skip_identical(self, tmp_path):
        w = SmartWriter()
        path = str(tmp_path / 'test.json')
        w.write_json(path, {'key': 'value'})
        w.write_json(path, {'key': 'value'})
        assert w.stats.files_written == 1
        assert w.stats.files_skipped == 1

    def test_rewrite_changed(self, tmp_path):
        w = SmartWriter()
        path = str(tmp_path / 'test.json')
        w.write_json(path, {'key': 'v1'})
        w.write_json(path, {'key': 'v2'})
        assert w.stats.files_written == 2

    def test_cleanup_stale(self, tmp_path):
        (tmp_path / 'keep.json').write_text('{}')
        (tmp_path / 'stale.json').write_text('{}')
        w = SmartWriter()
        w.cleanup_stale(str(tmp_path), {'keep.json'})
        assert w.stats.files_deleted == 1
        assert not (tmp_path / 'stale.json').exists()
        assert (tmp_path / 'keep.json').exists()


# ── ReleaseIndexBuilder ──────────────────────────────────────────────

class TestReleaseIndexBuilder:
    def test_baseline(self):
        vi = VersionInfo(raw='1.0.0', appian_version='1.0', solution_version='0', sort_key=(1, 0, 0))
        idx = ReleaseIndexBuilder.build_baseline('GSS', vi, '2026-01-01', 'pkg.zip', 100, 10)
        assert idx['_metadata']['total_releases'] == 1
        assert idx['releases'][0]['is_baseline'] is True

    def test_append(self):
        vi1 = VersionInfo(raw='1.0.0', appian_version='1.0', solution_version='0', sort_key=(1, 0, 0))
        idx = ReleaseIndexBuilder.build_baseline('GSS', vi1, '2026-01-01', 'pkg.zip', 100, 10)
        vi2 = VersionInfo(raw='2.0.0', appian_version='2.0', solution_version='0', sort_key=(2, 0, 0))
        ReleaseIndexBuilder.append_release(idx, vi2, '2026-02-01', 'pkg2.zip', 110, 12,
                                           {'objects_added': 10}, '1.0.0')
        assert idx['_metadata']['total_releases'] == 2
        assert idx['_metadata']['latest_release'] == '2.0.0'
        assert idx['releases'][1]['previous_release'] == '1.0.0'


# ── VersionedWriter ─────────────────────────────────────────────────

class TestVersionedWriter:
    def test_baseline_creates_structure(self, tmp_path):
        from appian_parser.domain.models import BuildArtifacts
        artifacts = BuildArtifacts(
            object_files={'_a-001': {'uuid': '_a-001', 'name': 'X', 'type': 'Expression Rule'}},
            code_files={'_a-001': {'uuid': '_a-001', 'sail_code': '1+1'}},
            bundle_dicts=[{'_metadata': {'bundle_id': 'B1', 'bundle_type': 'action', 'root_name': 'B1', 'parent_name': None, 'object_count': 1}}],
            graph={'_metadata': {'node_count': 1, 'edge_count': 0}, 'nodes': [], 'edges': []},
            search_index={'X': {'uuid': '_a-001'}},
            app_overview={'_metadata': {}},
            orphan_index={'_metadata': {'total_orphans': 0}},
        )
        manifest = {'_metadata': {'version': '1.0.0'}, 'objects': {}}
        parsed_state = {'_metadata': {'version': '1.0.0'}, 'objects': {}}
        release_index = {'_metadata': {}, 'releases': []}

        data_dir = str(tmp_path / 'data')
        w = VersionedWriter(data_dir, pretty=True)
        stats = w.write_baseline(artifacts, manifest, parsed_state, release_index)

        assert os.path.isfile(f"{data_dir}/current/manifest.json")
        assert os.path.isfile(f"{data_dir}/current/objects/_a-001.json")
        assert os.path.isfile(f"{data_dir}/current/code/_a-001.json")
        assert os.path.isfile(f"{data_dir}/current/bundles/B1.json")
        assert os.path.isfile(f"{data_dir}/current/graph.json")
        assert os.path.isfile(f"{data_dir}/current/parsed_state.json")
        assert os.path.isfile(f"{data_dir}/release_index.json")
        assert stats.files_written > 0

    def test_second_write_skips_unchanged(self, tmp_path):
        from appian_parser.domain.models import BuildArtifacts
        artifacts = BuildArtifacts(
            object_files={'_a-001': {'uuid': '_a-001'}},
            code_files={},
            bundle_dicts=[],
            graph={'nodes': [], 'edges': []},
            search_index={},
            app_overview={},
            orphan_index={},
        )
        manifest = {'objects': {}}
        parsed_state = {'objects': {}}

        data_dir = str(tmp_path / 'data')
        w1 = VersionedWriter(data_dir, pretty=True)
        w1.write_baseline(artifacts, manifest, parsed_state, {'releases': []})

        w2 = VersionedWriter(data_dir, pretty=True)
        w2.write_daily_update(artifacts, manifest, parsed_state)
        # parsed_state is always written (raw), but objects should be skipped
        assert w2.stats.files_skipped >= 1
