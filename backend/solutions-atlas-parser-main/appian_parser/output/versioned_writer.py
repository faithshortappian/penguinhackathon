"""Smart writer with content-aware writes and versioned directory output."""

from __future__ import annotations

import json
import os

from appian_parser.domain.models import BuildArtifacts, WriteStats


class SmartWriter:
    """Wraps file I/O with content comparison to minimize git churn."""

    def __init__(self, pretty: bool = True):
        self._indent = 2 if pretty else None
        self.stats = WriteStats()

    def write_json(self, path: str, data) -> None:
        new_content = json.dumps(data, indent=self._indent, ensure_ascii=False, default=str)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                if f.read() == new_content:
                    self.stats.files_skipped += 1
                    return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        self.stats.files_written += 1

    def write_raw(self, path: str, data) -> None:
        """Write without smart comparison (for large files like parsed_state)."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=self._indent, ensure_ascii=False, default=str)
        self.stats.files_written += 1

    def cleanup_stale(self, directory: str, expected_filenames: set[str]) -> None:
        if not os.path.isdir(directory):
            return
        for filename in os.listdir(directory):
            if filename not in expected_filenames:
                os.remove(os.path.join(directory, filename))
                self.stats.files_deleted += 1


class VersionedWriter:
    """Writes v3 artifacts to the versioned directory structure."""

    def __init__(self, data_dir: str, pretty: bool = True):
        self._data_dir = data_dir
        self._current = f"{data_dir}/current"
        self._writer = SmartWriter(pretty=pretty)

    @property
    def stats(self) -> WriteStats:
        return self._writer.stats

    def write_baseline(
        self,
        artifacts: BuildArtifacts,
        manifest: dict,
        parsed_state: dict,
        release_index: dict,
    ) -> WriteStats:
        self._write_current(artifacts, manifest, parsed_state)
        self._writer.write_json(f"{self._data_dir}/release_index.json", release_index)
        self._cleanup_stale(artifacts)
        return self._writer.stats

    def write_daily_update(
        self,
        artifacts: BuildArtifacts,
        manifest: dict,
        parsed_state: dict,
    ) -> WriteStats:
        self._write_current(artifacts, manifest, parsed_state)
        self._cleanup_stale(artifacts)
        return self._writer.stats

    def write_new_release(
        self,
        artifacts: BuildArtifacts,
        manifest: dict,
        parsed_state: dict,
        changelog: dict,
        release_index: dict,
        new_version: str,
        removed_uuids: set[str] | None = None,
    ) -> WriteStats:
        """Full new release write: update current, write changelog, update release index."""
        self._write_current(artifacts, manifest, parsed_state)

        # Remove deleted objects (full parse only)
        if removed_uuids:
            for uuid in removed_uuids:
                for subdir in ('objects', 'code'):
                    path = f"{self._current}/{subdir}/{uuid}.json"
                    if os.path.isfile(path):
                        os.remove(path)
                        self._writer.stats.files_deleted += 1

        # Changelog
        os.makedirs(f"{self._data_dir}/changelogs", exist_ok=True)
        self._writer.write_json(f"{self._data_dir}/changelogs/{new_version}.json", changelog)

        # Release index
        self._writer.write_json(f"{self._data_dir}/release_index.json", release_index)

        self._cleanup_stale(artifacts)
        return self._writer.stats

    def _write_current(self, artifacts: BuildArtifacts, manifest: dict, parsed_state: dict) -> None:
        w = self._writer
        c = self._current

        w.write_json(f"{c}/manifest.json", manifest)
        w.write_json(f"{c}/app_overview.json", artifacts.app_overview)
        w.write_json(f"{c}/search_index.json", artifacts.search_index)
        w.write_json(f"{c}/graph.json", artifacts.graph)
        w.write_json(f"{c}/orphans_index.json", artifacts.orphan_index)

        for uuid, obj_dict in artifacts.object_files.items():
            w.write_json(f"{c}/objects/{uuid}.json", obj_dict)

        for uuid, code_dict in artifacts.code_files.items():
            w.write_json(f"{c}/code/{uuid}.json", code_dict)

        for bundle_dict in artifacts.bundle_dicts:
            bid = bundle_dict['_metadata']['bundle_id']
            w.write_json(f"{c}/bundles/{bid}.json", bundle_dict)

        w.write_raw(f"{c}/parsed_state.json", parsed_state)

    def _cleanup_stale(self, artifacts: BuildArtifacts) -> None:
        c = self._current
        self._writer.cleanup_stale(f"{c}/objects", {f"{u}.json" for u in artifacts.object_files})
        self._writer.cleanup_stale(f"{c}/code", {f"{u}.json" for u in artifacts.code_files})
        self._writer.cleanup_stale(f"{c}/bundles",
                                   {f'{b["_metadata"]["bundle_id"]}.json' for b in artifacts.bundle_dicts})
