"""Builds the single-fetch app_overview.json."""

import json
import os
from datetime import datetime, timezone
from typing import Any

from appian_parser.domain.models import ParsedObject
from appian_parser.output.app_description_builder import derive_description
from appian_parser.output.app_domain_builder import extract_domains
from appian_parser.output.app_capability_builder import extract_capabilities
from appian_parser.output.app_cross_app_builder import extract_cross_app_dependencies


class AppOverviewBuilder:
    """Builds the single-fetch application overview."""

    def build(
        self,
        package_info: dict,
        object_counts: dict,
        bundle_entries: list[dict],
        dependency_summary: dict,
        coverage: dict,
        parsed_objects: list[ParsedObject] | None = None,
        dependencies: list | None = None,
    ) -> dict[str, Any]:
        objs = parsed_objects or []
        return {
            '_metadata': {
                'parser_version': '2.0.0',
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'source_package': package_info.get('filename', ''),
            },
            'description': derive_description(bundle_entries, objs),
            'domains': extract_domains(bundle_entries, objs),
            'capabilities': extract_capabilities(bundle_entries),
            'cross_app_dependencies': extract_cross_app_dependencies(objs, dependencies or []),
            'package_info': package_info,
            'object_counts': object_counts,
            'bundles': bundle_entries,
            'dependency_summary': dependency_summary,
            'coverage': coverage,
        }

    @staticmethod
    def write(overview: dict, output_dir: str, pretty: bool = True) -> None:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, 'app_overview.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(overview, f, indent=2 if pretty else None, ensure_ascii=False, default=str)
