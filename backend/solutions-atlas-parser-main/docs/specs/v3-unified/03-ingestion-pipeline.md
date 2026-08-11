# 03 — Ingestion Pipeline

The ingestion pipeline is responsible for getting data into the data layer. It supports two modes: full parse (from a complete ZIP) and delta parse (from a delta ZIP merged with existing state). The core transform pipeline is identical in both modes.

---

## Pipeline Overview

Regardless of mode, the pipeline has four phases:

```
Phase 1: ACQUIRE        → Assemble the complete set of ParsedObjects
Phase 2: TRANSFORM      → Resolve references, analyze dependencies, enrich
Phase 3: BUILD          → Produce all output artifacts in memory
Phase 4: WRITE          → Persist artifacts to disk
```

The modes differ only in Phase 1 (how objects are acquired) and Phase 4 (how files are written). Phases 2 and 3 are identical.

---

## Phase 1: Acquire Object Set

### Full Parse Mode

Triggered by: `dump <zip> --data-dir <dir>` or `dump <zip> <output_dir>` (legacy)

```
ZIP file
  → PackageReader.read()          Extract ZIP, discover XML/XSD files
  → For each XML file:
      TypeDetector.detect()       Determine object type from root tag
      ParserRegistry.get_parser() Get type-specific parser
      parser.parse()              Extract structured data from XML
      DiffHashService.hash()      Generate SHA-512 content hash
  → list[ParsedObject]            Complete set of all objects
```

This is the existing pipeline, unchanged. It produces the full set of `ParsedObject` instances from scratch.

### Delta Parse Mode

Triggered by: `delta <delta_zip> --data-dir <dir>`

```
Delta ZIP file (3 modified objects)
  → PackageReader.read()          Extract ZIP, discover XML/XSD files
  → Parse delta XML files         Same pipeline as full parse, just fewer files
  → list[ParsedObject]            3 delta objects (unresolved)

Existing state
  → ParsedStateStore.load()       Load parsed_state.json (~0.3s)
  → list[ParsedObject]            2,500 existing objects (already resolved)

Merge
  → DeltaMerger.merge()           Replace/add delta objects into existing set
  → list[ParsedObject]            2,500 merged objects (2,497 resolved + 3 unresolved)
```

The merge is a simple dict-keyed replacement: build a `{uuid: obj}` map from existing objects, overwrite/add entries from delta objects, flatten back to a list.

The merger also returns two sets:
- `modified_uuids`: UUIDs that existed before and were replaced (hash differs)
- `added_uuids`: UUIDs that are new (not in existing state)

These sets are used later for smart writing and version detection.

### Version Detection

After the object set is assembled (in either mode), the pipeline detects the application version:

1. Load `app_config.json` to get the `version_constant` name
2. Find the constant with that name in the parsed objects
3. Extract its value as the version string
4. Parse into components: `25.04.02.09.00` → appian_version `25.04`, solution_version `02.09.00`, sort_key `(25, 4, 2, 9, 0)`

If `--release` is provided on the CLI, it overrides auto-detection.

### Mode Detection (Delta Only)

For delta parses, the pipeline also determines whether this is a **daily update** or a **new release**:

```
Load current/manifest.json → get current version
Compare with detected version:
  Same version     → DAILY UPDATE (update current/ in place, no versioning)
  Different version → NEW RELEASE (snapshot, archive, changelog, then update)
  Not found in delta → DAILY UPDATE (version constant wasn't modified)
```

### Fallback

If `parsed_state.json` doesn't exist when a delta parse is requested (cache miss, first run, corruption), the pipeline falls back to a full parse automatically. The full parse generates `parsed_state.json` for future delta runs.

---

## Phase 2: Transform

Identical for both modes. Operates on the complete merged object set.

```
1. Reference Resolution
   ReferenceResolver.resolve_all(merged_objects, locale)
   → Replaces UUIDs with rule!/cons!/type! names in SAIL code
   → Replaces Record Type URNs with recordType!Name.field
   → Replaces Translation URNs with translated text
   → Mutates objects in place

2. Dependency Analysis
   DependencyAnalyzer.analyze(merged_objects)
   → Extracts inter-object dependencies via pattern matching
   → Returns list[Dependency] (source → target with type)

3. Enrichment (optional)
   Enricher.enrich_all(merged_objects, dependencies)
   → Adds depth scores, tags, and other derived metadata
```

For delta parses, resolution runs on all 2,500 objects. For the ~2,497 already-resolved objects, the regex scans find no UUIDs to replace — effectively a no-op. For the 3 delta objects, UUIDs get replaced with names. The cost is just the regex scan time (~0.76s), which is acceptable.

This "full re-resolution" approach is chosen over incremental resolution because:
- A new object in the delta might be referenced by UUID in an existing object that wasn't fully resolved before (the referenced object didn't exist yet)
- The full analysis on 2,500 objects takes ~2s total — not worth optimizing
- The real savings from delta parsing are in download bandwidth and git commit size, not parser speed

---

## Phase 3: Build Artifacts

All output artifacts are produced in memory. No files are written in this phase. This separation is critical — it allows Phase 4 to apply smart writing, versioning logic, and different output strategies without modifying the builders.

```
1. Bundle Generation
   BundleCoordinator.build_all(parsed_objects, dependencies)
   → Discovers entry points (actions, processes, sites, web APIs, dashboards, pages)
   → BFS traversal from each entry point to collect transitive dependencies
   → Returns: bundle_assignments (uuid → bundle_ids), hub_uuids, bundle_entries, bundle_data

2. Search Index
   SearchIndexBuilder.build(parsed_objects, dependencies, bundle_assignments)
   → Returns: dict (name → {uuid, type, description, bundle_count, deps})

3. App Overview
   AppOverviewBuilder.build(package_info, object_counts, bundle_entries, dep_summary, coverage)
   → Returns: dict (package metadata + bundle index + dependency summary)

4. Dependency Graph
   GraphExporter.build(parsed_objects, dependencies, bundle_assignments, hub_uuids)
   → Returns: dict (nodes[] + edges[])

5. Object Files
   ObjectFileBuilder.build_all(parsed_objects, dependencies, bundle_assignments, hub_uuids)
   → Returns: dict[uuid, dict] (enriched object metadata for each object)

6. Code Files
   CodeFileBuilder.build_all(parsed_objects)
   → Returns: dict[uuid, dict] (SAIL code for each object that has code)

7. Orphan Index
   OrphanIndexBuilder.build(parsed_objects, bundle_assignments)
   → Returns: dict (orphan catalog)

8. Manifest
   ManifestBuilder.build(parsed_objects, version, previous_manifest)
   → Returns: dict (uuid → {name, type, hash, last_changed_in})
```

All builders are pure functions: data in → data out. They receive `ParsedObject` instances and dependency data, and return dicts ready for JSON serialization.

The key change from the current system: builders like `BundleCoordinator` currently both build AND write files. In the new system, they only build. Writing is handled by Phase 4.

---

## Phase 4: Write

The write phase persists all artifacts to disk. Its behavior depends on the mode.

### Legacy Mode (flat output)

For `dump <zip> <output_dir>` without `--data-dir`:

- Write all artifacts to `output_dir/` directly
- No manifest, no parsed_state, no versioning
- Every file is written unconditionally (no smart write)
- Backward compatible with current behavior

### Versioned Full Parse

For `dump <zip> --data-dir <dir>`:

First parse (baseline):
- Write all artifacts to `current/`
- Write `manifest.json` with `last_changed_in` = current version for all objects
- Write `parsed_state.json`
- Create `release_index.json` with one baseline entry
- No changelog (nothing to compare against)

Subsequent full parse:
- Same as "new release" flow in delta mode (snapshot, archive, write, changelog)

### Versioned Delta Parse — Daily Update

For `delta <zip> --data-dir <dir>` when version hasn't changed:

- Write artifacts to `current/` using **smart write**
- Smart write: for each file, compare new content hash with existing file — skip if identical
- Update `manifest.json` (carry forward `last_changed_in` for unchanged objects)
- Update `parsed_state.json`
- No changelog, no snapshot, no history archival
- No update to `release_index.json`

### Versioned Delta Parse — New Release

For `delta <zip> --data-dir <dir>` when version has changed:

Pre-write:
1. Snapshot current metadata to `release_snapshots/<old_version>/`
   - Copy `manifest.json` and `app_overview.json`
2. Archive modified objects to `history/`
   - For each object whose hash changed: save its current state (metadata + code + deps) to `history/<uuid>/<old_version>.json`

Write:
3. Write all artifacts to `current/` using smart write
4. Write `manifest.json` with updated `last_changed_in` for changed objects
5. Write `parsed_state.json`

Post-write:
6. Generate changelog: diff old manifest vs new manifest → `changelogs/<new_version>.json`
7. Update `release_index.json`: append new release entry with change summary
8. Prune: if releases exceed `max_retained_releases`, delete oldest snapshot + changelog + history files

---

## Smart Writing

Smart writing is the mechanism that minimizes git churn for delta updates. It wraps all file I/O with a content comparison:

```
For each file to write:
  1. Serialize new content to JSON string
  2. If file exists on disk:
     a. Read existing content
     b. Compare strings
     c. If identical → skip (don't write)
     d. If different → write
  3. If file doesn't exist → write (new file)
```

Applied to:
- `objects/<uuid>.json` — ~2,497 skipped, ~3 written (for 3 changed objects)
- `code/<uuid>.json` — ~2,497 skipped, ~3 written
- `bundles/<Name>.json` — most skipped, ~5-10 written (bundles containing changed objects)
- `graph.json` — always written (edges change when objects change)
- `search_index.json` — always written (cheap, usually changes)
- `app_overview.json` — always written
- `manifest.json` — always written
- `parsed_state.json` — always written

For a delta parse with 3 changed objects, the expected git footprint is ~20-30 changed files instead of ~3,000.

Smart writing also tracks statistics: files written vs files skipped. These are reported in the CLI output.

Additionally, smart writing handles **stale file cleanup**: if a bundle no longer exists (entry point removed), its file should be deleted. If an object is no longer in the parsed set (removed from package), its files should be deleted. The writer compares the set of files that should exist with the set that does exist, and removes stale files.

---

## Parsed State Lifecycle

`parsed_state.json` is the bridge between full parses and delta parses. Its lifecycle:

| Event | Action |
|-------|--------|
| First full parse | Created with all resolved objects |
| Subsequent full parse | Overwritten with all resolved objects |
| Delta parse | Loaded, merged with delta, overwritten with merged set |
| MCP server query | Never read — MCP uses `objects/`, `code/`, `bundles/`, `graph.json` |
| Git commit | Never committed — in `.gitignore` |
| CI pipeline | Cached between runs via CI cache mechanism |
| Cache miss | Delta falls back to full parse, which regenerates the file |

The file contains resolved data (UUIDs already replaced with names in SAIL code). This means when loading for delta merge, existing objects are already resolved. Resolution on the merged set is mostly a no-op for existing objects.

---

## CLI Commands

### `dump` (existing, enhanced)

```bash
# Legacy mode — flat output, no versioning
python -m appian_parser dump MyApp.zip ./output

# Versioned mode — writes to data layer
python -m appian_parser dump MyApp.zip --data-dir ./data/GSS

# With options
python -m appian_parser dump MyApp.zip --data-dir ./data/GSS \
  --release 25.04.02.09.00 \
  --locale es-ES \
  --exclude-types "Group,Translation String"
```

| Flag | Default | Description |
|------|---------|-------------|
| `--data-dir` | none | Root of versioned data store. If omitted, uses legacy flat mode. |
| `--release` | auto-detect | Override version string (skip constant lookup) |
| `--app-config` | `<data-dir>/app_config.json` | Path to app configuration |
| `--locale` | `en-US` | Locale for translation resolution |
| `--exclude-types` | none | Comma-separated types to skip |
| `--no-deps` | false | Skip dependency analysis (no bundles, no graph) |
| `--no-pretty` | false | Compact JSON output |

### `delta` (new)

```bash
# Standard delta parse
python -m appian_parser delta delta_package.zip --data-dir ./data/GSS

# With options
python -m appian_parser delta delta_package.zip --data-dir ./data/GSS \
  --locale es-ES
```

| Flag | Default | Description |
|------|---------|-------------|
| `--data-dir` | required | Root of versioned data store |
| `--app-config` | `<data-dir>/app_config.json` | Path to app configuration |
| `--release` | auto-detect | Override version string |
| `--locale` | `en-US` | Locale for translation resolution |
| `--no-pretty` | false | Compact JSON output |

The `delta` command requires `--data-dir` (there is no legacy delta mode — delta only makes sense with persistent state).

### `types` (existing, unchanged)

```bash
python -m appian_parser types
```

---

## Performance Expectations

### Full Parse (2,500 objects)

| Phase | Time |
|-------|------|
| Parse XML | ~0.19s |
| Resolve references | ~0.76s |
| Analyze dependencies | ~0.15s |
| Enrich | ~0.10s |
| Build artifacts | ~0.60s |
| Write files | ~0.40s |
| Write parsed_state.json | ~0.30s |
| **Total** | **~2.5s** |

### Delta Parse (3 changed objects)

| Phase | Time |
|-------|------|
| Parse 3 XML files | ~0.002s |
| Load parsed_state.json | ~0.30s |
| Merge | ~0.001s |
| Resolve references (full set) | ~0.76s |
| Analyze dependencies (full set) | ~0.15s |
| Enrich (full set) | ~0.10s |
| Build artifacts | ~0.60s |
| Smart write (~20 files) | ~0.05s |
| Write parsed_state.json | ~0.30s |
| **Total** | **~2.3s** |

The parser-side savings from delta mode are modest (~0.2s). The real savings are:

| Metric | Full Parse | Delta Parse |
|--------|-----------|-------------|
| Download size | ~10MB | ~50KB |
| Files written to disk | ~5,000 | ~20-30 |
| Git diff size | ~5,000 files | ~20-30 files |

---

## Edge Cases

### New object in delta references existing object

Resolution runs on the full merged set. The existing object is in the UUID lookup. The reference resolves correctly.

### Existing object references new object by UUID

Resolution runs on the full merged set. The new object is now in the UUID lookup. When the resolver scans the existing object's SAIL code, it finds the UUID and resolves it. The existing object's content changes even though it wasn't in the delta — its `diff_hash` will change, and it will appear as "modified" in the output. This is correct behavior.

### Object missing from delta (not modified)

It stays as-is in the existing state. Per design, absence from a delta does not mean deletion — Appian supports partial exports.

### Delta contains all objects (full export sent as delta)

Works correctly. All existing objects get replaced. The merge produces the same result as a full parse. Slightly slower due to loading parsed_state.json first, but functionally identical.

### Empty delta (no changes)

The merge produces the same set as existing. Resolution and dependency analysis produce identical results. Smart write skips all files. Git commit has nothing to commit.

### Parsed state corrupted or missing

Delta command detects the missing file, prints a warning, and falls back to full parse. The full parse regenerates parsed_state.json.

---

## Open Questions

All questions resolved.

## Resolved Questions

1. ~~**Smart write granularity for bundles**~~: **Only affected bundles.** Use `bundle_assignments` (already computed) to identify which bundles contain changed UUIDs. Only those bundles are rewritten. This is the whole point of smart write — minimal git footprint.

2. ~~**Parsed state compression**~~: **Deferred.** Not needed now — 0.3s load time is acceptable and the file isn't in git. If CI cache size becomes a problem, `gzip` (stdlib) can reduce 15-50MB to ~2-5MB with minimal code change. Flagged as a future optimization.

3. ~~**Delta ZIP format**~~: **Confirmed: identical format.** Tested with actual Appian packages. The delta ZIP (`SourceSelection-2.9.0-21 - Delta Package Compared with 2.8.0.zip`) uses the exact same structure as the full ZIP: outer ZIP → inner ZIP → same directory layout (`content/`, `group/`, `connectedSystem/`, etc.) with the same XML format (`<groupHaul>`, `<interfaceHaul>`, etc.). The only difference is file count: full has 2,653 files (2,474 XML + 107 XSD), delta has 162 files (153 XML + 0 XSD). No parser changes needed for delta mode — the existing parsers work on both.
