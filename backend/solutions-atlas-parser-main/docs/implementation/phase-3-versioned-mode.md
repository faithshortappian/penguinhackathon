# Phase 3 — Versioned Mode

**Goal**: Add `--data-dir` flag to the `dump` command. When provided, output goes to the versioned directory structure (`data/<AppName>/current/`) with manifest, version detection, and smart writing. This is the first parse (baseline) flow.

**Prerequisite**: Phase 2 complete (legacy writer working, all builders tested).

---

## 3.1 App Config Loader

**New file**: `appian_parser/versioning/app_config.py`

**Purpose**: Load and validate `app_config.json`.

**Class**: `AppConfig`

```python
@dataclass
class AppConfig:
    application_name: str
    version_constant: str
    max_retained_releases: int

    @staticmethod
    def load(path: str) -> "AppConfig":
        """Load from JSON file. Raises FileNotFoundError if missing."""
        with open(path) as f:
            data = json.load(f)
        return AppConfig(
            application_name=data["application_name"],
            version_constant=data["version_constant"],
            max_retained_releases=data["max_retained_releases"],
        )
```

**Tests**: `tests/versioning/test_app_config.py`
- Test load valid config
- Test missing file raises
- Test missing required field raises

---

## 3.2 Version Detector

**New file**: `appian_parser/versioning/version_detector.py`

**Purpose**: Extract application version from parsed objects using the version constant name.

**Class**: `VersionDetector`

```python
@dataclass
class VersionInfo:
    raw: str                    # "25.04.02.09.00"
    appian_version: str         # "25.04"
    solution_version: str       # "02.09.00"
    sort_key: tuple[int, ...]   # (25, 4, 2, 9, 0)

class VersionDetector:
    def detect(
        self,
        parsed_objects: list[ParsedObject],
        version_constant_name: str,
    ) -> VersionInfo | None:
        """Find the version constant and extract version info."""
        for obj in parsed_objects:
            if obj.object_type == "Constant" and obj.name == version_constant_name:
                raw = obj.data.get("value", "")
                return self._parse_version(raw)
        return None

    def _parse_version(self, raw: str) -> VersionInfo:
        """Parse '25.04.02.09.00' into VersionInfo."""
        parts = raw.split(".")
        sort_key = tuple(int(p) for p in parts)
        appian_version = f"{parts[0]}.{parts[1]}"
        solution_version = ".".join(parts[2:])
        return VersionInfo(raw=raw, appian_version=appian_version,
                          solution_version=solution_version, sort_key=sort_key)
```

**Tests**: `tests/versioning/test_version_detector.py`
- Test detection from sample parsed objects
- Test version parsing with various formats
- Test returns None when constant not found

---

## 3.3 Manifest Builder (Enhanced)

**Modified file**: `appian_parser/output/manifest_builder.py`

**Changes**: The current `ManifestBuilder` builds a basic manifest. Enhance it to produce the v3 manifest with `_metadata` and `last_changed_in`.

```python
class ManifestBuilder:
    def build(
        self,
        parsed_objects: list[ParsedObject],
        version: str,
        generated_at: str,
        previous_manifest: dict | None = None,
    ) -> dict:
        """Build manifest.json dict."""
        objects = {}
        for obj in parsed_objects:
            last_changed = version  # default for new/changed objects
            if previous_manifest:
                prev_entry = previous_manifest.get("objects", {}).get(obj.uuid)
                if prev_entry and prev_entry["diff_hash"] == obj.diff_hash:
                    last_changed = prev_entry["last_changed_in"]  # carry forward

            objects[obj.uuid] = {
                "name": obj.name,
                "type": obj.object_type,
                "diff_hash": obj.diff_hash,
                "last_changed_in": last_changed,
            }

        return {
            "_metadata": {
                "version": version,
                "total_objects": len(objects),
                "generated_at": generated_at,
            },
            "objects": objects,
        }
```

**Tests**: `tests/output/test_manifest_builder.py`
- Test baseline (no previous manifest) → all objects get current version
- Test with previous manifest → unchanged objects carry forward `last_changed_in`
- Test changed object gets new version

---

## 3.4 Smart Writer

**New file**: `appian_parser/output/smart_writer.py`

**Purpose**: Wraps file I/O with content comparison to minimize git churn. Also handles stale file cleanup.

**Class**: `SmartWriter`

```python
@dataclass
class WriteStats:
    files_written: int = 0
    files_skipped: int = 0
    files_deleted: int = 0

class SmartWriter:
    def __init__(self, pretty: bool = True):
        self._pretty = pretty
        self.stats = WriteStats()

    def write_json(self, path: str, data: dict | list) -> None:
        """Write JSON file only if content changed."""
        new_content = json.dumps(data, indent=2 if self._pretty else None, ensure_ascii=False)
        if os.path.exists(path):
            with open(path, "r") as f:
                existing = f.read()
            if existing == new_content:
                self.stats.files_skipped += 1
                return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(new_content)
        self.stats.files_written += 1

    def cleanup_stale(self, directory: str, expected_filenames: set[str]) -> None:
        """Delete files in directory that are not in expected set."""
        if not os.path.isdir(directory):
            return
        for filename in os.listdir(directory):
            if filename not in expected_filenames:
                os.remove(os.path.join(directory, filename))
                self.stats.files_deleted += 1
```

**Tests**: `tests/output/test_smart_writer.py`
- Test write new file → written
- Test write identical content → skipped
- Test write changed content → written
- Test cleanup_stale removes unexpected files
- Test cleanup_stale preserves expected files
- Test stats tracking

---

## 3.5 Versioned Writer

**New file**: `appian_parser/output/versioned_writer.py`

**Purpose**: Writes all v3 artifacts to the versioned directory structure (`data/<AppName>/current/`). Uses `SmartWriter` for content-aware writes.

**Class**: `VersionedWriter`

```python
class VersionedWriter:
    def __init__(self, data_dir: str, pretty: bool = True):
        self._data_dir = data_dir          # e.g., ./data/GSS
        self._current = f"{data_dir}/current"
        self._writer = SmartWriter(pretty=pretty)

    def write_baseline(
        self,
        artifacts: BuildArtifacts,
        manifest: dict,
        parsed_state: dict,
        release_index: dict,
        app_config_path: str | None = None,
    ) -> WriteStats:
        """Write all artifacts for first parse (baseline)."""
        # current/ directory
        self._writer.write_json(f"{self._current}/manifest.json", manifest)
        self._writer.write_json(f"{self._current}/app_overview.json", artifacts.app_overview)
        self._writer.write_json(f"{self._current}/search_index.json", artifacts.search_index)
        self._writer.write_json(f"{self._current}/graph.json", artifacts.graph)
        self._writer.write_json(f"{self._current}/orphans_index.json", artifacts.orphan_index)

        # objects/
        for uuid, obj_dict in artifacts.object_files.items():
            self._writer.write_json(f"{self._current}/objects/{uuid}.json", obj_dict)

        # code/
        for uuid, code_dict in artifacts.code_files.items():
            self._writer.write_json(f"{self._current}/code/{uuid}.json", code_dict)

        # bundles/
        for bundle_dict in artifacts.bundle_dicts:
            bid = bundle_dict["_metadata"]["bundle_id"]
            self._writer.write_json(f"{self._current}/bundles/{bid}.json", bundle_dict)

        # parsed_state.json (always written, not smart-written)
        self._write_raw_json(f"{self._current}/parsed_state.json", parsed_state)

        # release_index.json (at data_dir root, not in current/)
        self._writer.write_json(f"{self._data_dir}/release_index.json", release_index)

        # Stale cleanup
        self._cleanup_stale(artifacts)

        return self._writer.stats

    def _cleanup_stale(self, artifacts: BuildArtifacts) -> None:
        """Remove files that should no longer exist."""
        expected_objects = {f"{uuid}.json" for uuid in artifacts.object_files}
        self._writer.cleanup_stale(f"{self._current}/objects", expected_objects)

        expected_code = {f"{uuid}.json" for uuid in artifacts.code_files}
        self._writer.cleanup_stale(f"{self._current}/code", expected_code)

        expected_bundles = {f'{b["_metadata"]["bundle_id"]}.json' for b in artifacts.bundle_dicts}
        self._writer.cleanup_stale(f"{self._current}/bundles", expected_bundles)
```

**Tests**: `tests/output/test_versioned_writer.py`
- Test baseline write creates correct directory structure
- Test all files exist under `current/`
- Test `release_index.json` at data_dir root
- Test stale file cleanup
- Test smart write stats (second write with same data → all skipped)

---

## 3.6 Parsed State Builder

**New file**: `appian_parser/versioning/parsed_state.py`

**Purpose**: Build and load `parsed_state.json` — the internal cache for delta parsing.

**Class**: `ParsedStateStore`

```python
class ParsedStateStore:
    @staticmethod
    def build(
        parsed_objects: list[ParsedObject],
        version: str,
        generated_at: str,
    ) -> dict:
        """Build parsed_state.json dict from parsed objects."""
        objects = {}
        for obj in parsed_objects:
            objects[obj.uuid] = {
                "name": obj.name,
                "object_type": obj.object_type,
                "diff_hash": obj.diff_hash,
                "source_file": obj.source_file,
                "data": obj.data,
            }
        return {
            "_metadata": {
                "version": version,
                "total_objects": len(objects),
                "generated_at": generated_at,
            },
            "objects": objects,
        }

    @staticmethod
    def load(path: str) -> tuple[list[ParsedObject], str]:
        """Load parsed_state.json, return (parsed_objects, version)."""
        with open(path) as f:
            state = json.load(f)
        version = state["_metadata"]["version"]
        objects = []
        for uuid, entry in state["objects"].items():
            objects.append(ParsedObject(
                uuid=uuid,
                name=entry["name"],
                object_type=entry["object_type"],
                data=entry["data"],
                diff_hash=entry["diff_hash"],
                source_file=entry.get("source_file", ""),
            ))
        return objects, version
```

**Tests**: `tests/versioning/test_parsed_state.py`
- Test build → load roundtrip preserves all data
- Test load missing file raises FileNotFoundError

---

## 3.7 Release Index Builder

**New file**: `appian_parser/versioning/release_index.py`

**Purpose**: Build and update `release_index.json`.

**Class**: `ReleaseIndexBuilder`

```python
class ReleaseIndexBuilder:
    @staticmethod
    def build_baseline(
        version_info: VersionInfo,
        parsed_at: str,
        source_package: str,
        total_objects: int,
        total_bundles: int,
    ) -> dict:
        """Build release_index.json for first parse."""
        return {
            "_metadata": {
                "application": "",  # filled by caller from app_config
                "total_releases": 1,
                "latest_release": version_info.raw,
            },
            "releases": [{
                "version": version_info.raw,
                "appian_version": version_info.appian_version,
                "solution_version": version_info.solution_version,
                "sort_key": list(version_info.sort_key),
                "parsed_at": parsed_at,
                "source_package": source_package,
                "total_objects": total_objects,
                "total_bundles": total_bundles,
                "is_baseline": True,
                "change_summary": None,
            }],
        }

    @staticmethod
    def append_release(
        existing_index: dict,
        version_info: VersionInfo,
        parsed_at: str,
        source_package: str,
        total_objects: int,
        total_bundles: int,
        change_summary: dict,
    ) -> dict:
        """Append a new release entry to existing index."""
        # ... append to releases list, update _metadata
```

**Tests**: `tests/versioning/test_release_index.py`
- Test baseline creation
- Test append release
- Test sort_key ordering

---

## 3.8 Version-Aware Object Files

**Modified file**: `appian_parser/output/object_file_builder.py`

**Changes**: Add `version_history` support. The builder accepts an optional `version` and `previous_object_files` parameter.

```python
def build_all(
    self,
    parsed_objects, dependencies, bundle_assignments, hub_uuids, orphan_uuids,
    version: str | None = None,
    previous_object_files: dict[str, dict] | None = None,
) -> dict[str, dict]:
    for obj in parsed_objects:
        obj_dict = self._build_object(obj, ...)

        if version:
            obj_dict["version_history"] = self._build_version_history(
                obj, version, previous_object_files
            )

        result[obj.uuid] = obj_dict

def _build_version_history(self, obj, version, previous_files):
    """Build version_history array."""
    current_entry = {"version": version, "status": "current", "diff_hash": obj.diff_hash}

    if not previous_files:
        # Baseline — only current entry
        return [current_entry]

    prev = previous_files.get(obj.uuid)
    if not prev:
        # New object — added in this version
        return [current_entry]

    # Carry forward previous history, update current
    prev_history = prev.get("version_history", [])
    # The old "current" entry becomes "modified" (its version stays the same)
    new_history = [current_entry]
    for entry in prev_history:
        if entry["status"] == "current":
            if entry["diff_hash"] != obj.diff_hash:
                # Object changed — old current becomes "modified"
                new_history.append({**entry, "status": "modified"})
            # If hash is same (daily update), drop old current (replaced by new current)
        else:
            new_history.append(entry)
    return new_history
```

**Tests**: Update `tests/output/test_object_file_builder.py`
- Test baseline → version_history has 1 entry with status "current"
- Test new object → version_history has 1 entry with status "current"
- Test modified object → old "current" becomes "modified", new "current" added
- Test daily update (same hash) → "current" entry updated in place, no new entry
- Test version=None → no version_history field (legacy mode)

---

## 3.9 Wire Versioned Mode into CLI

**Modified file**: `appian_parser/cli.py`

**Changes**: Add `--data-dir` flag to `dump` command. When provided, use `VersionedWriter` instead of `LegacyWriter`.

```python
def dump_package(zip_path: str, output_dir: str, options: DumpOptions) -> DumpResult:
    # ... ACQUIRE + TRANSFORM (unchanged) ...

    # DETECT VERSION (new, only in versioned mode)
    version_info = None
    if options.data_dir:
        app_config = AppConfig.load(f"{options.data_dir}/app_config.json")
        detector = VersionDetector()
        version_info = detector.detect(parsed_objects, app_config.version_constant)
        if options.release_override:
            version_info = detector._parse_version(options.release_override)

    # BUILD (pass version for version_history)
    artifacts = _build_artifacts(
        parsed_objects, dependencies, options,
        version=version_info.raw if version_info else None,
    )

    # WRITE
    if options.data_dir:
        # Versioned mode
        manifest = ManifestBuilder().build(parsed_objects, version_info.raw, now_iso)
        parsed_state = ParsedStateStore.build(parsed_objects, version_info.raw, now_iso)
        release_index = ReleaseIndexBuilder.build_baseline(version_info, now_iso, ...)

        writer = VersionedWriter(options.data_dir, pretty=options.pretty)
        stats = writer.write_baseline(artifacts, manifest, parsed_state, release_index)
    else:
        # Legacy mode
        writer = LegacyWriter()
        stats = writer.write_all(output_dir, ...)
```

**Modified `DumpOptions`**: Add new fields:
```python
@dataclass
class DumpOptions:
    # ... existing fields ...
    data_dir: str | None = None
    release_override: str | None = None
```

**Tests**: `tests/test_cli.py`
- Test `dump` without `--data-dir` → legacy output (existing tests)
- Test `dump` with `--data-dir` → versioned output structure
- Test version detection from parsed objects
- Test `--release` override

---

## Phase 3 Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `AppConfig` | New class | Loads app_config.json |
| `VersionDetector` | New class | Extracts version from parsed objects |
| `SmartWriter` | New class | Content-aware file writes |
| `VersionedWriter` | New class | Writes versioned directory structure |
| `ParsedStateStore` | New class | Build/load parsed_state.json |
| `ReleaseIndexBuilder` | New class | Build/update release_index.json |
| `ManifestBuilder` | Enhanced | v3 manifest with _metadata and last_changed_in |
| `ObjectFileBuilder` | Enhanced | version_history support |
| `DumpOptions` | Enhanced | data_dir, release_override fields |
| `dump_package()` | Enhanced | Versioned mode branch |

## Phase 3 Verification

After Phase 3:
- `python -m appian_parser dump MyApp.zip ./output` → legacy mode (unchanged)
- `python -m appian_parser dump MyApp.zip --data-dir ./data/GSS` → versioned mode
- Versioned output has: `current/` with all artifacts, `release_index.json`, `parsed_state.json`
- Smart write: second run with same ZIP → all files skipped (0 written)
- Version detected from parsed objects matches expected
- All tests pass
