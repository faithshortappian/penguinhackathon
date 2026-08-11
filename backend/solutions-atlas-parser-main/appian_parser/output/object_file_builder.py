"""Builds enriched object metadata files (objects/<uuid>.json)."""

from __future__ import annotations

from appian_parser.domain.models import ParsedObject

# Fields to extract from obj.data per object type
_TYPE_SPECIFIC_FIELDS: dict[str, list[str]] = {
    'Expression Rule': ['inputs', 'output_type', 'test_cases'],
    'Interface': ['parameters'],
    'Process Model': ['variables', 'total_nodes', 'complexity_score', 'start_form_interface'],
    'Record Type': ['fields', 'relationships', 'views', 'actions', 'data_source'],
    'CDT': ['namespace', 'fields'],
    'Integration': ['connected_system', 'http_method', 'url'],
    'Web API': ['http_method', 'url_alias', 'security'],
    'Site': ['pages'],
    'Constant': ['value', 'value_type', 'scope'],
    'Connected System': ['base_url', 'auth_type'],
    'Control Panel': ['interfaces', 'primary_record_type'],
    'Group': ['group_type', 'parent_group'],
    'Translation Set': ['default_locale', 'enabled_locales'],
    'Translation String': ['translations'],
}


def extract_type_specific(obj: ParsedObject) -> dict:
    """Extract type-dependent fields from obj.data."""
    fields = _TYPE_SPECIFIC_FIELDS.get(obj.object_type, [])
    result = {}
    for f in fields:
        if f in obj.data:
            result[f] = obj.data[f]
    return result


class ObjectFileBuilder:
    """Builds the v3 objects/<uuid>.json dicts."""

    def build_all(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        bundle_assignments: dict[str, list[str]],
        hub_uuids: set[str],
        orphan_uuids: set[str],
        *,
        version: str | None = None,
        previous_object_files: dict[str, dict] | None = None,
    ) -> dict[str, dict]:
        """Build enriched object dict for every parsed object."""
        calls_map: dict[str, list[dict]] = {}
        called_by_map: dict[str, list[dict]] = {}

        for dep in dependencies:
            calls_map.setdefault(dep.source_uuid, []).append({
                'uuid': dep.target_uuid,
                'name': dep.target_name,
                'type': dep.target_type,
                'dep_type': dep.dependency_type,
            })
            called_by_map.setdefault(dep.target_uuid, []).append({
                'uuid': dep.source_uuid,
                'name': dep.source_name,
                'type': dep.source_type,
                'dep_type': dep.dependency_type,
            })

        result: dict[str, dict] = {}
        for obj in parsed_objects:
            calls = calls_map.get(obj.uuid, [])
            called_by = called_by_map.get(obj.uuid, [])

            obj_dict: dict = {
                'uuid': obj.uuid,
                'name': obj.name,
                'type': obj.object_type,
                'description': obj.data.get('description', ''),
                'diff_hash': obj.diff_hash,
                'bundles': bundle_assignments.get(obj.uuid, []),
                'is_hub': obj.uuid in hub_uuids,
                'is_orphan': obj.uuid in orphan_uuids,
                'inbound_count': len(called_by),
                'outbound_count': len(calls),
                'calls': calls,
                'called_by': called_by,
                'type_specific': extract_type_specific(obj),
            }

            if version is not None:
                obj_dict['version_history'] = self._build_version_history(
                    obj, version, previous_object_files,
                )

            result[obj.uuid] = obj_dict

        return result

    @staticmethod
    def _build_version_history(
        obj: ParsedObject,
        version: str,
        previous_files: dict[str, dict] | None,
    ) -> list[dict]:
        current_entry = {'version': version, 'status': 'current', 'diff_hash': obj.diff_hash}

        if not previous_files:
            return [current_entry]

        prev = previous_files.get(obj.uuid)
        if not prev:
            return [current_entry]

        prev_history = prev.get('version_history', [])
        new_history = [current_entry]
        for entry in prev_history:
            if entry['status'] == 'current':
                if entry['diff_hash'] != obj.diff_hash:
                    new_history.append({**entry, 'status': 'modified'})
                # same hash (daily update) → drop old current, replaced by new
            else:
                new_history.append(entry)
        return new_history
