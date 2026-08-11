"""Builds the dependency graph artifact (graph.json)."""

from __future__ import annotations

from appian_parser.domain.models import ParsedObject

HUB_CALLER_THRESHOLD = 20


class GraphBuilder:
    """Builds the v3 graph.json dict."""

    def build(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        bundle_assignments: dict[str, list[str]],
        hub_uuids: set[str],
    ) -> dict:
        """Build complete dependency graph dict."""
        # Build inbound/outbound counts from edges
        inbound: dict[str, int] = {}
        outbound: dict[str, int] = {}
        seen_edges: set[tuple[str, str, str]] = set()
        edges: list[dict] = []

        for dep in dependencies:
            key = (dep.source_uuid, dep.target_uuid, dep.dependency_type)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({
                    'from': dep.source_uuid,
                    'to': dep.target_uuid,
                    'type': dep.dependency_type,
                })
                outbound[dep.source_uuid] = outbound.get(dep.source_uuid, 0) + 1
                inbound[dep.target_uuid] = inbound.get(dep.target_uuid, 0) + 1

        nodes: list[dict] = []
        for obj in parsed_objects:
            bundles = bundle_assignments.get(obj.uuid, [])
            nodes.append({
                'id': obj.uuid,
                'name': obj.name,
                'type': obj.object_type,
                'bundles': bundles,
                'inbound_count': inbound.get(obj.uuid, 0),
                'outbound_count': outbound.get(obj.uuid, 0),
                'is_hub': obj.uuid in hub_uuids,
                'is_orphan': len(bundles) == 0,
            })

        return {
            '_metadata': {
                'schema_version': '1.0',
                'node_count': len(nodes),
                'edge_count': len(edges),
                'hub_threshold': HUB_CALLER_THRESHOLD,
            },
            'nodes': nodes,
            'edges': edges,
        }
