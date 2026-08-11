"""Application manifest builder."""

from datetime import datetime, timezone
from typing import Any

from appian_parser.output.json_dumper import ParsedObject


class ManifestBuilder:
    """Builds application-level manifest from parsed objects."""

    @staticmethod
    def build(
        zip_filename: str,
        parsed_objects: list[ParsedObject],
        errors: list,
        parse_duration: float = 0.0,
        total_xml_files: int = 0,
        total_files_in_zip: int = 0,
    ) -> dict[str, Any]:
        by_type: dict[str, list] = {}
        for obj in parsed_objects:
            by_type.setdefault(obj.object_type, []).append({
                'uuid': obj.uuid,
                'name': obj.name,
            })

        total_by_type = {t: len(objs) for t, objs in by_type.items()}

        return {
            '_metadata': {
                'parser_version': '1.0.0',
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'source_package': zip_filename,
                'parse_duration_seconds': round(parse_duration, 2),
            },
            'package_info': {
                'filename': zip_filename,
                'total_files_in_zip': total_files_in_zip,
                'total_xml_files': total_xml_files,
                'total_parsed_objects': len(parsed_objects),
                'total_errors': len(errors),
            },
            'object_inventory': {
                'by_type': {t: {'count': len(objs), 'objects': objs} for t, objs in sorted(by_type.items())},
                'total_by_type': dict(sorted(total_by_type.items())),
            },
        }
