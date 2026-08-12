"""V3 manifest builder — master index of all objects."""

from __future__ import annotations

from appian_parser.domain.models import ParsedObject


class V3ManifestBuilder:
    """Builds the v3 manifest.json dict."""

    @staticmethod
    def build(
        parsed_objects: list[ParsedObject],
        version: str,
        generated_at: str,
        previous_manifest: dict | None = None,
    ) -> dict:
        objects = {}
        for obj in parsed_objects:
            last_changed = version
            if previous_manifest:
                prev = previous_manifest.get('objects', {}).get(obj.uuid)
                if prev and prev['diff_hash'] == obj.diff_hash:
                    last_changed = prev['last_changed_in']

            objects[obj.uuid] = {
                'name': obj.name,
                'type': obj.object_type,
                'diff_hash': obj.diff_hash,
                'last_changed_in': last_changed,
            }

        return {
            '_metadata': {
                'version': version,
                'total_objects': len(objects),
                'generated_at': generated_at,
            },
            'objects': objects,
        }
