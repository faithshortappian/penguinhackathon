"""Writes v3 artifacts to a flat output directory (legacy mode)."""

from __future__ import annotations

import json
import os

from appian_parser.domain.models import BuildArtifacts, ParseError, WriteStats


class LegacyWriter:
    """Writes all v3 artifacts to a flat output directory."""

    def write_all(
        self,
        output_dir: str,
        artifacts: BuildArtifacts,
        errors: list[ParseError],
        pretty: bool = True,
    ) -> WriteStats:
        indent = 2 if pretty else None
        stats = WriteStats()

        os.makedirs(f"{output_dir}/objects", exist_ok=True)
        os.makedirs(f"{output_dir}/code", exist_ok=True)
        os.makedirs(f"{output_dir}/bundles", exist_ok=True)

        def _write(path: str, data) -> None:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
            stats.files_written += 1

        # Single files
        _write(f"{output_dir}/app_overview.json", artifacts.app_overview)
        _write(f"{output_dir}/search_index.json", artifacts.search_index)
        _write(f"{output_dir}/graph.json", artifacts.graph)
        _write(f"{output_dir}/orphans_index.json", artifacts.orphan_index)

        # Per-object files
        for uuid, obj_dict in artifacts.object_files.items():
            _write(f"{output_dir}/objects/{uuid}.json", obj_dict)

        # Per-object code files
        for uuid, code_dict in artifacts.code_files.items():
            _write(f"{output_dir}/code/{uuid}.json", code_dict)

        # Per-bundle files
        for bundle_dict in artifacts.bundle_dicts:
            bid = bundle_dict['_metadata']['bundle_id']
            _write(f"{output_dir}/bundles/{bid}.json", bundle_dict)

        # Errors
        if errors:
            _write(f"{output_dir}/_errors.json", [
                {'file': e.file, 'error': e.error, 'object_type': e.object_type}
                for e in errors
            ])

        return stats
