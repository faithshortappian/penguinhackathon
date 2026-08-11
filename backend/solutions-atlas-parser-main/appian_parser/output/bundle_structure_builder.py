"""Builds lightweight bundle structure files (no code)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from appian_parser.domain.models import ParsedObject
from appian_parser.parsers.write_extractor import (
    build_cdt_table_index,
    build_constant_entity_index,
    build_entity_cdt_index,
    extract_node_writes,
)


# Fields that contain SAIL code — excluded from structure objects
_CODE_FIELDS = {
    'sail_code', 'definition', 'form_expression', 'start_form_expression',
    'test_inputs', 'test_cases', 'settings_json_raw', 'request_body',
}

# Simplified node type mapping
_NODE_TYPE_MAP = {
    'Start Event': 'START_EVENT',
    'End Event': 'END_EVENT',
    'Terminate Event': 'TERMINATE_EVENT',
    'XOR Gateway': 'XOR_GATEWAY',
    'AND Gateway': 'AND_GATEWAY',
    'OR Gateway': 'OR_GATEWAY',
    'Subprocess': 'SUBPROCESS',
    # Write smart services kept distinct so the coverage gate can see writes
    # (previously flattened to SCRIPT_TASK, which dropped write identity).
    'Write Records': 'WRITE_RECORDS',
    'Write to Data Store Entity': 'WRITE_DSE',
    'Write to Multiple DSE': 'WRITE_DSE',
    'Script Task': 'SCRIPT_TASK',
    'User Input Task': 'USER_TASK',
    'Send E-Mail': 'SCRIPT_TASK',
    'Raise Error Event': 'ERROR_EVENT',
}


class BundleStructureBuilder:
    """Builds lightweight bundle structure files (no code)."""

    def build_structure(
        self,
        entry_point: Any,
        objects: list[ParsedObject],
        dep_outbound: dict[str, list],
        dep_inbound: dict[str, list],
        obj_map: dict[str, ParsedObject],
    ) -> dict[str, Any]:
        bundle_uuids = {o.uuid for o in objects}

        metadata = {
            'bundle_type': entry_point.bundle_type,
            'root_name': entry_point.name,
            'parent_name': entry_point.parent_name,
            'total_objects': len(objects),
        }

        ep_detail = self._build_entry_point(entry_point, obj_map)
        flow = self._build_flow(entry_point, objects, obj_map)
        obj_entries = [
            self._build_object_entry(o, bundle_uuids, dep_outbound, dep_inbound)
            for o in objects
        ]

        return {
            '_metadata': metadata,
            'entry_point': ep_detail,
            'flow': flow,
            'objects': sorted(obj_entries, key=lambda x: (x['type'], x['name'])),
        }

    # ── Entry point ─────────────────────────────────────────────────────

    def _build_entry_point(self, ep: Any, obj_map: dict[str, ParsedObject]) -> dict[str, Any]:
        detail: dict[str, Any] = {}

        if ep.bundle_type == 'action':
            action = ep.extra.get('action', {})
            target_uuid = action.get('target_uuid')
            # target may be UUID or resolved name
            pm = obj_map.get(target_uuid) if target_uuid else None
            if not pm and target_uuid:
                for o in obj_map.values():
                    if o.object_type == 'Process Model' and o.name == target_uuid:
                        pm = o
                        break
            detail['action_type'] = action.get('action_type')
            detail['record_type'] = ep.parent_name
            detail['target_process'] = pm.name if pm else target_uuid
            # Find form interface
            if pm:
                form_uuid = pm.data.get('start_form_interface_uuid')
                form_obj = obj_map.get(form_uuid) if form_uuid else None
                if not form_obj and form_uuid:
                    for o in obj_map.values():
                        if o.name == form_uuid:
                            form_obj = o
                            break
                detail['form_interface'] = form_obj.name if form_obj else form_uuid
            detail['expressions'] = action.get('expressions')

        elif ep.bundle_type == 'process' and ep.uuid in obj_map:
            pm = obj_map[ep.uuid]
            detail['complexity_score'] = pm.data.get('complexity_score')
            detail['total_nodes'] = pm.data.get('total_nodes')
            sf = pm.data.get('start_form_interface_uuid')
            detail['start_form'] = obj_map[sf].name if sf and sf in obj_map else sf

        elif ep.bundle_type == 'page':
            detail['record_type'] = ep.parent_name or (obj_map[ep.uuid].name if ep.uuid in obj_map else None)
            detail['views'] = [
                {'view_type': v.get('view_type'), 'view_name': v.get('view_name'), 'url_stub': v.get('url_stub')}
                for v in ep.extra.get('views', []) if v.get('ui_expr')
            ]

        elif ep.bundle_type == 'site' and ep.uuid in obj_map:
            site = obj_map[ep.uuid]
            detail['url_stub'] = site.data.get('url_stub')
            detail['pages'] = _compact_pages(site.data.get('pages', []))

        elif ep.bundle_type == 'dashboard' and ep.uuid in obj_map:
            cp = obj_map[ep.uuid]
            detail['url_stub'] = cp.data.get('url_stub')
            detail['primary_record_type'] = cp.data.get('primary_record_display_name')
            detail['interfaces'] = [
                i.get('interface_name') or i.get('interface_uuid')
                for i in cp.data.get('interfaces', [])
            ]

        elif ep.bundle_type == 'web_api' and ep.uuid in obj_map:
            wa = obj_map[ep.uuid]
            detail['http_method'] = wa.data.get('http_method')
            detail['url_alias'] = wa.data.get('url_alias')
            detail['security'] = wa.data.get('security')

        return detail

    # ── Flow ────────────────────────────────────────────────────────────

    def _build_flow(
        self, ep: Any, objects: list[ParsedObject], obj_map: dict[str, ParsedObject],
    ) -> dict[str, Any] | None:
        """Build simplified flow graph for bundles that have process models."""
        pm_obj = None
        if ep.bundle_type == 'action':
            target = ep.extra.get('action', {}).get('target_uuid')
            if target:
                # target may be a UUID or a resolved name
                pm_obj = obj_map.get(target)
                if not pm_obj:
                    # Search by name in bundle objects
                    for o in objects:
                        if o.object_type == 'Process Model' and o.name == target:
                            pm_obj = o
                            break
        elif ep.bundle_type == 'process':
            pm_obj = obj_map.get(ep.uuid)

        if not pm_obj or pm_obj.object_type != 'Process Model':
            return None

        # Resolution indexes for write extraction, built once from all objects:
        #   cons!NAME -> entity_uuid -> cdt_type -> table
        all_objs = list(obj_map.values())
        write_indexes = {
            'constant_entity_index': build_constant_entity_index(all_objs),
            'entity_cdt_index': build_entity_cdt_index(all_objs),
            'cdt_table_index': build_cdt_table_index(all_objs),
        }

        subprocesses = [
            o for o in objects
            if o.object_type == 'Process Model' and o.uuid != pm_obj.uuid
        ]

        result: dict[str, Any] = {
            'process_model': self._build_flow_graph(pm_obj, obj_map, write_indexes),
        }
        if subprocesses:
            result['subprocesses'] = [
                self._build_flow_graph(sp, obj_map, write_indexes) for sp in subprocesses
            ]
        return result

    def _build_flow_graph(
        self,
        pm: ParsedObject,
        obj_map: dict[str, ParsedObject],
        write_indexes: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Transform raw PM data into a simplified directed graph."""
        write_indexes = write_indexes or {}
        data = pm.data
        nodes = data.get('nodes', [])
        flows = data.get('flows', [])

        # Build lookup: both node_id and gui_id → node
        id_to_node: dict[str, dict] = {}
        for n in nodes:
            id_to_node[n['node_id']] = n
            id_to_node[str(n.get('gui_id', ''))] = n

        # Build adjacency from flows
        outgoing: dict[str, list[dict]] = defaultdict(list)
        for fl in flows:
            outgoing[fl['from_node_id']].append(fl)

        graph_nodes = []
        for n in nodes:
            node_entry: dict[str, Any] = {
                'name': n.get('node_name', 'Unknown'),
                'type': _NODE_TYPE_MAP.get(n.get('node_type_name', ''), n.get('node_type_name', 'UNKNOWN')),
            }

            # Resolve next nodes
            next_names = []
            for fl in outgoing.get(n['node_id'], []):
                target = id_to_node.get(fl['to_node_id'])
                if target:
                    label = fl.get('flow_label')
                    next_names.append(f"{target['node_name']} ({label})" if label else target['node_name'])
            if next_names:
                node_entry['next'] = next_names

            # Data-write targets (RECORD + CDT) — deterministic coverage signal
            writes = extract_node_writes(n, **write_indexes)
            if writes:
                node_entry['writes'] = writes

            # Gateway branch conditions (already parsed; surfaced here so the
            # coverage gate can resolve a concrete path). Resolve the target
            # node name where possible.
            gateway_conditions = n.get('gateway_conditions') or []
            if gateway_conditions:
                resolved = []
                for c in gateway_conditions:
                    target = id_to_node.get(str(c.get('target_gui_id', '')))
                    resolved.append({
                        'condition': c.get('condition'),
                        'label': c.get('label'),
                        'to': target['node_name'] if target else c.get('target_gui_id'),
                        'is_default': c.get('is_default', False),
                    })
                node_entry['gateway_conditions'] = resolved

            # Subprocess reference
            if n.get('subprocess_uuid'):
                sp = obj_map.get(n['subprocess_uuid'])
                node_entry['subprocess'] = sp.name if sp else n['subprocess_uuid']

            # Interface reference
            if n.get('interface_uuid'):
                iface = obj_map.get(n['interface_uuid'])
                node_entry['interface'] = iface.name if iface else n['interface_uuid']

            graph_nodes.append(node_entry)

        return {
            'name': pm.name,
            'complexity_score': data.get('complexity_score'),
            'total_nodes': data.get('total_nodes'),
            'nodes': graph_nodes,
        }

    # ── Object entries ──────────────────────────────────────────────────

    @staticmethod
    def _build_object_entry(
        obj: ParsedObject,
        bundle_uuids: set[str],
        dep_outbound: dict[str, list],
        dep_inbound: dict[str, list],
    ) -> dict[str, Any]:
        calls = sorted({d.target_name for d in dep_outbound.get(obj.uuid, []) if d.target_uuid in bundle_uuids})
        called_by = sorted({d.source_name for d in dep_inbound.get(obj.uuid, []) if d.source_uuid in bundle_uuids})

        entry: dict[str, Any] = {
            'uuid': obj.uuid,
            'name': obj.name,
            'type': obj.object_type,
            'description': obj.data.get('description'),
        }

        # Promote type-specific fields (no code)
        _promote_fields(entry, obj)

        entry['calls'] = calls
        entry['called_by'] = called_by
        return entry


def _promote_fields(entry: dict, obj: ParsedObject) -> None:
    """Promote type-specific fields to top level, excluding code."""
    data = obj.data
    otype = obj.object_type

    if otype in ('Interface', 'Expression Rule'):
        entry['parameters'] = data.get('parameters', [])
    elif otype == 'Record Type':
        actions = data.get('actions', [])
        entry['actions'] = [a.get('reference_key', 'Unknown') for a in actions]
        views = data.get('views', [])
        entry['views'] = [v.get('view_name') or v.get('view_type', 'Unknown') for v in views]
    elif otype == 'CDT':
        entry['fields'] = [
            {'name': f.get('name'), 'type': f.get('type')}
            for f in data.get('fields', [])
        ]
    elif otype == 'Constant':
        entry['value'] = data.get('value')
        entry['value_type'] = data.get('value_type')
    elif otype == 'Integration':
        entry['connected_system'] = data.get('connected_system_name') or data.get('connected_system_uuid')
        entry['http_method'] = data.get('http_method')
    elif otype == 'Web API':
        entry['url_alias'] = data.get('url_alias')
        entry['http_method'] = data.get('http_method')
    elif otype == 'Connected System':
        entry['system_type'] = data.get('system_type')
        entry['base_url'] = data.get('base_url')
    elif otype == 'Site':
        entry['url_stub'] = data.get('url_stub')
    elif otype == 'Control Panel':
        entry['url_stub'] = data.get('url_stub')


def _compact_pages(pages: list[dict]) -> list[dict]:
    """Recursively compact page structures."""
    result = []
    for p in pages:
        page: dict[str, Any] = {
            'name': p.get('static_name') or p.get('name_expr'),
            'url_stub': p.get('url_stub'),
        }
        children = p.get('children', [])
        if children:
            page['children'] = _compact_pages(children)
        result.append(page)
    return result
