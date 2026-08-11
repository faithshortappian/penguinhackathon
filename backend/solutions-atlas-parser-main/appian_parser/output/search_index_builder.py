"""Builds the flat search_index.json from parsed objects, dependencies, and bundle assignments."""

import json
import os
from collections import defaultdict

from appian_parser.domain.models import ParsedObject


class SearchIndexBuilder:
    """Builds a flat name → metadata lookup for all parsed objects."""

    def build(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        bundle_assignments: dict[str, list[str]],
    ) -> dict[str, dict]:
        # Pre-compute dep counts
        out_counts: dict[str, int] = defaultdict(int)
        in_counts: dict[str, int] = defaultdict(int)
        for d in dependencies:
            out_counts[d.source_uuid] += 1
            in_counts[d.target_uuid] += 1

        index: dict[str, dict] = {}
        for obj in parsed_objects:
            bundles = bundle_assignments.get(obj.uuid, [])
            index[obj.name] = {
                'uuid': obj.uuid,
                'type': obj.object_type,
                'description': obj.data.get('description'),
                'bundle_count': len(bundles),
                'bundles': bundles[:5],  # Top 5 only; full list in objects/<uuid>.json
                'deps_out': out_counts.get(obj.uuid, 0),
                'deps_in': in_counts.get(obj.uuid, 0),
            }
        return index

    @staticmethod
    def write(index: dict, output_dir: str, pretty: bool = True) -> None:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, 'search_index.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2 if pretty else None, ensure_ascii=False, default=str)
