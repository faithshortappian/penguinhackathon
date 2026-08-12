"""App configuration, version detection, and release index."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from appian_parser.domain.models import ParsedObject


@dataclass
class AppConfig:
    """Per-application configuration from app_config.json."""
    application_name: str
    version_constant: str
    max_retained_releases: int

    @staticmethod
    def load(path: str) -> AppConfig:
        with open(path) as f:
            data = json.load(f)
        return AppConfig(
            application_name=data['application_name'],
            version_constant=data['version_constant'],
            max_retained_releases=data['max_retained_releases'],
        )


@dataclass
class VersionInfo:
    """Parsed version information."""
    raw: str
    appian_version: str
    solution_version: str
    sort_key: tuple[int, ...]


class VersionDetector:
    """Extracts application version from parsed objects."""

    def detect(self, parsed_objects: list[ParsedObject], version_constant_name: str) -> VersionInfo | None:
        for obj in parsed_objects:
            if obj.object_type == 'Constant' and obj.name == version_constant_name:
                raw = obj.data.get('value', '')
                if raw:
                    return self.parse_version(raw)
        return None

    @staticmethod
    def parse_version(raw: str) -> VersionInfo:
        parts = raw.strip().split('.')
        sort_key = tuple(int(p) for p in parts if p.isdigit())
        appian_version = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else raw
        solution_version = '.'.join(parts[2:]) if len(parts) > 2 else ''
        return VersionInfo(raw=raw, appian_version=appian_version,
                           solution_version=solution_version, sort_key=sort_key)


class ReleaseIndexBuilder:
    """Builds and updates release_index.json."""

    @staticmethod
    def build_baseline(
        app_name: str, version_info: VersionInfo, parsed_at: str,
        source_package: str, total_objects: int, total_bundles: int,
    ) -> dict:
        return {
            '_metadata': {
                'application': app_name,
                'total_releases': 1,
                'latest_release': version_info.raw,
            },
            'releases': [{
                'version': version_info.raw,
                'appian_version': version_info.appian_version,
                'solution_version': version_info.solution_version,
                'sort_key': list(version_info.sort_key),
                'parsed_at': parsed_at,
                'source_package': source_package,
                'total_objects': total_objects,
                'total_bundles': total_bundles,
                'is_baseline': True,
                'change_summary': None,
            }],
        }

    @staticmethod
    def append_release(
        index: dict, version_info: VersionInfo, parsed_at: str,
        source_package: str, total_objects: int, total_bundles: int,
        change_summary: dict, previous_release: str,
    ) -> dict:
        index['releases'].append({
            'version': version_info.raw,
            'appian_version': version_info.appian_version,
            'solution_version': version_info.solution_version,
            'sort_key': list(version_info.sort_key),
            'parsed_at': parsed_at,
            'source_package': source_package,
            'total_objects': total_objects,
            'total_bundles': total_bundles,
            'is_baseline': False,
            'previous_release': previous_release,
            'change_summary': change_summary,
        })
        index['_metadata']['total_releases'] = len(index['releases'])
        index['_metadata']['latest_release'] = version_info.raw
        return index
