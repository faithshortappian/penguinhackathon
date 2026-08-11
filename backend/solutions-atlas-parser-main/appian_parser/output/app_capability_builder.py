"""Builds a compact capability inventory from bundle entry points."""

from collections import defaultdict

from appian_parser.domain.name_utils import (
    clean_action_name,
    humanize_object_name,
    humanize_record_name,
)


def extract_capabilities(bundle_entries: list[dict]) -> list[dict]:
    """Build capability inventory grouped by record type, site, web API, process."""
    capabilities: list[dict] = []

    # Group actions by parent record type
    actions_by_parent: dict[str, list[str]] = defaultdict(list)
    for entry in bundle_entries:
        if entry.get('bundle_type') == 'action':
            parent = entry.get('parent_name', '')
            action_name = entry.get('root_name', '')
            if ' - ' in action_name:
                action_name = action_name.split(' - ', 1)[1]
            if action_name.startswith('#"urn:'):
                action_name = ''
            if parent:
                actions_by_parent[parent].append(action_name)

    for parent, actions in sorted(actions_by_parent.items()):
        clean_actions = [clean_action_name(a) for a in actions]
        seen_actions: set[str] = set()
        unique_actions: list[str] = []
        for a in clean_actions:
            if a and a not in seen_actions:
                seen_actions.add(a)
                unique_actions.append(a)
        rt_name = humanize_record_name(parent)
        if not rt_name or rt_name in ('SYNCEDRECORD', 'RECORD'):
            rt_name = parent
        cap: dict = {
            'type': 'record actions',
            'record_type': rt_name,
            'action_count': len(actions),
        }
        if unique_actions:
            cap['actions'] = unique_actions[:5]
        capabilities.append(cap)

    # Merge capabilities with the same record_type
    merged: dict[str, dict] = {}
    other_caps: list[dict] = []
    for cap in capabilities:
        if cap['type'] == 'record actions':
            rt = cap['record_type']
            if rt in merged:
                merged[rt]['action_count'] += cap['action_count']
                existing = set(merged[rt].get('actions', []))
                for a in cap.get('actions', []):
                    if a not in existing and len(merged[rt].get('actions', [])) < 5:
                        merged[rt].setdefault('actions', []).append(a)
                        existing.add(a)
            else:
                merged[rt] = cap
        else:
            other_caps.append(cap)
    capabilities = list(merged.values()) + other_caps

    # Sites
    for entry in bundle_entries:
        if entry.get('bundle_type') == 'site':
            capabilities.append({'type': 'site', 'name': entry['root_name']})

    # Dashboards
    for entry in bundle_entries:
        if entry.get('bundle_type') == 'dashboard':
            capabilities.append({'type': 'dashboard', 'name': entry['root_name']})

    # Web APIs
    web_apis = [e for e in bundle_entries if e.get('bundle_type') == 'web_api']
    if web_apis:
        capabilities.append({
            'type': 'web apis',
            'count': len(web_apis),
            'endpoints': [humanize_object_name(e['root_name']) for e in web_apis[:8]],
        })

    # Processes
    processes = [e for e in bundle_entries if e.get('bundle_type') == 'process']
    if processes:
        capabilities.append({
            'type': 'processes',
            'count': len(processes),
            'examples': [humanize_object_name(e['root_name']) for e in processes[:8]],
        })

    return capabilities
