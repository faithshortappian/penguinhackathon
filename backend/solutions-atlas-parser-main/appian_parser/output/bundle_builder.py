"""
Builds self-contained documentation bundles per top-level entry point.

Each bundle contains the root object and its full transitive dependency tree,
giving an AI everything needed to document a complete functional flow in one file.
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
    UUID_PREFIXED_RE,
    UUID_STANDARD_RE,
)
from appian_parser.output.json_dumper import ParsedObject


# ── Configuration ───────────────────────────────────────────────────────

@dataclass
class BundleOptions:
    pretty: bool = True


# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class EntryPoint:
    """A top-level entry point that roots a bundle."""
    uuid: str
    name: str
    object_type: str
    bundle_type: str          # action, site, dashboard, web_api, process
    parent_name: str | None = None  # e.g. record type name for actions
    extra: dict = field(default_factory=dict)


_BUNDLE_TYPE_FOLDERS = {
    'action': 'actions',
    'page': 'pages',
    'site': 'sites',
    'dashboard': 'dashboards',
    'web_api': 'web_apis',
    'process': 'processes',
}

# Expression rules called by this many or more distinct objects are treated
# as shared utilities — included as leaf nodes but not expanded during BFS.
_HUB_CALLER_THRESHOLD = 20


# ── Builder ─────────────────────────────────────────────────────────────

class BundleBuilder:
    """Builds self-contained documentation bundles per entry point."""

    def __init__(self, options: BundleOptions | None = None):
        self.options = options or BundleOptions()
        self._name_lookup: dict[str, str] = {}

    def build_and_write(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        manifest: dict[str, Any],
        output_dir: str,
    ) -> str:
        """Build all bundles and write to output_dir/bundles/. Returns bundles dir path."""
        obj_map = {obj.uuid: obj for obj in parsed_objects}
        adj = self._build_adjacency(dependencies)
        dep_outbound, dep_inbound = self._build_dep_lookup(dependencies)

        # Build name lookup for SAIL reference resolution
        self._name_lookup: dict[str, str] = {}
        for obj in parsed_objects:
            self._name_lookup[obj.name.lower()] = obj.uuid

        # Identify hub expression rules (called by many objects) — these are
        # shared utilities whose transitive deps bloat bundles without adding
        # business context.  Include them as leaves but don't expand.
        inbound_counts: dict[str, int] = defaultdict(int)
        for d in dependencies:
            inbound_counts[d.target_uuid] += 1
        self._hub_uuids: set[str] = {
            uid for uid, count in inbound_counts.items()
            if count >= _HUB_CALLER_THRESHOLD
            and uid in obj_map
            and obj_map[uid].object_type == 'Expression Rule'
        }

        entry_points = self._discover_entry_points(parsed_objects, obj_map)
        bundles_dir = os.path.join(output_dir, 'bundles')

        index_entries = []
        bundled_uuids: set[str] = set()

        for ep in entry_points:
            # Walk transitive deps from the entry point's root
            root_uuids = self._get_root_uuids(ep, obj_map)
            # Don't expand Record Type nodes — they are reference data hubs
            # that cause massive fan-out. Include them as leaves but don't
            # follow their outbound edges.
            reachable = self._walk_deps(root_uuids, adj, stop_types={'Record Type'}, obj_map=obj_map,
                                        hub_uuids=self._hub_uuids)
            reachable.update(root_uuids)
            bundled_uuids.update(reachable)

            # Collect objects
            bundle_objects = [obj_map[u] for u in reachable if u in obj_map]

            # Build bundle content
            bundle = self._build_bundle(ep, bundle_objects, dep_outbound, dep_inbound, obj_map)

            # Write
            subdir = os.path.join(bundles_dir, _BUNDLE_TYPE_FOLDERS.get(ep.bundle_type, ep.bundle_type + 's'))
            os.makedirs(subdir, exist_ok=True)
            filename = _sanitize(ep.name) + '.json'
            filepath = os.path.join(subdir, filename)
            self._write_json(filepath, bundle)

            index_entries.append({
                'file': f"{_BUNDLE_TYPE_FOLDERS.get(ep.bundle_type, ep.bundle_type + 's')}/{filename}",
                'bundle_type': ep.bundle_type,
                'root_name': ep.name,
                'root_object_type': ep.object_type,
                'parent_name': ep.parent_name,
                'object_count': len(bundle_objects),
            })

        # Build and write index
        index = self._build_index(index_entries, parsed_objects, bundled_uuids, manifest)
        os.makedirs(bundles_dir, exist_ok=True)
        self._write_json(os.path.join(bundles_dir, '_index.json'), index)

        # Write orphaned objects (not reachable from any entry point)
        orphans = [obj for obj in parsed_objects if obj.uuid not in bundled_uuids]
        if orphans:
            by_type: dict[str, list[dict]] = defaultdict(list)
            for obj in orphans:
                by_type[_type_to_key(obj.object_type)].append({
                    'uuid': obj.uuid,
                    'name': obj.name,
                    'object_type': obj.object_type,
                    'description': obj.data.get('description'),
                    'data': _extract_type_data(obj),
                })
            self._write_json(os.path.join(bundles_dir, '_orphans.json'), {
                '_metadata': {
                    'description': 'Objects not reachable from any entry point (action, site, dashboard, web API, or standalone process).',
                    'total_objects': len(orphans),
                },
                'objects': dict(by_type),
            })

        return bundles_dir

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
                    # target_uuid may be resolved to a name by ReferenceResolver
                    target_uuid = self._resolve_target(raw_target, obj_map) if raw_target else None
                    action_name = (action.get('expressions') or {}).get('TITLE') or action.get('reference_key', 'Unknown')
                    # Strip SAIL wrapper if present
                    action_name = _strip_sail_wrapper(action_name)
                    eps.append(EntryPoint(
                        uuid=target_uuid or obj.uuid,
                        name=f"{obj.name} - {action_name}",
                        object_type='Record Type Action',
                        bundle_type='action',
                        parent_name=obj.name,
                        extra={'action': action, 'record_type_uuid': obj.uuid},
                    ))

                # Page bundle: record type summary/detail views with their interfaces
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
                eps.append(EntryPoint(
                    uuid=obj.uuid,
                    name=obj.name,
                    object_type='Site',
                    bundle_type='site',
                ))

            elif otype == 'Control Panel':
                eps.append(EntryPoint(
                    uuid=obj.uuid,
                    name=obj.name,
                    object_type='Control Panel',
                    bundle_type='dashboard',
                ))

            elif otype == 'Web API':
                eps.append(EntryPoint(
                    uuid=obj.uuid,
                    name=obj.name,
                    object_type='Web API',
                    bundle_type='web_api',
                ))

        # Standalone process models: PMs not targeted by any record action
        action_target_uuids: set[str] = set()
        for obj in parsed_objects:
            if obj.object_type == 'Record Type':
                for a in obj.data.get('actions', []):
                    raw = a.get('target_uuid')
                    if raw:
                        resolved = self._resolve_target(raw, obj_map)
                        if resolved:
                            action_target_uuids.add(resolved)
        # Also exclude PMs that are subprocesses of other PMs
        subprocess_uuids: set[str] = set()
        for obj in parsed_objects:
            if obj.object_type == 'Process Model':
                for node in obj.data.get('nodes', []):
                    sub_uuid = node.get('subprocess_uuid')
                    if sub_uuid:
                        subprocess_uuids.add(sub_uuid)

        for obj in parsed_objects:
            if obj.object_type == 'Process Model' and obj.uuid not in action_target_uuids and obj.uuid not in subprocess_uuids:
                eps.append(EntryPoint(
                    uuid=obj.uuid,
                    name=obj.name,
                    object_type='Process Model',
                    bundle_type='process',
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
        """Map source_uuid -> outbound deps and target_uuid -> inbound deps."""
        outbound: dict[str, list] = defaultdict(list)
        inbound: dict[str, list] = defaultdict(list)
        for d in dependencies:
            outbound[d.source_uuid].append(d)
            inbound[d.target_uuid].append(d)
        return outbound, inbound

    def _get_root_uuids(self, ep: EntryPoint, obj_map: dict[str, ParsedObject]) -> set[str]:
        """Get the set of UUIDs to start the graph walk from."""
        roots = set()
        if ep.uuid and ep.uuid in obj_map:
            roots.add(ep.uuid)

        if ep.bundle_type == 'action':
            # For actions: only the target PM + refs from action expressions.
            # Do NOT include the record type — it pulls in all views/actions.
            action = ep.extra.get('action', {})
            rt_uuid = ep.extra.get('record_type_uuid')
            target = action.get('target_uuid')
            if target:
                # target_uuid may be resolved to a name by ReferenceResolver
                target_uid = target if target in obj_map else self._name_lookup.get(target.lower())
                if target_uid and target_uid in obj_map:
                    roots.add(target_uid)
            # Resolve references from the action's own SAIL expressions
            for text in (action.get('expressions') or {}).values():
                if text:
                    roots.update(self._resolve_sail_refs(text, obj_map, self._name_lookup))
            # Exclude the parent record type — its closure is too broad
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
            # For page bundles: only the view interfaces, not the full record type
            for v in ep.extra.get('views', []):
                ui_expr = v.get('ui_expr')
                if ui_expr:
                    roots.update(self._resolve_sail_refs(ui_expr, obj_map, self._name_lookup))
                vis_expr = v.get('visibility_expr')
                if vis_expr:
                    roots.update(self._resolve_sail_refs(vis_expr, obj_map, self._name_lookup))

        return roots

    @staticmethod
    def _resolve_sail_refs(text: str, obj_map: dict[str, ParsedObject], name_lookup: dict[str, str] | None = None) -> set[str]:
        """Extract object UUIDs referenced in a SAIL expression string."""
        found: set[str] = set()
        nl = name_lookup or {}

        for pattern in [RULE_REF_RE, CONS_REF_RE, TYPE_REF_RE, RECORD_TYPE_REF_RE]:
            for m in pattern.finditer(text):
                uid = nl.get(m.group(1).lower())
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

    @staticmethod
    def _walk_deps(root_uuids: set[str], adj: dict[str, set[str]], stop_types: set[str] | None = None,
                   obj_map: dict[str, ParsedObject] | None = None,
                   hub_uuids: set[str] | None = None) -> set[str]:
        """BFS to collect all transitively reachable UUIDs.

        Args:
            stop_types: If provided, include objects of these types but don't
                        follow their outbound edges (they act as leaf nodes).
        """
        visited: set[str] = set()
        queue = list(root_uuids)
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            # Don't expand stop-type nodes (include them but don't follow edges)
            if stop_types and obj_map and current in obj_map:
                if obj_map[current].object_type in stop_types:
                    continue
            # Don't expand hub utility rules
            if hub_uuids and current in hub_uuids and current not in root_uuids:
                continue
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        return visited

    # ── Bundle assembly ─────────────────────────────────────────────────

    def _build_bundle(
        self,
        ep: EntryPoint,
        objects: list[ParsedObject],
        dep_outbound: dict[str, list],
        dep_inbound: dict[str, list],
        obj_map: dict[str, ParsedObject],
    ) -> dict[str, Any]:
        bundle_uuids = {o.uuid for o in objects}
        obj_index = {o.uuid: o for o in objects}

        base = {
            '_metadata': {
                'bundle_type': ep.bundle_type,
                'root_object': {
                    'uuid': ep.uuid,
                    'name': ep.name,
                    'object_type': ep.object_type,
                    'parent_name': ep.parent_name,
                },
                'total_objects': len(objects),
            },
        }

        builder = {
            'action': self._build_action_bundle,
            'process': self._build_process_bundle,
            'page': self._build_page_bundle,
            'site': self._build_site_bundle,
            'dashboard': self._build_dashboard_bundle,
            'web_api': self._build_web_api_bundle,
        }.get(ep.bundle_type, self._build_generic_bundle)

        base.update(builder(ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map))
        return base

    # ── Type-specific bundle builders ───────────────────────────────────

    def _resolve_target(self, value: str | None, obj_map: dict[str, ParsedObject]) -> str | None:
        """Resolve a target that may be a UUID or a resolved name back to a UUID."""
        if not value:
            return None
        if value in obj_map:
            return value
        return self._name_lookup.get(value.lower())

    def _build_action_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        action = ep.extra.get('action', {})
        target_uuid = self._resolve_target(action.get('target_uuid'), obj_map)

        # Section 1: Action metadata
        action_section = {
            'name': ep.name,
            'record_type': ep.parent_name,
            'action_type': action.get('action_type'),
            'reference_key': action.get('reference_key'),
            'icon_id': action.get('icon_id'),
            'dialog_size': action.get('dialog_size'),
            'security': action.get('record_ui_security_type'),
            'expressions': action.get('expressions'),
        }

        # Section 2: Interface (form) — the PM's start form + sub-interfaces
        pm_obj = obj_map.get(target_uuid) if target_uuid else None
        form_uuid = None
        if pm_obj:
            # Check PM-level start form first
            sf_uuid = pm_obj.data.get('start_form_interface_uuid')
            if sf_uuid:
                form_uuid = self._resolve_target(sf_uuid, obj_map)
            # Fall back to first node with interface_uuid
            if not form_uuid:
                for node in pm_obj.data.get('nodes', []):
                    if node.get('interface_uuid'):
                        form_uuid = self._resolve_target(node['interface_uuid'], obj_map)
                        if form_uuid:
                            break

        interfaces = [o for o in objects if o.object_type == 'Interface']
        form_interface = None
        sub_interfaces = []
        for iface in interfaces:
            entry = _obj_entry(iface, bundle_uuids, dep_outbound, dep_inbound)
            if iface.uuid == form_uuid:
                form_interface = entry
            else:
                sub_interfaces.append(entry)

        interface_section = {
            'entry_form': form_interface,
            'sub_interfaces': sorted(sub_interfaces, key=lambda x: x['name']),
        }

        # Section 3: Process flow — PM + subprocesses + supporting objects
        process_section: dict[str, Any] = {}
        if pm_obj:
            process_section['process_model'] = _obj_entry(pm_obj, bundle_uuids, dep_outbound, dep_inbound)

        subprocesses = [o for o in objects if o.object_type == 'Process Model' and o.uuid != (target_uuid or '')]
        if subprocesses:
            process_section['subprocesses'] = [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in subprocesses]

        # Supporting objects: everything that isn't an interface or PM
        skip_uuids = {o.uuid for o in interfaces} | {o.uuid for o in objects if o.object_type == 'Process Model'}
        supporting = _group_by_type([o for o in objects if o.uuid not in skip_uuids], bundle_uuids, dep_outbound, dep_inbound)
        if supporting:
            process_section['supporting_objects'] = supporting

        return {
            'action': action_section,
            'interface': interface_section,
            'process': process_section,
        }

    def _build_process_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        pm_obj = obj_map.get(ep.uuid)

        # Section 1: Process model
        process_section: dict[str, Any] = {}
        if pm_obj:
            process_section['process_model'] = _obj_entry(pm_obj, bundle_uuids, dep_outbound, dep_inbound)

        subprocesses = [o for o in objects if o.object_type == 'Process Model' and o.uuid != ep.uuid]
        if subprocesses:
            process_section['subprocesses'] = [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in subprocesses]

        # Section 2: Interfaces used by the PM
        interfaces = [o for o in objects if o.object_type == 'Interface']
        interface_section = [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in interfaces] if interfaces else []

        # Section 3: Supporting objects
        skip_uuids = {o.uuid for o in interfaces} | {o.uuid for o in objects if o.object_type == 'Process Model'}
        supporting = _group_by_type([o for o in objects if o.uuid not in skip_uuids], bundle_uuids, dep_outbound, dep_inbound)

        return {
            'process': process_section,
            'interfaces': sorted(interface_section, key=lambda x: x['name']),
            'supporting_objects': supporting,
        }

    def _build_page_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        views = ep.extra.get('views', [])

        # Section 1: View definitions
        view_section = [
            {
                'view_type': v.get('view_type'),
                'view_name': v.get('view_name'),
                'url_stub': v.get('url_stub'),
                'ui_expr': v.get('ui_expr'),
            }
            for v in views if v.get('ui_expr')
        ]

        # Section 2: Interfaces
        interfaces = [o for o in objects if o.object_type == 'Interface']
        interface_section = [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in interfaces]

        # Section 3: Supporting objects
        skip_uuids = {o.uuid for o in interfaces}
        supporting = _group_by_type([o for o in objects if o.uuid not in skip_uuids], bundle_uuids, dep_outbound, dep_inbound)

        return {
            'views': view_section,
            'interfaces': sorted(interface_section, key=lambda x: x['name']),
            'supporting_objects': supporting,
        }

    def _build_site_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        site_obj = obj_map.get(ep.uuid)
        site_section: dict[str, Any] = {}
        if site_obj:
            site_section = {
                'url_stub': site_obj.data.get('url_stub'),
                'pages': _compact_pages(site_obj.data.get('pages', [])),
                'branding': {k: site_obj.data.get(k) for k in [
                    'display_name', 'header_background_color_expr',
                    'accent_color_expr', 'logo_expr',
                ] if site_obj.data.get(k)},
            }

        # Page targets and their deps
        skip_uuids = {ep.uuid} if ep.uuid else set()
        interfaces = [o for o in objects if o.object_type == 'Interface' and o.uuid not in skip_uuids]
        remaining = [o for o in objects if o.uuid not in skip_uuids and o.object_type != 'Interface']
        supporting = _group_by_type(remaining, bundle_uuids, dep_outbound, dep_inbound)

        return {
            'site': site_section,
            'interfaces': [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in interfaces],
            'supporting_objects': supporting,
        }

    def _build_dashboard_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        cp_obj = obj_map.get(ep.uuid)
        dashboard_section: dict[str, Any] = {}
        if cp_obj:
            dashboard_section = {
                'url_stub': cp_obj.data.get('url_stub'),
                'primary_record_type': cp_obj.data.get('primary_record_display_name'),
                'settings': cp_obj.data.get('settings_json_raw'),
            }

        skip_uuids = {ep.uuid} if ep.uuid else set()
        interfaces = [o for o in objects if o.object_type == 'Interface' and o.uuid not in skip_uuids]
        remaining = [o for o in objects if o.uuid not in skip_uuids and o.object_type != 'Interface']
        supporting = _group_by_type(remaining, bundle_uuids, dep_outbound, dep_inbound)

        return {
            'dashboard': dashboard_section,
            'interfaces': [_obj_entry(o, bundle_uuids, dep_outbound, dep_inbound) for o in interfaces],
            'supporting_objects': supporting,
        }

    def _build_web_api_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        wa_obj = obj_map.get(ep.uuid)
        api_section: dict[str, Any] = {}
        if wa_obj:
            api_section = {
                'url_alias': wa_obj.data.get('url_alias'),
                'http_method': wa_obj.data.get('http_method'),
                'sail_code': wa_obj.data.get('sail_code'),
                'security': wa_obj.data.get('security'),
            }

        skip_uuids = {ep.uuid} if ep.uuid else set()
        supporting = _group_by_type([o for o in objects if o.uuid not in skip_uuids], bundle_uuids, dep_outbound, dep_inbound)

        return {
            'web_api': api_section,
            'supporting_objects': supporting,
        }

    def _build_generic_bundle(
        self, ep, objects, obj_index, bundle_uuids, dep_outbound, dep_inbound, obj_map,
    ) -> dict[str, Any]:
        return {
            'entry_point': self._build_entry_point_detail(ep, obj_map),
            'objects': _group_by_type(objects, bundle_uuids, dep_outbound, dep_inbound),
        }

    def _build_entry_point_detail(self, ep: EntryPoint, obj_map: dict[str, ParsedObject]) -> dict[str, Any]:
        """Build detailed info about the entry point itself."""
        detail: dict[str, Any] = {
            'name': ep.name,
            'bundle_type': ep.bundle_type,
            'object_type': ep.object_type,
        }

        if ep.bundle_type == 'action':
            action = ep.extra.get('action', {})
            detail['action_type'] = action.get('action_type')
            detail['expressions'] = action.get('expressions')
            target_uuid = action.get('target_uuid')
            if target_uuid and target_uuid in obj_map:
                pm = obj_map[target_uuid]
                detail['process_model'] = pm.name
            detail['record_type'] = ep.parent_name

        elif ep.bundle_type == 'site' and ep.uuid in obj_map:
            site = obj_map[ep.uuid]
            detail['url_stub'] = site.data.get('url_stub')
            detail['pages'] = _compact_pages(site.data.get('pages', []))

        elif ep.bundle_type == 'dashboard' and ep.uuid in obj_map:
            cp = obj_map[ep.uuid]
            detail['url_stub'] = cp.data.get('url_stub')
            detail['primary_record_type'] = cp.data.get('primary_record_display_name')

        elif ep.bundle_type == 'web_api' and ep.uuid in obj_map:
            wa = obj_map[ep.uuid]
            detail['url_alias'] = wa.data.get('url_alias')
            detail['http_method'] = wa.data.get('http_method')

        elif ep.bundle_type == 'process' and ep.uuid in obj_map:
            pm = obj_map[ep.uuid]
            detail['complexity_score'] = pm.data.get('complexity_score')
            detail['total_nodes'] = pm.data.get('total_nodes')

        elif ep.bundle_type == 'page' and ep.uuid in obj_map:
            rt = obj_map[ep.uuid]
            detail['record_type'] = rt.name
            detail['description'] = rt.data.get('description')
            detail['views'] = [
                {
                    'view_type': v.get('view_type'),
                    'view_name': v.get('view_name'),
                    'url_stub': v.get('url_stub'),
                    'ui_expr': v.get('ui_expr'),
                }
                for v in ep.extra.get('views', [])
                if v.get('ui_expr')
            ]

        return detail

    # ── Index ───────────────────────────────────────────────────────────

    @staticmethod
    def _build_index(
        entries: list[dict],
        all_objects: list[ParsedObject],
        bundled_uuids: set[str],
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        orphaned = len(all_objects) - len(bundled_uuids)

        return {
            '_metadata': {
                'description': (
                    'Index of all documentation bundles. Each bundle is a self-contained '
                    'file with a top-level entry point and its full transitive dependency tree.'
                ),
            },
            'app_overview': {
                'package_info': manifest.get('package_info', {}),
                'object_counts': manifest.get('object_inventory', {}).get('total_by_type', {}),
            },
            'coverage': {
                'total_objects': len(all_objects),
                'objects_in_bundles': len(bundled_uuids),
                'orphaned_count': orphaned,
            },
            'bundles': sorted(entries, key=lambda e: (e['bundle_type'], e['root_name'])),
        }

    # ── I/O ─────────────────────────────────────────────────────────────

    def _write_json(self, path: str, data: Any) -> None:
        indent = 2 if self.options.pretty else None
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, default=str)


# ── Helpers ─────────────────────────────────────────────────────────────

def _extract_type_data(obj: ParsedObject) -> dict[str, Any]:
    """Extract the relevant type-specific fields from parsed data (exclude common envelope fields)."""
    skip = {'uuid', 'name', 'version_uuid', 'description'}
    return {k: v for k, v in obj.data.items() if k not in skip and v is not None}


def _obj_entry(
    obj: ParsedObject,
    bundle_uuids: set[str],
    dep_outbound: dict[str, list],
    dep_inbound: dict[str, list],
) -> dict[str, Any]:
    """Build a single object entry with scoped dependency info."""
    calls = [d.target_name for d in dep_outbound.get(obj.uuid, []) if d.target_uuid in bundle_uuids]
    called_by = [d.source_name for d in dep_inbound.get(obj.uuid, []) if d.source_uuid in bundle_uuids]
    return {
        'uuid': obj.uuid,
        'name': obj.name,
        'object_type': obj.object_type,
        'description': obj.data.get('description'),
        'data': _extract_type_data(obj),
        'calls': sorted(set(calls)),
        'called_by': sorted(set(called_by)),
    }


def _group_by_type(
    objects: list[ParsedObject],
    bundle_uuids: set[str],
    dep_outbound: dict[str, list],
    dep_inbound: dict[str, list],
) -> dict[str, list[dict]]:
    """Group objects by type key, each with dependency info."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for obj in objects:
        by_type[_type_to_key(obj.object_type)].append(
            _obj_entry(obj, bundle_uuids, dep_outbound, dep_inbound)
        )
    return dict(by_type)


_TYPE_KEY_MAP = {
    'Expression Rule': 'expression_rules',
    'Interface': 'interfaces',
    'Process Model': 'processes',
    'Record Type': 'record_types',
    'CDT': 'cdts',
    'Constant': 'constants',
    'Integration': 'integrations',
    'Connected System': 'connected_systems',
    'Web API': 'web_apis',
    'Site': 'sites',
    'Group': 'groups',
    'Control Panel': 'control_panels',
    'Translation Set': 'translation_sets',
    'Translation String': 'translation_strings',
    'Data Type': 'data_types',
}


def _type_to_key(object_type: str) -> str:
    return _TYPE_KEY_MAP.get(object_type, object_type.lower().replace(' ', '_') + 's')


def _sanitize(name: str) -> str:
    """Sanitize a name for use as a filename."""
    s = re.sub(r'[^\w\s-]', '', name)
    s = re.sub(r'[\s]+', '_', s.strip())
    return s[:80] or 'unnamed'


def _strip_sail_wrapper(text: str | None) -> str:
    """Strip common SAIL wrappers like a!textField(value: \"X\") to just X."""
    if not text:
        return 'Unknown'
    # If it's a quoted string literal, extract it
    m = re.match(r'^"(.+)"$', text.strip())
    if m:
        return m.group(1)
    return text


def _compact_pages(pages: list[dict]) -> list[dict]:
    """Recursively compact page structures."""
    result = []
    for p in pages:
        page = {
            'name': p.get('static_name') or p.get('name_expr'),
            'url_stub': p.get('url_stub'),
            'ui_object_uuid': p.get('ui_object_uuid'),
        }
        children = p.get('children', [])
        if children:
            page['children'] = _compact_pages(children)
        result.append(page)
    return result
