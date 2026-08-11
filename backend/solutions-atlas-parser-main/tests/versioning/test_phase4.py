"""Tests for Phase 4 delta and versioning components."""

import json
import os
import pytest

from appian_parser.domain.models import ParsedObject
from appian_parser.versioning.delta import DeltaMerger, ModeDetector, ParseMode
from appian_parser.versioning.history import (
    HistoryArchiver, SnapshotWriter, ChangelogBuilder, RetentionPruner,
)
from appian_parser.dependencies.analyzer import Dependency


def _obj(uuid='_a-001', name='R1', diff_hash='h1', obj_type='Expression Rule', **kw):
    return ParsedObject(uuid=uuid, name=name, object_type=obj_type,
                        data={'description': 'test', **kw}, diff_hash=diff_hash)


def _dep(src, tgt, dep_type='CALLS'):
    return Dependency(source_uuid=src, source_name=f'S_{src}', source_type='Expression Rule',
                      target_uuid=tgt, target_name=f'T_{tgt}', target_type='Expression Rule',
                      dependency_type=dep_type, reference_context='sail_code', is_resolved=True)


# ── DeltaMerger ──────────────────────────────────────────────────────

class TestDeltaMerger:
    def test_merge_replaces_existing(self):
        existing = [_obj(uuid='_a-001', diff_hash='old')]
        delta = [_obj(uuid='_a-001', diff_hash='new')]
        result = DeltaMerger().merge(existing, delta)
        assert len(result.merged_objects) == 1
        assert result.merged_objects[0].diff_hash == 'new'
        assert '_a-001' in result.modified_uuids

    def test_merge_adds_new(self):
        existing = [_obj(uuid='_a-001')]
        delta = [_obj(uuid='_a-002', name='R2')]
        result = DeltaMerger().merge(existing, delta)
        assert len(result.merged_objects) == 2
        assert '_a-002' in result.added_uuids

    def test_merge_unchanged(self):
        existing = [_obj(uuid='_a-001', diff_hash='same')]
        delta = [_obj(uuid='_a-001', diff_hash='same')]
        result = DeltaMerger().merge(existing, delta)
        assert len(result.modified_uuids) == 0
        assert len(result.added_uuids) == 0

    def test_empty_delta(self):
        existing = [_obj()]
        result = DeltaMerger().merge(existing, [])
        assert len(result.merged_objects) == 1


# ── ModeDetector ─────────────────────────────────────────────────────

class TestModeDetector:
    def test_same_version(self):
        assert ModeDetector().detect('1.0', '1.0') == ParseMode.DAILY_UPDATE

    def test_different_version(self):
        assert ModeDetector().detect('1.0', '2.0') == ParseMode.NEW_RELEASE

    def test_none_version(self):
        assert ModeDetector().detect('1.0', None) == ParseMode.DAILY_UPDATE


# ── ChangelogBuilder ─────────────────────────────────────────────────

class TestChangelogBuilder:
    def test_detects_added(self):
        old_m = {'objects': {}}
        new_m = {'objects': {'_a-001': {'name': 'R1', 'type': 'Expression Rule', 'diff_hash': 'h1'}}}
        cl = ChangelogBuilder().build(old_m, new_m, '1.0', '2.0', 'now', {}, None, [], 'VERSION', False)
        assert cl['summary']['objects_added'] == 1
        assert cl['object_changes'][0]['status'] == 'added'

    def test_detects_modified(self):
        old_m = {'objects': {'_a-001': {'name': 'R1', 'type': 'ER', 'diff_hash': 'old'}}}
        new_m = {'objects': {'_a-001': {'name': 'R1', 'type': 'ER', 'diff_hash': 'new'}}}
        cl = ChangelogBuilder().build(old_m, new_m, '1.0', '2.0', 'now', {}, None, [], 'VERSION', False)
        assert cl['summary']['objects_modified'] == 1

    def test_detects_removed_full_parse(self):
        old_m = {'objects': {'_a-001': {'name': 'R1', 'type': 'ER', 'diff_hash': 'h1'}}}
        new_m = {'objects': {}}
        cl = ChangelogBuilder().build(old_m, new_m, '1.0', '2.0', 'now', {}, None, [], 'VERSION', True)
        assert cl['summary']['objects_removed'] == 1

    def test_no_removed_in_delta(self):
        old_m = {'objects': {'_a-001': {'name': 'R1', 'type': 'ER', 'diff_hash': 'h1'}}}
        new_m = {'objects': {}}
        cl = ChangelogBuilder().build(old_m, new_m, '1.0', '2.0', 'now', {}, None, [], 'VERSION', False)
        assert cl['summary']['objects_removed'] == 0

    def test_excludes_version_constant(self):
        old_m = {'objects': {}}
        new_m = {'objects': {'_a-001': {'name': 'MY_VERSION', 'type': 'Constant', 'diff_hash': 'h1'}}}
        cl = ChangelogBuilder().build(old_m, new_m, '1.0', '2.0', 'now', {}, None, [], 'MY_VERSION', False)
        assert cl['summary']['objects_added'] == 0


# ── HistoryArchiver ──────────────────────────────────────────────────

class TestHistoryArchiver:
    def test_archives_changed(self, tmp_path):
        obj = _obj(definition='code here')
        dep = _dep('_a-001', '_a-002')
        count = HistoryArchiver().archive(
            str(tmp_path), {'_a-001'}, '1.0.0', [obj], [dep], {'_a-001': ['B1']},
        )
        assert count == 1
        path = tmp_path / 'history' / '_a-001' / '1.0.0.json'
        assert path.exists()
        data = json.loads(path.read_text())
        assert data['name'] == 'R1'
        assert data['bundles'] == ['B1']

    def test_skips_missing_uuid(self, tmp_path):
        count = HistoryArchiver().archive(str(tmp_path), {'_a-999'}, '1.0', [], [], {})
        assert count == 0


# ── SnapshotWriter ───────────────────────────────────────────────────

class TestSnapshotWriter:
    def test_creates_snapshot(self, tmp_path):
        current = tmp_path / 'current'
        current.mkdir()
        (current / 'manifest.json').write_text('{"m": 1}')
        (current / 'app_overview.json').write_text('{"a": 1}')
        SnapshotWriter().snapshot(str(tmp_path), '1.0.0')
        assert (tmp_path / 'release_snapshots' / '1.0.0' / 'manifest.json').exists()
        assert (tmp_path / 'release_snapshots' / '1.0.0' / 'app_overview.json').exists()


# ── RetentionPruner ──────────────────────────────────────────────────

class TestRetentionPruner:
    def test_no_prune_under_limit(self):
        idx = {'_metadata': {'total_releases': 2}, 'releases': [{'version': '1.0'}, {'version': '2.0'}]}
        pruned = RetentionPruner().prune_if_needed('/tmp', idx, 5)
        assert pruned == 0
        assert len(idx['releases']) == 2

    def test_prunes_oldest(self, tmp_path):
        # Create snapshot + changelog for v1.0
        (tmp_path / 'release_snapshots' / '1.0').mkdir(parents=True)
        (tmp_path / 'release_snapshots' / '1.0' / 'manifest.json').write_text('{}')
        (tmp_path / 'changelogs').mkdir()
        (tmp_path / 'changelogs' / '1.0.json').write_text('{}')

        idx = {'_metadata': {'total_releases': 3},
               'releases': [{'version': '1.0'}, {'version': '2.0'}, {'version': '3.0'}]}
        pruned = RetentionPruner().prune_if_needed(str(tmp_path), idx, 2)
        assert pruned == 1
        assert len(idx['releases']) == 2
        assert idx['releases'][0]['version'] == '2.0'
        assert not (tmp_path / 'release_snapshots' / '1.0').exists()
        assert not (tmp_path / 'changelogs' / '1.0.json').exists()
