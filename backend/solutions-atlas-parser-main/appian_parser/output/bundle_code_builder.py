"""Builds code-only bundle files, loaded on demand."""

import json
import os
from typing import Any

from appian_parser.domain.models import ParsedObject

# Map object type → data field(s) that contain SAIL code
_CODE_FIELD_MAP: dict[str, list[str]] = {
    'Interface': ['sail_code'],
    'Expression Rule': ['definition'],
    'Web API': ['sail_code'],
    'Integration': ['sail_code'],
}


class BundleCodeBuilder:
    """Builds code-only bundle files, loaded on demand."""

    def build_code(self, bundle_id: str, objects: list[ParsedObject]) -> dict[str, Any]:
        entries: dict[str, dict] = {}
        for obj in objects:
            code = self._extract_code(obj)
            if code:
                entries[obj.uuid] = {
                    'name': obj.name,
                    'type': obj.object_type,
                    'sail_code': code,
                }
        return {
            '_metadata': {'bundle_id': bundle_id},
            'objects': entries,
        }

    @staticmethod
    def _extract_code(obj: ParsedObject) -> str | None:
        """Extract SAIL code from an object's data."""
        for field in _CODE_FIELD_MAP.get(obj.object_type, []):
            val = obj.data.get(field)
            if val:
                return val

        # Process models: concatenate node expressions
        if obj.object_type == 'Process Model':
            parts = []
            for node in obj.data.get('nodes', []):
                if node.get('form_expression'):
                    parts.append(f"// Node: {node.get('node_name', '?')}\n{node['form_expression']}")
                for inp in node.get('inputs', []):
                    if inp.get('input_expression'):
                        parts.append(f"// Input: {inp.get('name', '?')}\n{inp['input_expression']}")
                for out in node.get('outputs', []):
                    if out.get('output_expression'):
                        parts.append(f"// Output: {out.get('name', '?')}\n{out['output_expression']}")
            if parts:
                return '\n\n'.join(parts)

        return None
