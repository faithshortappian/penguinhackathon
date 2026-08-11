"""Builds per-object code files (code/<uuid>.json)."""

from __future__ import annotations

from appian_parser.domain.models import ParsedObject

# Map object type → data field(s) that contain SAIL code
_CODE_FIELD_MAP: dict[str, list[str]] = {
    'Interface': ['sail_code'],
    'Expression Rule': ['definition'],
    'Web API': ['sail_code'],
    'Integration': ['sail_code'],
}


def extract_code(obj: ParsedObject) -> str | None:
    """Extract SAIL code from an object's data. Returns None if no code."""
    for field in _CODE_FIELD_MAP.get(obj.object_type, []):
        val = obj.data.get(field)
        if val:
            return val

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


class CodeFileBuilder:
    """Builds the v3 code/<uuid>.json dicts."""

    def build_all(self, parsed_objects: list[ParsedObject]) -> dict[str, dict]:
        """Build code dict for every object that has SAIL code."""
        result: dict[str, dict] = {}
        for obj in parsed_objects:
            code = extract_code(obj)
            if code:
                result[obj.uuid] = {
                    'uuid': obj.uuid,
                    'name': obj.name,
                    'type': obj.object_type,
                    'sail_code': code,
                }
        return result
