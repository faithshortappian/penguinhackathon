"""Builds single-file bundle dicts (bundles/<Name>.json) in v3 format."""

from __future__ import annotations

from typing import Any

from appian_parser.domain.models import ParsedObject
from appian_parser.output.bundle_structure_builder import BundleStructureBuilder


class BundleFileBuilder:
    """Builds v3 bundle dicts with members array instead of embedded objects."""

    def __init__(self):
        self._structure_builder = BundleStructureBuilder()

    def build(
        self,
        entry_point: Any,
        objects: list[ParsedObject],
        dep_outbound: dict[str, list],
        dep_inbound: dict[str, list],
        obj_map: dict[str, ParsedObject],
        bundle_id: str,
    ) -> dict:
        """Build a single bundle dict in v3 format."""
        # Reuse existing structure builder for entry_point and flow
        old_structure = self._structure_builder.build_structure(
            entry_point, objects, dep_outbound, dep_inbound, obj_map,
        )

        members = [
            {'uuid': obj.uuid, 'name': obj.name, 'type': obj.object_type}
            for obj in objects
        ]

        key_objects = self._get_key_objects(objects, dep_inbound, dep_outbound)

        return {
            '_metadata': {
                'bundle_id': bundle_id,
                'bundle_type': entry_point.bundle_type,
                'root_name': entry_point.name,
                'parent_name': entry_point.parent_name,
                'object_count': len(objects),
            },
            'entry_point': old_structure.get('entry_point', {}),
            'flow': old_structure.get('flow'),
            'members': members,
            'key_objects': key_objects,
        }

    @staticmethod
    def _get_key_objects(
        objects: list[ParsedObject],
        dep_inbound: dict[str, list],
        dep_outbound: dict[str, list],
    ) -> list[str]:
        """Top 5 most-connected objects by name."""
        scored = []
        for obj in objects:
            count = len(dep_inbound.get(obj.uuid, [])) + len(dep_outbound.get(obj.uuid, []))
            scored.append((count, obj.name))
        scored.sort(reverse=True)
        return [name for _, name in scored[:5]]
