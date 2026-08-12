"""History archival, snapshots, changelogs, and retention pruning."""

from __future__ import annotations

import json
import os
import shutil

from appian_parser.domain.models import ParsedObject
from appian_parser.output.object_file_builder import extract_type_specific
from appian_parser.output.code_file_builder import extract_code


class HistoryArchiver:
    """Archives changed objects to history/<uuid>/<version>.json."""

    def archive(
        self,
        data_dir: str,
        changed_uuids: set[str],
        old_version: str,
        old_objects: list[ParsedObject],
        dependencies: list,
        bundle_assignments: dict[str, list[str]],
        pretty: bool = True,
    ) -> int:
        obj_map = {o.uuid: o for o in old_objects}
        calls_map: dict[str, list] = {}
        called_by_map: dict[str, list] = {}
        for dep in dependencies:
            calls_map.setdefault(dep.source_uuid, []).append(
                {'uuid': dep.target_uuid, 'name': dep.target_name, 'type': dep.target_type, 'dep_type': dep.dependency_type})
            called_by_map.setdefault(dep.target_uuid, []).append(
                {'uuid': dep.source_uuid, 'name': dep.source_name, 'type': dep.source_type, 'dep_type': dep.dependency_type})

        archived = 0
        for uuid in changed_uuids:
            obj = obj_map.get(uuid)
            if not obj:
                continue
            snapshot = {
                'uuid': obj.uuid, 'name': obj.name, 'type': obj.object_type,
                'description': obj.data.get('description', ''), 'diff_hash': obj.diff_hash,
                'bundles': bundle_assignments.get(obj.uuid, []),
                'calls': calls_map.get(uuid, []), 'called_by': called_by_map.get(uuid, []),
                'sail_code': extract_code(obj), 'type_specific': extract_type_specific(obj),
            }
            path = f"{data_dir}/history/{uuid}/{old_version}.json"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2 if pretty else None, ensure_ascii=False, default=str)
            archived += 1
        return archived


class SnapshotWriter:
    """Copies current manifest + app_overview to release_snapshots."""

    def snapshot(self, data_dir: str, version: str) -> None:
        dest = f"{data_dir}/release_snapshots/{version}"
        os.makedirs(dest, exist_ok=True)
        for fname in ('manifest.json', 'app_overview.json'):
            src = f"{data_dir}/current/{fname}"
            if os.path.isfile(src):
                shutil.copy2(src, f"{dest}/{fname}")


class ChangelogBuilder:
    """Generates changelog by diffing old manifest vs new manifest."""

    def build(
        self,
        old_manifest: dict, new_manifest: dict,
        old_version: str, new_version: str, generated_at: str,
        bundle_assignments: dict[str, list[str]],
        old_bundle_dicts: list[dict] | None, new_bundle_dicts: list[dict],
        version_constant_name: str, is_full_parse: bool,
    ) -> dict:
        old_objs = old_manifest.get('objects', {})
        new_objs = new_manifest.get('objects', {})
        obj_changes, added, modified, removed, unchanged = [], 0, 0, 0, 0

        for uuid, new_e in new_objs.items():
            if new_e['name'] == version_constant_name:
                continue
            if uuid not in old_objs:
                obj_changes.append({'uuid': uuid, 'name': new_e['name'], 'type': new_e['type'],
                                    'status': 'added', 'old_hash': None, 'new_hash': new_e['diff_hash'],
                                    'affected_bundles': bundle_assignments.get(uuid, [])})
                added += 1
            elif old_objs[uuid]['diff_hash'] != new_e['diff_hash']:
                obj_changes.append({'uuid': uuid, 'name': new_e['name'], 'type': new_e['type'],
                                    'status': 'modified', 'old_hash': old_objs[uuid]['diff_hash'],
                                    'new_hash': new_e['diff_hash'],
                                    'affected_bundles': bundle_assignments.get(uuid, [])})
                modified += 1
            else:
                unchanged += 1

        if is_full_parse:
            for uuid, old_e in old_objs.items():
                if uuid not in new_objs and old_e['name'] != version_constant_name:
                    obj_changes.append({'uuid': uuid, 'name': old_e['name'], 'type': old_e['type'],
                                        'status': 'removed', 'old_hash': old_e['diff_hash'], 'new_hash': None,
                                        'affected_bundles': []})
                    removed += 1

        bundle_changes = self._diff_bundles(old_bundle_dicts, new_bundle_dicts)
        b_added = sum(1 for b in bundle_changes if b['status'] == 'added')
        b_modified = sum(1 for b in bundle_changes if b['status'] == 'modified')
        b_removed = sum(1 for b in bundle_changes if b['status'] == 'removed')

        return {
            '_metadata': {'from_release': old_version, 'to_release': new_version, 'generated_at': generated_at},
            'summary': {
                'objects_added': added, 'objects_modified': modified,
                'objects_removed': removed, 'objects_unchanged': unchanged,
                'bundles_added': b_added, 'bundles_modified': b_modified,
                'bundles_removed': b_removed,
                'bundles_unchanged': len(new_bundle_dicts) - b_added - b_modified,
            },
            'object_changes': obj_changes,
            'bundle_changes': bundle_changes,
        }

    @staticmethod
    def _diff_bundles(old_bundles: list[dict] | None, new_bundles: list[dict]) -> list[dict]:
        old_map = {b['_metadata']['bundle_id']: b for b in (old_bundles or [])}
        new_map = {b['_metadata']['bundle_id']: b for b in new_bundles}
        changes = []

        for bid, new_b in new_map.items():
            if bid not in old_map:
                changes.append({'bundle_id': bid, 'bundle_type': new_b['_metadata']['bundle_type'],
                                'status': 'added', 'members_added': [], 'members_removed': []})
            else:
                old_uuids = {m['uuid'] for m in old_map[bid].get('members', [])}
                new_uuids = {m['uuid'] for m in new_b.get('members', [])}
                if old_uuids != new_uuids:
                    new_members_map = {m['uuid']: m for m in new_b.get('members', [])}
                    old_members_map = {m['uuid']: m for m in old_map[bid].get('members', [])}
                    m_added = [{'name': new_members_map[u]['name'], 'type': new_members_map[u]['type']}
                               for u in new_uuids - old_uuids if u in new_members_map]
                    m_removed = [{'name': old_members_map[u]['name'], 'type': old_members_map[u]['type']}
                                 for u in old_uuids - new_uuids if u in old_members_map]
                    changes.append({'bundle_id': bid, 'bundle_type': new_b['_metadata']['bundle_type'],
                                    'status': 'modified', 'members_added': m_added, 'members_removed': m_removed})

        for bid in old_map:
            if bid not in new_map:
                changes.append({'bundle_id': bid, 'bundle_type': old_map[bid]['_metadata']['bundle_type'],
                                'status': 'removed', 'members_added': [], 'members_removed': []})
        return changes


class RetentionPruner:
    """Prunes oldest release data when retention limit exceeded."""

    def prune_if_needed(self, data_dir: str, release_index: dict, max_retained: int) -> int:
        releases = release_index.get('releases', [])
        pruned = 0
        while len(releases) > max_retained:
            oldest = releases.pop(0)
            self._delete_release_data(data_dir, oldest['version'])
            pruned += 1
        release_index['_metadata']['total_releases'] = len(releases)
        return pruned

    @staticmethod
    def _delete_release_data(data_dir: str, version: str) -> None:
        shutil.rmtree(f"{data_dir}/release_snapshots/{version}", ignore_errors=True)
        changelog = f"{data_dir}/changelogs/{version}.json"
        if os.path.isfile(changelog):
            os.remove(changelog)
        history_dir = f"{data_dir}/history"
        if os.path.isdir(history_dir):
            for uuid_dir_name in os.listdir(history_dir):
                vfile = os.path.join(history_dir, uuid_dir_name, f"{version}.json")
                if os.path.isfile(vfile):
                    os.remove(vfile)
                uuid_path = os.path.join(history_dir, uuid_dir_name)
                if os.path.isdir(uuid_path) and not os.listdir(uuid_path):
                    os.rmdir(uuid_path)
