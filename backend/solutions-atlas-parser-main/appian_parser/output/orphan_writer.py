"""Writes orphaned object files (objects not in any bundle)."""

import json
import os
from collections import defaultdict

from appian_parser.domain.models import ParsedObject
from appian_parser.output.bundle_code_builder import BundleCodeBuilder


class OrphanWriter:
    """Writes orphaned object files (objects not in any bundle)."""

    def write_all(
        self,
        orphan_objects: list[ParsedObject],
        dependencies: list,
        output_dir: str,
        pretty: bool = True,
    ) -> None:
        if not orphan_objects:
            return

        orphans_dir = os.path.join(output_dir, 'orphans')
        os.makedirs(orphans_dir, exist_ok=True)
        indent = 2 if pretty else None

        # Build dep lookups scoped to orphans
        orphan_uuids = {o.uuid for o in orphan_objects}
        outbound: dict[str, list] = defaultdict(list)
        inbound: dict[str, list] = defaultdict(list)
        for d in dependencies:
            if d.source_uuid in orphan_uuids:
                outbound[d.source_uuid].append(d)
            if d.target_uuid in orphan_uuids:
                inbound[d.target_uuid].append(d)

        code_builder = BundleCodeBuilder()

        # Write index
        by_type: dict[str, list[dict]] = defaultdict(list)
        for obj in orphan_objects:
            by_type[obj.object_type].append({'uuid': obj.uuid, 'name': obj.name})

        index = {
            '_metadata': {
                'description': 'Objects not reachable from any entry point.',
                'total_objects': len(orphan_objects),
            },
            'by_type': {k: sorted(v, key=lambda x: x['name']) for k, v in sorted(by_type.items())},
        }
        with open(os.path.join(orphans_dir, '_index.json'), 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=indent, ensure_ascii=False, default=str)

        # Write per-orphan files
        for obj in orphan_objects:
            data = {
                'uuid': obj.uuid,
                'name': obj.name,
                'type': obj.object_type,
                'description': obj.data.get('description'),
                'sail_code': code_builder._extract_code(obj),
                'calls': [
                    {'name': d.target_name, 'type': d.target_type, 'dep_type': d.dependency_type}
                    for d in outbound.get(obj.uuid, [])
                ],
                'called_by': [
                    {'name': d.source_name, 'type': d.source_type, 'dep_type': d.dependency_type}
                    for d in inbound.get(obj.uuid, [])
                ],
            }
            path = os.path.join(orphans_dir, f'{obj.uuid}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
