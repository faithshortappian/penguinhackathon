"""Builds a cross-application dependency map from parsed objects.

Appian solutions use a naming convention for cross-app integration:
  - ENTRYPOINT objects: "{prefix}_ENTRYPOINT_{type}_{name}" — exposed APIs
  - APPREF objects: "{prefix}_APPREF_{target}_{type}_{name}" — calls to other apps

This builder extracts both to produce a structured cross-app dependency map.
Falls back to prefix-level aggregation from the dependency graph for
additional signal.
"""

import re
from collections import defaultdict

from appian_parser.domain.models import ParsedObject


def extract_cross_app_dependencies(
    parsed_objects: list[ParsedObject],
    dependencies: list,
) -> dict:
    """Build cross-app dependency map from ENTRYPOINT/APPREF objects.

    Returns:
        {
            "entry_points": [...],       # What this app exposes
            "app_references": [...],     # What this app calls in other apps
            "dependency_edges": [...],   # Aggregated APPREF prefix-to-prefix edges
            "shared_library_usage": [...] # Prefix-level shared code usage from dep graph
        }
    """
    entry_points = _extract_entry_points(parsed_objects)
    app_references = _extract_app_references(parsed_objects)
    edges = _aggregate_dependency_edges(parsed_objects, dependencies)
    shared = _aggregate_shared_library_usage(parsed_objects, dependencies)

    return {
        'entry_points': entry_points,
        'app_references': app_references,
        'dependency_edges': edges,
        'shared_library_usage': shared,
    }


# Pattern: {prefix}_ENTRYPOINT_{operation_type}_{name}
_ENTRYPOINT_RE = re.compile(
    r'^(.+?)_ENTRYPOINT_([A-Z]+)_(.+)$'
)

# Pattern: {prefix}_APPREF_{target_app}_{operation_type}_{name}
_APPREF_RE = re.compile(
    r'^(.+?)_APPREF_([A-Z][A-Z0-9]{1,10})_([A-Z]+)_(.+)$'
)


def _extract_entry_points(parsed_objects: list[ParsedObject]) -> list[dict]:
    """Extract ENTRYPOINT objects — what this app exposes to others."""
    results: list[dict] = []
    for obj in parsed_objects:
        m = _ENTRYPOINT_RE.match(obj.name)
        if m:
            results.append({
                'name': obj.name,
                'prefix': m.group(1),
                'operation_type': m.group(2),
                'function': m.group(3),
            })
    return results


def _extract_app_references(parsed_objects: list[ParsedObject]) -> list[dict]:
    """Extract APPREF objects — what this app calls in other apps."""
    results: list[dict] = []
    for obj in parsed_objects:
        m = _APPREF_RE.match(obj.name)
        if m:
            results.append({
                'name': obj.name,
                'source_prefix': m.group(1),
                'target_app': m.group(2),
                'operation_type': m.group(3),
                'function': m.group(4),
            })
    return results


def _aggregate_dependency_edges(
    parsed_objects: list[ParsedObject],
    dependencies: list,
) -> list[dict]:
    """Aggregate APPREF objects into prefix-to-prefix edges with counts."""
    # Count APPREF-based edges
    edge_calls: dict[tuple[str, str], list[str]] = defaultdict(list)
    for obj in parsed_objects:
        m = _APPREF_RE.match(obj.name)
        if m:
            src = m.group(1)
            tgt = m.group(2)
            edge_calls[(src, tgt)].append(f"{m.group(3)}: {m.group(4)}")

    edges: list[dict] = []
    for (src, tgt), calls in sorted(edge_calls.items(), key=lambda x: -len(x[1])):
        # Deduplicate
        unique = list(dict.fromkeys(calls))
        edges.append({
            'from': src,
            'to': tgt,
            'reference_count': len(calls),
            'references': unique[:8],
        })

    return edges


def _get_prefix(name: str) -> str:
    """Extract the application prefix from an object name."""
    parts = name.split('_')
    if len(parts) >= 3:
        return '_'.join(parts[:2])
    return ''


def _aggregate_shared_library_usage(
    parsed_objects: list[ParsedObject],
    dependencies: list,
) -> list[dict]:
    """Aggregate cross-prefix calls from the dependency graph.

    Captures shared library usage (e.g. AS_CO, AS_FRM) that wouldn't
    appear as APPREF objects since they're bundled in the same ZIP.
    """
    if not dependencies:
        return []

    obj_map = {obj.uuid: obj for obj in parsed_objects}

    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    edge_samples: dict[tuple[str, str], list[str]] = defaultdict(list)

    for dep in dependencies:
        src = obj_map.get(dep.source_uuid)
        tgt = obj_map.get(dep.target_uuid)
        if not src or not tgt:
            continue
        src_prefix = _get_prefix(src.name)
        tgt_prefix = _get_prefix(tgt.name)
        if src_prefix and tgt_prefix and src_prefix != tgt_prefix:
            key = (src_prefix, tgt_prefix)
            edge_counts[key] += 1
            if tgt.name not in edge_samples[key] and len(edge_samples[key]) < 5:
                edge_samples[key].append(tgt.name)

    edges: list[dict] = []
    for (src, tgt), count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        edges.append({
            'from': src,
            'to': tgt,
            'call_count': count,
            'sample_calls': edge_samples[(src, tgt)],
        })

    return edges
