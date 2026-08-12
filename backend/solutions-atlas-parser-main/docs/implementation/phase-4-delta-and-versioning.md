# Phase 4 — Delta Parse & Versioning

**Goal**: Add the `delta` CLI command, delta merge, new release detection, history archival, changelog generation, and retention pruning. This is the most complex phase.

**Prerequisite**: Phase 3 complete (versioned baseline write working).

---

## 4.1 Delta Merger

**New file**: `appian_parser/versioning/delta_merger.py`

**Purpose**: Merge delta-parsed objects into existing state.

**Class**: `DeltaMerger`

```python
@dataclass
class MergeResult:
    merged_objects: list[ParsedObject]
    modified_uuids: set[str]    # existed before, hash changed
    added_uuids: set[str]       # new objects not in existing state

class DeltaMerger:
    def merge(
        self,
        existing_objects: list[ParsedObject],
        delta_objects: list[ParsedObject],
    ) -> MergeResult:
        """Merge delta objects into existing set."""
        existing_map = {obj.uuid: obj for obj in existing_objects}
        modified = set()
        added = set()

        for delta_obj in delta_objects:
            if delta_obj.uuid in existing_map:
                if existing_map[delta_obj.uuid].diff_hash != delta_obj.diff_hash:
                    modified.add(delta_obj.uuid)
                existing_map[delta_obj.uuid] = delta_obj
            else:
                added.add(delta_obj.uuid)
                existing_map[delta_obj.uuid] = delta_obj

        return MergeResult(
            merged_objects=list(existing_map.values()),
            modified_uuids=modified,
            added_uuids=added,
        )
```

**Tests**: `tests/versioning/test_delta_merger.py`
- Test merge replaces existing object with same UUID
- Test merge adds new object
- Test modified_uuids contains objects with changed hash
- Test added_uuids contains new objects
- Test unchanged objects preserved
- Test empty delta → no changes

---

## 4.2 Mode Detector

**New file**: `appian_parser/versioning/mode_detector.py`

**Purpose**: Determine if a delta parse is a daily update or a new release.

**Class**: `ModeDetector`

```python
class ParseMode(Enum):
    DAILY_UPDATE = "daily_update"
    NEW_RELEASE = "new_release"

class ModeDetector:
    def detect(
        self,
        current_version: str,       # from manifest
        detected_version: str | None, # from parsed objects
    ) -> ParseMode:
        if detected_version is None:
            return ParseMode.DAILY_UPDATE  # version constant not in delta
        if detected_version == current_version:
            return ParseMode.DAILY_UPDATE
        return ParseMode.NEW_RELEASE
```

**Tests**: `tests/versioning/test_mode_detector.py`
- Test same version → DAILY_UPDATE
- Test different version → NEW_RELEASE
- Test None version → DAILY_UPDATE

---

## 4.3 History Archiver

**New file**: `appian_parser/versioning/history_archiver.py`

**Purpose**: Archive modified/removed objects to `history/<uuid>/<version>.json` before overwriting.

**Class**: `HistoryArchiver`

```python
class HistoryArchiver:
    def archive(
        self,
        data_dir: str,
        changed_uuids: set[str],
        old_version: str,
        in_memory_objects: list[ParsedObject],
        dependencies: list[Dependency],
        bundle_assignments: dict[str, list[str]],
        pretty: bool = True,
    ) -> int:
        """Archive changed objects to history. Returns count archived."""
        obj_map = {obj.uuid: obj for obj in in_memory_objects}
        # Build calls/called_by from dependencies
        calls_map, called_by_map = self._build_dep_maps(dependencies)
        archived = 0

        for uuid in changed_uuids:
            obj = obj_map.get(uuid)
            if not obj:
                continue

            snapshot = {
                "uuid": obj.uuid,
                "name": obj.name,
                "type": obj.object_type,
                "description": obj.data.get("description", ""),
                "diff_hash": obj.diff_hash,
                "bundles": bundle_assignments.get(obj.uuid, []),
                "calls": [self._dep_entry(d) for d in calls_map.get(uuid, [])],
                "called_by": [self._dep_entry(d) for d in called_by_map.get(uuid, [])],
                "sail_code": self._extract_code(obj),
                "type_specific": ObjectFileBuilder._extract_type_specific_static(obj),
            }

            path = f"{data_dir}/history/{uuid}/{old_version}.json"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(snapshot, f, indent=2 if pretty else None, ensure_ascii=False)
            archived += 1

        return archived
```

**Note**: Uses `ObjectFileBuilder._extract_type_specific` as a static method (extract it in Phase 1 to be reusable).

**Tests**: `tests/versioning/test_history_archiver.py`
- Test archive creates correct directory structure
- Test snapshot contains code + metadata + deps
- Test only changed UUIDs are archived
- Test missing UUID in obj_map is skipped

---

## 4.4 Changelog Builder

**New file**: `appian_parser/versioning/changelog_builder.py`

**Purpose**: Generate changelog by diffing old manifest vs new manifest.

**Class**: `ChangelogBuilder`

```python
class ChangelogBuilder:
    def build(
        self,
        old_manifest: dict,
        new_manifest: dict,
        old_version: str,
        new_version: str,
        bundle_assignments: dict[str, list[str]],
        old_bundle_dicts: list[dict] | None,
        new_bundle_dicts: list[dict],
        version_constant_name: str,
        is_full_parse: bool,
    ) -> dict:
        """Build changelog dict."""
        old_objects = old_manifest.get("objects", {})
        new_objects = new_manifest.get("objects", {})

        object_changes = []
        added = modified = removed = unchanged = 0

        # Detect added and modified
        for uuid, new_entry in new_objects.items():
            if uuid not in old_objects:
                if new_entry["name"] == version_constant_name:
                    continue  # exclude version constant
                object_changes.append({
                    "uuid": uuid, "name": new_entry["name"], "type": new_entry["type"],
                    "status": "added", "old_hash": None, "new_hash": new_entry["diff_hash"],
                    "affected_bundles": bundle_assignments.get(uuid, []),
                })
                added += 1
            elif old_objects[uuid]["diff_hash"] != new_entry["diff_hash"]:
                if new_entry["name"] == version_constant_name:
                    continue
                object_changes.append({
                    "uuid": uuid, "name": new_entry["name"], "type": new_entry["type"],
                    "status": "modified",
                    "old_hash": old_objects[uuid]["diff_hash"],
                    "new_hash": new_entry["diff_hash"],
                    "affected_bundles": bundle_assignments.get(uuid, []),
                })
                modified += 1
            else:
                unchanged += 1

        # Detect removed (full parse only)
        if is_full_parse:
            for uuid, old_entry in old_objects.items():
                if uuid not in new_objects:
                    if old_entry["name"] == version_constant_name:
                        continue
                    object_changes.append({
                        "uuid": uuid, "name": old_entry["name"], "type": old_entry["type"],
                        "status": "removed", "old_hash": old_entry["diff_hash"], "new_hash": None,
                        "affected_bundles": [],
                    })
                    removed += 1

        # Bundle changes
        bundle_changes = self._diff_bundles(old_bundle_dicts, new_bundle_dicts)

        return {
            "_metadata": {"from_release": old_version, "to_release": new_version, "generated_at": ...},
            "summary": {
                "objects_added": added, "objects_modified": modified,
                "objects_removed": removed, "objects_unchanged": unchanged,
                "bundles_added": ..., "bundles_modified": ...,
                "bundles_removed": ..., "bundles_unchanged": ...,
            },
            "object_changes": object_changes,
            "bundle_changes": bundle_changes,
        }

    def _diff_bundles(self, old_bundles, new_bundles):
        """Diff bundle member lists to produce bundle_changes with members_added/removed."""
        old_map = {b["_metadata"]["bundle_id"]: b for b in (old_bundles or [])}
        new_map = {b["_metadata"]["bundle_id"]: b for b in new_bundles}
        changes = []

        for bid, new_b in new_map.items():
            if bid not in old_map:
                changes.append({"bundle_id": bid, "status": "added", ...})
            else:
                old_members = {m["uuid"] for m in old_map[bid].get("members", [])}
                new_members = {m["uuid"] for m in new_b.get("members", [])}
                if old_members != new_members:
                    # Compute members_added, members_removed
                    ...

        for bid in old_map:
            if bid not in new_map:
                changes.append({"bundle_id": bid, "status": "removed", ...})

        return changes
```

**Tests**: `tests/versioning/test_changelog_builder.py`
- Test added objects detected
- Test modified objects detected (hash differs)
- Test removed objects detected (full parse only)
- Test removed objects NOT detected in delta mode
- Test version constant excluded
- Test bundle changes with members_added/members_removed
- Test unchanged objects not listed

---

## 4.5 Retention Pruner

**New file**: `appian_parser/versioning/pruner.py`

**Purpose**: Delete oldest release data when retention limit exceeded.

**Class**: `RetentionPruner`

```python
class RetentionPruner:
    def prune_if_needed(
        self,
        data_dir: str,
        release_index: dict,
        max_retained: int,
    ) -> int:
        """Prune oldest release if over limit. Returns releases pruned."""
        releases = release_index.get("releases", [])
        pruned = 0
        while len(releases) > max_retained:
            oldest = releases.pop(0)
            version = oldest["version"]
            self._delete_release_data(data_dir, version)
            pruned += 1
        # Update metadata
        release_index["_metadata"]["total_releases"] = len(releases)
        return pruned

    def _delete_release_data(self, data_dir, version):
        shutil.rmtree(f"{data_dir}/release_snapshots/{version}", ignore_errors=True)
        _safe_delete(f"{data_dir}/changelogs/{version}.json")
        # Delete history files for this version
        history_dir = f"{data_dir}/history"
        if os.path.isdir(history_dir):
            for uuid_dir in os.listdir(history_dir):
                version_file = f"{history_dir}/{uuid_dir}/{version}.json"
                _safe_delete(version_file)
                # Clean up empty uuid dirs
                uuid_path = f"{history_dir}/{uuid_dir}"
                if os.path.isdir(uuid_path) and not os.listdir(uuid_path):
                    os.rmdir(uuid_path)
```

**Tests**: `tests/versioning/test_pruner.py`
- Test no pruning when under limit
- Test prunes oldest when over limit
- Test deletes snapshot, changelog, history files
- Test cleans up empty history directories

---

## 4.6 Release Snapshot Writer

**New file**: `appian_parser/versioning/snapshot_writer.py`

**Purpose**: Copy current manifest and app_overview to `release_snapshots/<version>/`.

**Class**: `SnapshotWriter`

```python
class SnapshotWriter:
    def snapshot(self, data_dir: str, version: str) -> None:
        """Copy current manifest + app_overview to release_snapshots."""
        dest = f"{data_dir}/release_snapshots/{version}"
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(f"{data_dir}/current/manifest.json", f"{dest}/manifest.json")
        shutil.copy2(f"{data_dir}/current/app_overview.json", f"{dest}/app_overview.json")
```

**Tests**: `tests/versioning/test_snapshot_writer.py`
- Test creates snapshot directory
- Test copies both files

---

## 4.7 Versioned Writer — New Release Flow

**Modified file**: `appian_parser/output/versioned_writer.py`

**Add method**: `write_new_release()` — the full pre-write → write → post-write flow.

```python
def write_new_release(
    self,
    artifacts: BuildArtifacts,
    manifest: dict,
    parsed_state: dict,
    old_manifest: dict,
    old_version: str,
    new_version: str,
    changelog: dict,
    release_index: dict,
    history_archiver: HistoryArchiver,
    changed_uuids: set[str],
    in_memory_old_objects: list[ParsedObject],
    old_dependencies: list[Dependency],
    old_bundle_assignments: dict[str, list[str]],
    app_config: AppConfig,
    is_full_parse: bool,
) -> WriteStats:
    """Full new release write flow."""
    # PRE-WRITE: snapshot
    SnapshotWriter().snapshot(self._data_dir, old_version)

    # PRE-WRITE: archive changed objects
    history_archiver.archive(
        self._data_dir, changed_uuids, old_version,
        in_memory_old_objects, old_dependencies, old_bundle_assignments,
    )

    # WRITE: update current/ (smart write)
    self._write_current(artifacts, manifest, parsed_state)

    # WRITE: remove deleted objects (full parse only)
    if is_full_parse:
        removed = set(old_manifest["objects"]) - set(manifest["objects"])
        for uuid in removed:
            _safe_delete(f"{self._current}/objects/{uuid}.json")
            _safe_delete(f"{self._current}/code/{uuid}.json")

    # POST-WRITE: changelog
    self._writer.write_json(f"{self._data_dir}/changelogs/{new_version}.json", changelog)

    # POST-WRITE: release index
    self._writer.write_json(f"{self._data_dir}/release_index.json", release_index)

    # POST-WRITE: prune
    RetentionPruner().prune_if_needed(
        self._data_dir, release_index, app_config.max_retained_releases
    )

    # Stale cleanup
    self._cleanup_stale(artifacts)

    return self._writer.stats
```

**Add method**: `write_daily_update()` — simplified flow without versioning.

```python
def write_daily_update(
    self,
    artifacts: BuildArtifacts,
    manifest: dict,
    parsed_state: dict,
) -> WriteStats:
    """Daily update — smart write to current/, no versioning."""
    self._write_current(artifacts, manifest, parsed_state)
    self._cleanup_stale(artifacts)
    return self._writer.stats
```

---

## 4.8 Delta CLI Command

**Modified file**: `appian_parser/cli.py`

**Add function**: `delta_package()` — the delta parse entry point.

```python
def delta_package(zip_path: str, options: DumpOptions) -> DumpResult:
    """Delta parse: merge delta ZIP into existing state."""
    assert options.data_dir, "delta requires --data-dir"

    app_config = AppConfig.load(f"{options.data_dir}/app_config.json")

    # Load existing state
    state_path = f"{options.data_dir}/current/parsed_state.json"
    if not os.path.exists(state_path):
        print("Warning: parsed_state.json not found. Falling back to full parse.")
        return dump_package(zip_path, None, options)

    existing_objects, existing_version = ParsedStateStore.load(state_path)
    old_manifest = _load_json(f"{options.data_dir}/current/manifest.json")

    # Parse delta ZIP
    reader = PackageReader()
    contents = reader.read(zip_path)
    try:
        delta_objects, errors = _parse_all(contents, ...)

        # Merge
        merger = DeltaMerger()
        merge_result = merger.merge(existing_objects, delta_objects)

        # Detect version
        detector = VersionDetector()
        version_info = detector.detect(merge_result.merged_objects, app_config.version_constant)
        if options.release_override:
            version_info = detector._parse_version(options.release_override)

        # Detect mode
        mode = ModeDetector().detect(existing_version, version_info.raw if version_info else None)

        # TRANSFORM (full set)
        resolver = ReferenceResolver(merge_result.merged_objects, ...)
        resolver.resolve_all(merge_result.merged_objects, locale=options.locale)
        dependencies = DependencyAnalyzer().analyze(merge_result.merged_objects)

        # BUILD
        artifacts = _build_artifacts(merge_result.merged_objects, dependencies, options,
                                     version=version_info.raw)

        # WRITE
        writer = VersionedWriter(options.data_dir, pretty=options.pretty)
        manifest = ManifestBuilder().build(merge_result.merged_objects, version_info.raw, now, old_manifest)
        parsed_state = ParsedStateStore.build(merge_result.merged_objects, version_info.raw, now)

        if mode == ParseMode.DAILY_UPDATE:
            stats = writer.write_daily_update(artifacts, manifest, parsed_state)
        else:
            # New release
            changelog = ChangelogBuilder().build(old_manifest, manifest, ...)
            release_index = _load_json(f"{options.data_dir}/release_index.json")
            ReleaseIndexBuilder.append_release(release_index, version_info, ...)
            stats = writer.write_new_release(artifacts, manifest, parsed_state, old_manifest, ...)

        return DumpResult(...)
    finally:
        reader.cleanup(contents.temp_dir)
```

**CLI argument parsing** (in `main()`):
```python
# Add delta subcommand
delta_parser = subparsers.add_parser("delta", help="Delta parse into versioned data store")
delta_parser.add_argument("package", help="Delta ZIP file")
delta_parser.add_argument("--data-dir", required=True)
delta_parser.add_argument("--release", default=None)
delta_parser.add_argument("--locale", default="en-US")
delta_parser.add_argument("--no-pretty", action="store_true")
```

**Tests**: `tests/test_delta_cli.py`
- Test delta with daily update (same version) → smart write, no changelog
- Test delta with new release → snapshot, history, changelog, release_index updated
- Test delta fallback to full parse when parsed_state missing
- Test empty delta → no files written
- Test delta with new object → added_uuids populated

---

## 4.9 Subsequent Full Parse — New Release

**Modified file**: `appian_parser/cli.py`

**Changes to `dump_package()`**: When `--data-dir` is provided and a previous manifest exists, treat it as a new release (not baseline).

```python
if options.data_dir:
    manifest_path = f"{options.data_dir}/current/manifest.json"
    if os.path.exists(manifest_path):
        # Subsequent full parse — new release flow
        old_manifest = _load_json(manifest_path)
        old_version = old_manifest["_metadata"]["version"]

        # Detect removed objects (full parse only)
        removed_uuids = set(old_manifest["objects"]) - {obj.uuid for obj in parsed_objects}

        # Load old state for history archival
        old_objects, _ = ParsedStateStore.load(f"{options.data_dir}/current/parsed_state.json")

        # ... build changelog, archive history, write new release ...
    else:
        # First parse — baseline flow (existing Phase 3 code)
        ...
```

**Tests**: `tests/test_cli.py`
- Test full parse over existing data → new release flow triggered
- Test removed objects detected and archived
- Test changelog includes removed objects

---

## Phase 4 Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `DeltaMerger` | New class | Merges delta objects into existing state |
| `ModeDetector` | New class | Daily update vs new release detection |
| `HistoryArchiver` | New class | Archives changed objects to history/ |
| `ChangelogBuilder` | New class | Diffs manifests to produce changelogs |
| `RetentionPruner` | New class | Prunes oldest release data |
| `SnapshotWriter` | New class | Copies current state to release_snapshots/ |
| `VersionedWriter` | Enhanced | write_new_release(), write_daily_update() |
| `delta_package()` | New function | Delta parse entry point |
| `dump_package()` | Enhanced | Subsequent full parse → new release flow |
| `delta` CLI command | New | `python -m appian_parser delta <zip> --data-dir <dir>` |

## Phase 4 Verification

After Phase 4:
- Full pipeline test with real data:
  1. `dump SourceSelectionv2.7.0.zip --data-dir ./data/GSS` → baseline
  2. `dump SourceSelectionv2.8.0.zip --data-dir ./data/GSS` → new release (changelog, history, snapshot)
  3. `delta SourceSelection-2.9.0-delta.zip --data-dir ./data/GSS` → new release via delta
- Verify: `release_index.json` has 3 entries
- Verify: `changelogs/` has 2 files
- Verify: `history/` has snapshots for changed objects
- Verify: `release_snapshots/` has 2 snapshots (v2.7.0 and v2.8.0)
- Verify: smart write stats show minimal files written for delta
- All tests pass
