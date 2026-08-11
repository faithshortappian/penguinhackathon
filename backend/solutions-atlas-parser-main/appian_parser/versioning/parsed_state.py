"""Parsed state store — internal cache for delta parsing."""

from __future__ import annotations

import json

from appian_parser.domain.models import ParsedObject


class ParsedStateStore:
    """Build and load parsed_state.json."""

    @staticmethod
    def build(parsed_objects: list[ParsedObject], version: str, generated_at: str) -> dict:
        objects = {}
        for obj in parsed_objects:
            objects[obj.uuid] = {
                'name': obj.name,
                'object_type': obj.object_type,
                'diff_hash': obj.diff_hash,
                'source_file': obj.source_file,
                'data': obj.data,
            }
        return {
            '_metadata': {'version': version, 'total_objects': len(objects), 'generated_at': generated_at},
            'objects': objects,
        }

    @staticmethod
    def load(path: str) -> tuple[list[ParsedObject], str]:
        with open(path) as f:
            state = json.load(f)
        version = state['_metadata']['version']
        objects = []
        for uuid, entry in state['objects'].items():
            objects.append(ParsedObject(
                uuid=uuid, name=entry['name'], object_type=entry['object_type'],
                data=entry['data'], diff_hash=entry.get('diff_hash'),
                source_file=entry.get('source_file', ''),
            ))
        return objects, version
