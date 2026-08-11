"""Orchestrates bundle generation using specialized builders.

Extracts entry point discovery and dependency walking from the old
BundleBuilder, delegates structure and code generation to specialized builders.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from appian_parser.domain.constants import (
    CANONICAL_RE,
    CONS_REF_RE,
    RECORD_TYPE_REF_RE,
    RULE_REF_RE,
    TYPE_REF_RE,
    UUID_FULL_RE,
    UUID_STANDARD_RE,
)
from appian_parser.domain.models import ParsedObject
from appian_parser.output.bundle_structure_builder import BundleStructureBuilder
from appian_parser.output.bundle_code_builder import BundleCodeBuilder


@dataclass
class EntryPoint:
    """A top-level entry point that roots a bundle."""
    uuid: str
    name: str
    object_type: str
    bundle_type: str
    parent_name: str | None = None
    extra: dict = field(default_factory=dict)


_HUB_CALLER_THRESHOLD = 20


class BundleCoordinator:
    """Orchestrates bundle generation using specialized builders."""

    def __init__(
        self,
        structure_builder: BundleStructureBuilder | None = None,
        code_builder: BundleCodeBuilder | None = None,
        pretty: bool = True,
    ):
        self._structure_builder = structure_builder or BundleStructureBuilder()
        self._code_builder = code_builder or BundleCodeBuilder()
        self._pretty = pretty
        self._name_lookup: dict[str, str] = {}
        self._index_entries: list[dict] = []

    def get_index_entries(self) -> list[dict]:
        """Return bundle index entries (available after build_all)."""
        return self._index_entries

    def build_all_v3(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
    ) -> tuple[dict[str, list[str]], set[str], list[dict], list[dict]]:
        """Build all bundles in memory. Returns (assignments, hub_uuids, index_entries, bundle_dicts)."""
        from appian_parser.output.bundle_file_builder import BundleFileBuilder

        obj_map = {obj.uuid: obj for obj in parsed_objects}
        adj = self._build_adjacency(dependencies)
        dep_outbound, dep_inbound = self._build_dep_lookup(dependencies)
        self._name_lookup = {obj.name.lower(): obj.uuid for obj in parsed_objects}

        inbound_counts: dict[str, int] = defaultdict(int)
        for d in dependencies:
            inbound_counts[d.target_uuid] += 1
        hub_uuids: set[str] = {
            uid for uid, count in inbound_counts.items()
            if count >= _HUB_CALLER_THRESHOLD
            and uid in obj_map
            and obj_map[uid].object_type == 'Expression Rule'
        }

        entry_points = self._discover_entry_points(parsed_objects, obj_map)
        file_builder = BundleFileBuilder()

        bundle_assignments: dict[str, list[str]] = defaultdict(list)
        index_entries: list[dict] = []
        bundle_dicts: list[dict] = []
        used_ids: set[str] = set()

        for ep in entry_points:
            root_uuids = self._get_root_uuids(ep, obj_map)
            reachable = self._walk_deps(root_uuids, adj, stop_types={'Record Type'},
                                        obj_map=obj_map, hub_uuids=hub_uuids)
            reachable.update(root_uuids)

            bundle_objects = [obj_map[u] for u in reachable if u in obj_map]
            bundle_id = _sanitize(ep.name)
            if bundle_id in used_ids:
                counter = 2
                while f"{bundle_id}_{counter}" in used_ids:
                    counter += 1
                bundle_id = f"{bundle_id}_{counter}"
            used_ids.add(bundle_id)

            for obj in bundle_objects:
                bundle_assignments[obj.uuid].append(bundle_id)

            bundle_dict = file_builder.build(
                ep, bundle_objects, dep_outbound, dep_inbound, obj_map, bundle_id,
            )
            bundle_dicts.append(bundle_dict)

            index_entries.append({
                'id': bundle_id,
                'bundle_type': ep.bundle_type,
                'root_name': ep.name,
                'parent_name': ep.parent_name,
                'object_count': len(bundle_objects),
                'key_objects': bundle_dict.get('key_objects', []),
            })

        index_entries.sort(key=lambda e: (e['bundle_type'], e['root_name']))
        self._index_entries = index_entries
        return dict(bundle_assignments), hub_uuids, index_entries, bundle_dicts

    def build_all(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        output_dir: str,
    ) -> dict[str, list[str]]:
        """Build all bundles. Returns bundle_assignments: uuid → list[bundle_id]."""
        obj_map = {obj.uuid: obj for obj in parsed_objects}
        adj = self._build_adjacency(dependencies)
        dep_outbound, dep_inbound = self._build_dep_lookup(dependencies)

        # Build name lookup
        self._name_lookup = {obj.name.lower(): obj.uuid for obj in parsed_objects}

        # Identify hub expression rules
        inbound_counts: dict[str, int] = defaultdict(int)
        for d in dependencies:
            inbound_counts[d.target_uuid] += 1
        hub_uuids: set[str] = {
            uid for uid, count in inbound_counts.items()
            if count >= _HUB_CALLER_THRESHOLD
            and uid in obj_map
            and obj_map[uid].object_type == 'Expression Rule'
        }

        entry_points = self._discover_entry_points(parsed_objects, obj_map)
        bundles_dir = os.path.join(output_dir, 'bundles')

        bundle_assignments: dict[str, list[str]] = defaultdict(list)
        self._index_entries = []
        used_ids: set[str] = set()

        for ep in entry_points:
            root_uuids = self._get_root_uuids(ep, obj_map)
            reachable = self._walk_deps(root_uuids, adj, stop_types={'Record Type'},
                                        obj_map=obj_map, hub_uuids=hub_uuids)
            reachable.update(root_uuids)

            bundle_objects = [obj_map[u] for u in reachable if u in obj_map]
            bundle_id = _sanitize(ep.name)

            # Handle collisions by appending a counter
            if bundle_id in used_ids:
                counter = 2
                while f"{bundle_id}_{counter}" in used_ids:
                    counter += 1
                bundle_id = f"{bundle_id}_{counter}"
            used_ids.add(bundle_id)

            # Track assignments
            for obj in bundle_objects:
                bundle_assignments[obj.uuid].append(bundle_id)

            # Write structure.json
            structure = self._structure_builder.build_structure(
                ep, bundle_objects, dep_outbound, dep_inbound, obj_map,
            )
            bundle_dir = os.path.join(bundles_dir, bundle_id)
            os.makedirs(bundle_dir, exist_ok=True)
            self._write_json(os.path.join(bundle_dir, 'structure.json'), structure)

            # Write code.json
            code = self._code_builder.build_code(bundle_id, bundle_objects)
            self._write_json(os.path.join(bundle_dir, 'code.json'), code)

            # Compute key_objects: top 5 most-connected within bundle
            bundle_uuids = {o.uuid for o in bundle_objects}
            connectivity = []
            for obj in bundle_objects:
                out_c = sum(1 for d in dep_outbound.get(obj.uuid, []) if d.target_uuid in bundle_uuids)
                in_c = sum(1 for d in dep_inbound.get(obj.uuid, []) if d.source_uuid in bundle_uuids)
                connectivity.append((obj.name, out_c + in_c))
            connectivity.sort(key=lambda x: -x[1])
            key_objects = [name for name, _ in connectivity[:5]]

            self._index_entries.append({
                'id': bundle_id,
                'bundle_type': ep.bundle_type,
                'root_name': ep.name,
                'parent_name': ep.parent_name,
                'object_count': len(bundle_objects),
                'key_objects': key_objects,
            })

        self._index_entries.sort(key=lambda e: (e['bundle_type'], e['root_name']))
        return dict(bundle_assignments)

    # ── Entry point discovery ───────────────────────────────────────────

    def _discover_entry_points(
        self, parsed_objects: list[ParsedObject], obj_map: dict[str, ParsedObject],
    ) -> list[EntryPoint]:
        eps: list[EntryPoint] = []

        for obj in parsed_objects:
            otype = obj.object_type

            if otype == 'Record Type':
                for action in obj.data.get('actions', []):
                    raw_target = action.get('target_uuid')
                    target_uuid = self._resolve_target(raw_target, obj_map) if raw_target else None
                    action_name = (action.get('expressions') or {}).get('TITLE') or action.get('reference_key', 'Unknown')
                    action_name = _strip_sail_wrapper(action_name)
                    eps.append(EntryPoint(
                        uuid=target_uuid or obj.uuid,
                        name=f"{obj.name} - {action_name}",
                        object_type='Record Type Action',
                        bundle_type='action',
                        parent_name=obj.name,
                        extra={'action': action, 'record_type_uuid': obj.uuid},
                    ))

                views = obj.data.get('views', [])
                if any(v.get('ui_expr') for v in views):
                    eps.append(EntryPoint(
                        uuid=obj.uuid,
                        name=obj.name,
                        object_type='Record Type Page',
                        bundle_type='page',
                        extra={'views': views},
                    ))

            elif otype == 'Site':
                eps.append(EntryPoint(uuid=obj.uuid, name=obj.name, object_type='Site', bundle_type='site'))

            elif otype == 'Control Panel':
                eps.append(EntryPoint(uuid=obj.uuid, name=obj.name, object_type='Control Panel', bundle_type='dashboard'))

            elif otype == 'Web API':
                eps.append(EntryPoint(uuid=obj.uuid, name=obj.name, object_type='Web API', bundle_type='web_api'))

        # Standalone process models
        action_target_uuids: set[str] = set()
        for obj in parsed_objects:
            if obj.object_type == 'Record Type':
                for a in obj.data.get('actions', []):
                    raw = a.get('target_uuid')
                    if raw:
                        resolved = self._resolve_target(raw, obj_map)
                        if resolved:
                            action_target_uuids.add(resolved)

        subprocess_uuids: set[str] = set()
        for obj in parsed_objects:
            if obj.object_type == 'Process Model':
                for node in obj.data.get('nodes', []):
                    sub_uuid = node.get('subprocess_uuid')
                    if sub_uuid:
                        subprocess_uuids.add(sub_uuid)

        for obj in parsed_objects:
            if (obj.object_type == 'Process Model'
                    and obj.uuid not in action_target_uuids
                    and obj.uuid not in subprocess_uuids):
                eps.append(EntryPoint(
                    uuid=obj.uuid, name=obj.name,
                    object_type='Process Model', bundle_type='process',
                ))

        return eps

    # ── Dependency graph ────────────────────────────────────────────────

    @staticmethod
    def _build_adjacency(dependencies: list) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = defaultdict(set)
        for d in dependencies:
            adj[d.source_uuid].add(d.target_uuid)
        return adj

    @staticmethod
    def _build_dep_lookup(dependencies: list) -> tuple[dict[str, list], dict[str, list]]:
        outbound: dict[str, list] = defaultdict(list)
        inbound: dict[str, list] = defaultdict(list)
        for d in dependencies:
            outbound[d.source_uuid].append(d)
            inbound[d.target_uuid].append(d)
        return outbound, inbound

    def _get_root_uuids(self, ep: EntryPoint, obj_map: dict[str, ParsedObject]) -> set[str]:
        roots = set()
        if ep.uuid and ep.uuid in obj_map:
            roots.add(ep.uuid)

        if ep.bundle_type == 'action':
            action = ep.extra.get('action', {})
            rt_uuid = ep.extra.get('record_type_uuid')
            target = action.get('target_uuid')
            if target:
                target_uid = target if target in obj_map else self._name_lookup.get(target.lower())
                if target_uid and target_uid in obj_map:
                    roots.add(target_uid)
            for text in (action.get('expressions') or {}).values():
                if text:
                    roots.update(self._resolve_sail_refs(text, obj_map))
            if rt_uuid:
                roots.discard(rt_uuid)

        elif ep.object_type == 'Site' and ep.uuid in obj_map:
            for page in obj_map[ep.uuid].data.get('pages', []):
                self._collect_page_uuids(page, roots, obj_map)

        elif ep.object_type == 'Control Panel' and ep.uuid in obj_map:
            data = obj_map[ep.uuid].data
            for iface in data.get('interfaces', []):
                uid = iface.get('interface_uuid')
                if uid and uid in obj_map:
                    roots.add(uid)
            for cp in data.get('custom_pages', []):
                uid = cp.get('interface_uuid')
                if uid and uid in obj_map:
                    roots.add(uid)
            prt = data.get('primary_record_type_uuid')
            if prt and prt in obj_map:
                roots.add(prt)

        elif ep.bundle_type == 'page':
            for v in ep.extra.get('views', []):
                for expr_field in ('ui_expr', 'visibility_expr'):
                    expr = v.get(expr_field)
                    if expr:
                        roots.update(self._resolve_sail_refs(expr, obj_map))

        return roots

    def _resolve_sail_refs(self, text: str, obj_map: dict[str, ParsedObject]) -> set[str]:
        found: set[str] = set()
        for pattern in [RULE_REF_RE, CONS_REF_RE, TYPE_REF_RE, RECORD_TYPE_REF_RE]:
            for m in pattern.finditer(text):
                uid = self._name_lookup.get(m.group(1).lower())
                if uid:
                    found.add(uid)
        for pattern in [UUID_FULL_RE, UUID_STANDARD_RE]:
            for m in pattern.finditer(text):
                uuid = m.group(1)
                if uuid in obj_map:
                    found.add(uuid)
                else:
                    cm = CANONICAL_RE.match(uuid)
                    if cm and cm.group(1) in obj_map:
                        found.add(cm.group(1))
        return found

    def _collect_page_uuids(self, page: dict, roots: set[str], obj_map: dict) -> None:
        uid = page.get('ui_object_uuid') or page.get('target_uuid')
        if uid and uid in obj_map:
            roots.add(uid)
        for child in page.get('children', []):
            self._collect_page_uuids(child, roots, obj_map)

    def _resolve_target(self, value: str | None, obj_map: dict[str, ParsedObject]) -> str | None:
        if not value:
            return None
        if value in obj_map:
            return value
        return self._name_lookup.get(value.lower())

    @staticmethod
    def _walk_deps(
        root_uuids: set[str], adj: dict[str, set[str]],
        stop_types: set[str] | None = None,
        obj_map: dict[str, ParsedObject] | None = None,
        hub_uuids: set[str] | None = None,
    ) -> set[str]:
        visited: set[str] = set()
        queue = list(root_uuids)
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            if stop_types and obj_map and current in obj_map:
                if obj_map[current].object_type in stop_types:
                    continue
            if hub_uuids and current in hub_uuids and current not in root_uuids:
                continue
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        return visited

    # ── I/O ─────────────────────────────────────────────────────────────

    def _write_json(self, path: str, data: Any) -> None:
        indent = 2 if self._pretty else None
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, default=str)


# ── Helpers ─────────────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    s = re.sub(r'[^\w\s-]', '', name)
    s = re.sub(r'[\s]+', '_', s.strip())
    return s[:80] or 'unnamed'


def _strip_sail_wrapper(text: str | None) -> str:
    if not text:
        return 'Unknown'
    m = re.match(r'^"(.+)"$', text.strip())
    if m:
        return m.group(1)
    return text
