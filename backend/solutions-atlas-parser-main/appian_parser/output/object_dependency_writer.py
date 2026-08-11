"""Writes individual object dependency files to objects/ directory."""

import json
import os
from collections import defaultdict

from appian_parser.domain.models import ParsedObject


class ObjectDependencyWriter:
    """Writes individual object dependency files."""

    def write_all(
        self,
        parsed_objects: list[ParsedObject],
        dependencies: list,
        bundle_assignments: dict[str, list[str]],
        output_dir: str,
        pretty: bool = True,
    ) -> None:
        objects_dir = os.path.join(output_dir, 'objects')
        os.makedirs(objects_dir, exist_ok=True)

        outbound: dict[str, list] = defaultdict(list)
        inbound: dict[str, list] = defaultdict(list)
        for d in dependencies:
            outbound[d.source_uuid].append(d)
            inbound[d.target_uuid].append(d)

        indent = 2 if pretty else None
        for obj in parsed_objects:
            data = {
                'uuid': obj.uuid,
                'name': obj.name,
                'type': obj.object_type,
                'description': obj.data.get('description'),
                'bundles': bundle_assignments.get(obj.uuid, []),
                'calls': [
                    {'name': d.target_name, 'type': d.target_type, 'dep_type': d.dependency_type}
                    for d in outbound.get(obj.uuid, [])
                ],
                'called_by': [
                    {'name': d.source_name, 'type': d.source_type, 'dep_type': d.dependency_type}
                    for d in inbound.get(obj.uuid, [])
                ],
            }
            path = os.path.join(objects_dir, f'{obj.uuid}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
