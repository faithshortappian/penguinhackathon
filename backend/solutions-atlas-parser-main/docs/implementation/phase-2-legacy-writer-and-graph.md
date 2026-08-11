# Phase 2 — Legacy Writer & Graph

**Goal**: Wire the Phase 1 builders into the pipeline and produce the new v3 output format in legacy mode (`dump <zip> <output_dir>`). The current `dump_package()` function is refactored to use the new builders. The old output format is replaced by the new one.

**Prerequisite**: Phase 1 complete (all builders tested).

---

## 2.1 Legacy Writer

**New file**: `appian_parser/output/legacy_writer.py`

**Purpose**: Writes all v3 artifacts to a flat output directory. This is the "Phase 4: Write" for legacy mode from Spec 03.

**Class**: `LegacyWriter`

**Method**:
```python
def write_all(
    self,
    output_dir: str,
    object_files: dict[str, dict],      # from ObjectFileBuilder
    code_files: dict[str, dict],         # from CodeFileBuilder
    bundle_dicts: list[dict],            # from BundleCoordinator → BundleFileBuilder
    graph: dict,                         # from GraphBuilder
    search_index: dict,                  # from SearchIndexBuilder
    app_overview: dict,                  # from AppOverviewBuilder
    orphan_index: dict,                  # from OrphanIndexBuilder
    errors: list[ParseError],
    pretty: bool = True,
) -> WriteStats:
    """Write all artifacts to output_dir. Returns write statistics."""
```

**Directory creation**:
```python
os.makedirs(f"{output_dir}/objects", exist_ok=True)
os.makedirs(f"{output_dir}/code", exist_ok=True)
os.makedirs(f"{output_dir}/bundles", exist_ok=True)
```

**File writes**:
```python
# Single files
_write_json(f"{output_dir}/app_overview.json", app_overview)
_write_json(f"{output_dir}/search_index.json", search_index)
_write_json(f"{output_dir}/graph.json", graph)
_write_json(f"{output_dir}/orphans_index.json", orphan_index)

# Per-object files
for uuid, obj_dict in object_files.items():
    _write_json(f"{output_dir}/objects/{uuid}.json", obj_dict)

# Per-object code files
for uuid, code_dict in code_files.items():
    _write_json(f"{output_dir}/code/{uuid}.json", code_dict)

# Per-bundle files
for bundle_dict in bundle_dicts:
    bundle_id = bundle_dict["_metadata"]["bundle_id"]
    _write_json(f"{output_dir}/bundles/{bundle_id}.json", bundle_dict)
```

**`WriteStats` dataclass**:
```python
@dataclass
class WriteStats:
    files_written: int
    files_skipped: int    # always 0 in legacy mode
    total_bytes: int
```

**Note**: Legacy mode does NOT include `version_history` in object files. The `LegacyWriter` strips this field if present, or the `ObjectFileBuilder` accepts a `include_version_history=False` parameter.

**Tests**: `tests/output/test_legacy_writer.py`
- Test directory structure created correctly
- Test all expected files exist
- Test object file count matches parsed object count
- Test code file count (only objects with code)
- Test bundle file count matches bundle count
- Test graph.json exists and has nodes/edges

---

## 2.2 Refactor `dump_package()` — Build Phase

**Modified file**: `appian_parser/cli.py`

**Changes**: Replace the current write calls with the new build → write pipeline. The function structure becomes:

```python
def dump_package(zip_path: str, output_dir: str, options: DumpOptions) -> DumpResult:
    # === PHASE 1: ACQUIRE (unchanged) ===
    reader = PackageReader()
    detector = TypeDetector(excluded_types=options.excluded_types or None)
    registry = ParserRegistry()
    contents = reader.read(zip_path)

    try:
        parsed_objects, errors = _parse_all(contents, detector, registry)

        # === PHASE 2: TRANSFORM (unchanged) ===
        label_lookup = LabelBundleResolver.build_lookup(contents.properties_files)
        resolver = ReferenceResolver(parsed_objects, label_lookup=label_lookup)
        resolver.resolve_all(parsed_objects, locale=options.locale)

        dependencies = []
        if options.include_dependencies:
            analyzer = DependencyAnalyzer()
            dependencies = analyzer.analyze(parsed_objects)

        # === PHASE 3: BUILD (new) ===
        artifacts = _build_artifacts(parsed_objects, dependencies, options)

        # === PHASE 4: WRITE (new) ===
        writer = LegacyWriter()
        stats = writer.write_all(
            output_dir=output_dir,
            object_files=artifacts.object_files,
            code_files=artifacts.code_files,
            bundle_dicts=artifacts.bundle_dicts,
            graph=artifacts.graph,
            search_index=artifacts.search_index,
            app_overview=artifacts.app_overview,
            orphan_index=artifacts.orphan_index,
            errors=errors,
            pretty=options.pretty,
        )

        return DumpResult(...)
    finally:
        reader.cleanup(contents.temp_dir)
```

**New helper**: `_build_artifacts()` — calls all builders and returns a container:

```python
@dataclass
class BuildArtifacts:
    object_files: dict[str, dict]
    code_files: dict[str, dict]
    bundle_dicts: list[dict]
    bundle_assignments: dict[str, list[str]]
    hub_uuids: set[str]
    graph: dict
    search_index: dict
    app_overview: dict
    orphan_index: dict

def _build_artifacts(
    parsed_objects: list[ParsedObject],
    dependencies: list[Dependency],
    options: DumpOptions,
) -> BuildArtifacts:
    # 1. Bundle generation (returns assignments, hubs, index entries, bundle dicts)
    coordinator = BundleCoordinator()
    bundle_assignments, hub_uuids, bundle_entries, bundle_dicts = \
        coordinator.build_all(parsed_objects, dependencies)

    bundled_uuids = set(bundle_assignments.keys())
    orphan_uuids = {obj.uuid for obj in parsed_objects if obj.uuid not in bundled_uuids}

    # 2. Object files
    obj_builder = ObjectFileBuilder()
    object_files = obj_builder.build_all(
        parsed_objects, dependencies, bundle_assignments, hub_uuids, orphan_uuids
    )

    # 3. Code files
    code_builder = CodeFileBuilder()
    code_files = code_builder.build_all(parsed_objects)

    # 4. Graph
    graph_builder = GraphBuilder()
    graph = graph_builder.build(parsed_objects, dependencies, bundle_assignments, hub_uuids)

    # 5. Search index
    search_builder = SearchIndexBuilder()
    search_index = search_builder.build(parsed_objects, dependencies, bundle_assignments)

    # 6. App overview
    overview_builder = AppOverviewBuilder()
    dep_summary = _build_dependency_summary(dependencies)
    coverage = {
        "total_objects": len(parsed_objects),
        "bundled": len(bundled_uuids),
        "orphaned": len(orphan_uuids),
    }
    app_overview = overview_builder.build(package_info, object_counts, bundle_entries, dep_summary, coverage)

    # 7. Orphan index
    orphan_builder = OrphanIndexBuilder()
    orphan_index = orphan_builder.build(parsed_objects, bundle_assignments)

    return BuildArtifacts(
        object_files=object_files,
        code_files=code_files,
        bundle_dicts=bundle_dicts,
        bundle_assignments=bundle_assignments,
        hub_uuids=hub_uuids,
        graph=graph,
        search_index=search_index,
        app_overview=app_overview,
        orphan_index=orphan_index,
    )
```

**Tests**: Update `tests/test_cli.py`
- Existing tests adapted to verify new output structure
- Test `objects/<uuid>.json` has `type_specific` field
- Test `code/<uuid>.json` exists for Expression Rules
- Test `bundles/<Name>.json` is a single file (not a directory)
- Test `graph.json` exists with nodes and edges
- Test `orphans_index.json` replaces `orphans/` directory

---

## 2.3 Validation Script Update

**Modified file**: `scripts/validate_restructured_output.py`

**Changes**: Update to validate the new v3 output structure instead of the old one. Key checks:

- Every UUID in `manifest.json` (if present) has a corresponding `objects/<uuid>.json`
- Every object with code has a `code/<uuid>.json`
- Every bundle's `members[].uuid` exists in `objects/`
- Graph node count matches object count
- Graph edge `from`/`to` UUIDs exist in node set
- Search index names match object names
- Orphan index UUIDs are NOT in any bundle's members

---

## 2.4 Remove Old Writers

**After validation passes**, remove the old output classes that are now replaced:

| Old Class | Replaced By |
|-----------|-------------|
| `BundleStructureBuilder` | `BundleFileBuilder` (via `BundleCoordinator`) |
| `BundleCodeBuilder` | `CodeFileBuilder` |
| `ObjectDependencyWriter` | `ObjectFileBuilder` + `LegacyWriter` |
| `OrphanWriter` | `OrphanIndexBuilder` + `LegacyWriter` |
| `JSONDumper` | `LegacyWriter` |
| `BundleBuilder` | `BundleCoordinator` + `BundleFileBuilder` |

**Do NOT remove yet**:
- `BundleSummarizer` — may still be useful
- `ManifestBuilder` — will be enhanced in Phase 3
- `EnrichmentWriter` — enrichment is orthogonal to this refactor

---

## Phase 2 Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `LegacyWriter` | New class | Writes v3 flat output |
| `BuildArtifacts` | New dataclass | Container for all built artifacts |
| `_build_artifacts()` | New function | Orchestrates all builders |
| `dump_package()` | Refactored | Uses build → write pipeline |
| Old writers | Removed | 6 classes removed |

## Phase 2 Verification

After Phase 2:
- `python -m appian_parser dump MyApp.zip ./output` produces v3 output structure
- Output has: `objects/`, `code/`, `bundles/` (single files), `graph.json`, `orphans_index.json`
- No `bundles/<Name>/structure.json` or `bundles/<Name>/code.json` (old format gone)
- Validation script passes on real package output
- All existing tests pass (adapted for new structure)
- Parse time still under 3 seconds for 2,500 objects
