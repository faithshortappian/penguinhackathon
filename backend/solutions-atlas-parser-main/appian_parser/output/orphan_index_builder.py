"""Builds the orphan index artifact (orphans_index.json)."""

from __future__ import annotations

from appian_parser.domain.models import ParsedObject


class OrphanIndexBuilder:
    """Builds the v3 orphans_index.json dict."""

    def build(
        self,
        parsed_objects: list[ParsedObject],
        bundle_assignments: dict[str, list[str]],
    ) -> dict:
        """Build orphan index — objects not in any bundle."""
        orphans = [
            obj for obj in parsed_objects
            if not bundle_assignments.get(obj.uuid)
        ]

        by_type: dict[str, int] = {}
        entries: list[dict] = []
        for obj in orphans:
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
            entries.append({
                'uuid': obj.uuid,
                'name': obj.name,
                'type': obj.object_type,
            })

        return {
            '_metadata': {'total_orphans': len(orphans)},
            'by_type': dict(sorted(by_type.items())),
            'orphans': entries,
        }
