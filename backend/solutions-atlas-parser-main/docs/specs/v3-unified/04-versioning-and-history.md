# 04 — Versioning and History

This document describes how the system tracks releases, maintains object history, generates changelogs, and manages retention. Versioning is layered on top of the data layer described in [02-data-layer.md](./02-data-layer.md) — it does not change how objects, bundles, or the graph are structured.

---

## Core Concepts

### Release

A release is a specific version of the application, identified by a version string like `25.04.02.09.00`. Releases form a strictly ordered linear chain — no branching.

### Current State

The `current/` directory always contains the latest parse. This is the fast default path — the MCP server reads from here for all queries that don't specify a historical release.

### Manifest

`current/manifest.json` is the master index. For every object, it records the content hash and the version where the object was last changed. This enables O(1) change detection and O(1) historical lookups.

### History

`history/<uuid>/<version>.json` contains a complete snapshot of an object as it was at a specific version, **before it was overwritten by a newer version**. Only changed objects get history entries. Unchanged objects have no history — their current state IS their historical state.

### Changelog

`changelogs/<version>.json` is a precomputed diff between two adjacent releases. It lists every object and bundle that changed, with status (added/modified) and affected bundles.

### Release Snapshot

`release_snapshots/<version>/` contains lightweight metadata from a previous release: the manifest and app overview. This enables reconstructing the object inventory at any historical release without storing full object data.

---

## Version Format

Appian application versions follow the format: `AA.AA.MM.mm.pp`

| Segment | Meaning | Example |
|---------|---------|---------|
| `AA.AA` | Appian platform version | `25.04` |
| `MM` | Solution major version | `02` |
| `mm` | Solution minor version | `09` |
| `pp` | Solution patch version | `00` |

Full example: `25.04.02.09.00`

Versions are compared as integer tuples: `(25, 4, 2, 9, 0)`. This ensures correct ordering (e.g., `25.04.02.09.00` < `25.04.02.10.00` < `25.04.03.00.00`).

### Version Source

Each application declares a version constant name in `app_config.json` (e.g., `AS_GSS_CO_APP_VERSION`). The parser finds this constant in the parsed objects and extracts the version string. The `--release` CLI flag serves as a fallback/override.

---

## `release_index.json`

The ordered list of all releases for this application. Source of truth for release history.

```json
{
  "_metadata": {
    "application": "GSS",
    "total_releases": 3,
    "latest_release": "25.04.03.00.00"
  },
  "releases": [
    {
      "version": "25.04.01.00.00",
      "appian_version": "25.04",
      "solution_version": "01.00.00",
      "sort_key": [25, 4, 1, 0, 0],
      "parsed_at": "2026-02-15T10:30:00Z",
      "source_package": "AS_GSS_Full_Application_v25.04.01.00.00.zip",
      "total_objects": 2461,
      "total_bundles": 215,
      "is_baseline": true,
      "change_summary": null
    },
    {
      "version": "25.04.02.09.00",
      "appian_version": "25.04",
      "solution_version": "02.09.00",
      "sort_key": [25, 4, 2, 9, 0],
      "parsed_at": "2026-03-20T14:00:00Z",
      "source_package": "AS_GSS_Full_Application_v25.04.02.09.00.zip",
      "total_objects": 2506,
      "total_bundles": 218,
      "is_baseline": false,
      "previous_release": "25.04.01.00.00",
      "change_summary": {
        "objects_added": 45,
        "objects_modified": 87,
        "objects_removed": 0,
        "objects_unchanged": 2374,
        "bundles_added": 3,
        "bundles_modified": 24,
        "bundles_removed": 0,
        "bundles_unchanged": 191
      }
    },
    {
      "version": "25.04.03.00.00",
      "appian_version": "25.04",
      "solution_version": "03.00.00",
      "sort_key": [25, 4, 3, 0, 0],
      "parsed_at": "2026-03-26T16:00:00Z",
      "source_package": "AS_GSS_Full_Application_v25.04.03.00.00.zip",
      "total_objects": 2520,
      "total_bundles": 220,
      "is_baseline": false,
      "previous_release": "25.04.02.09.00",
      "change_summary": {
        "objects_added": 14,
        "objects_modified": 52,
        "objects_removed": 0,
        "objects_unchanged": 2454,
        "bundles_added": 2,
        "bundles_modified": 18,
        "bundles_removed": 0,
        "bundles_unchanged": 200
      }
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Raw version string from the application constant |
| `appian_version` | string | First two segments (platform version) |
| `solution_version` | string | Remaining segments (solution version) |
| `sort_key` | int[] | Numeric tuple for correct ordering |
| `parsed_at` | string | ISO 8601 timestamp of when this release was parsed |
| `source_package` | string | Original ZIP filename |
| `total_objects` | int | Total parsed objects in this release |
| `total_bundles` | int | Total bundles generated |
| `is_baseline` | bool | True if this is the first release (no previous to compare against) |
| `previous_release` | string? | Version of the release this was compared against |
| `change_summary` | object? | Aggregate change counts (null for baseline) |

---

## Changelog Schema

`changelogs/<version>.json` — precomputed diff between two adjacent releases.

```json
{
  "_metadata": {
    "from_release": "25.04.02.09.00",
    "to_release": "25.04.03.00.00",
    "generated_at": "2026-03-26T16:00:00Z"
  },
  "summary": {
    "objects_added": 14,
    "objects_modified": 52,
    "objects_removed": 0,
    "objects_unchanged": 2454,
    "bundles_added": 2,
    "bundles_modified": 18,
    "bundles_removed": 0,
    "bundles_unchanged": 200
  },
  "object_changes": [
    {
      "uuid": "_a-0006eed1-...",
      "name": "AS_GSS_BL_validateLPTAScores",
      "type": "Expression Rule",
      "status": "modified",
      "old_hash": "a3f9c2e1b4d7...",
      "new_hash": "b7d1e4a9c3f2...",
      "affected_bundles": [
        "AS_GSS_Complete_LPTA_Evaluation",
        "AS_GSS_Review_Scores"
      ]
    },
    {
      "uuid": "_a-0008bbc3-...",
      "name": "AS_GSS_IF_NewFeatureForm",
      "type": "Interface",
      "status": "added",
      "old_hash": null,
      "new_hash": "f1a2b3c4d5e6...",
      "affected_bundles": [
        "AS_GSS_New_Feature_Action"
      ]
    }
  ],
  "bundle_changes": [
    {
      "bundle_id": "AS_GSS_Complete_LPTA_Evaluation",
      "bundle_type": "action",
      "status": "modified",
      "objects_added": 2,
      "objects_removed": 0,
      "objects_modified": 8,
      "old_object_count": 282,
      "new_object_count": 284,
      "members_added": [
        {"name": "AS_GSS_BL_newValidation", "type": "Expression Rule"},
        {"name": "AS_GSS_IF_newScorePanel", "type": "Interface"}
      ],
      "members_removed": []
    },
    {
      "bundle_id": "AS_GSS_New_Feature_Action",
      "bundle_type": "action",
      "status": "added",
      "objects_added": 47,
      "objects_removed": 0,
      "objects_modified": 0,
      "old_object_count": 0,
      "new_object_count": 47,
      "members_added": [],
      "members_removed": []
    }
  ]
}
```

**Object change statuses**: `added`, `modified`, `removed`. Unchanged objects are NOT listed — only changes appear. The `removed` status only appears in changelogs generated from full parses (see "Object Removal Tracking" in Design Decisions).

**Bundle change statuses**: `added`, `modified`, `removed`. A bundle is "modified" if any of its member objects were added or modified in this release.

**`affected_bundles`**: For each changed object, lists all bundles (in the new release) that contain this object. This enables impact analysis.

**Version constant exclusion**: The application's version constant (e.g., `AS_GSS_CO_APP_VERSION`) is excluded from `object_changes`. It changes every release by definition — including it is noise.

---

## History File Schema

`history/<uuid>/<version>.json` — a complete snapshot of an object at a specific version.

```json
{
  "uuid": "_a-0006eed1-...",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "description": "Validates LPTA scores against minimum thresholds",
  "diff_hash": "a3f9c2...",

  "bundles": ["AS_GSS_Complete_LPTA_Evaluation"],
  "calls": [
    {"uuid": "_b-...", "name": "AS_CO_UT_isBlank", "type": "Expression Rule", "dep_type": "CALLS"}
  ],
  "called_by": [
    {"uuid": "_c-...", "name": "AS_GSS_PM_CompleteLPTAEvaluation", "type": "Process Model", "dep_type": "CALLS"}
  ],

  "sail_code": "if(rule!AS_CO_UT_isBlank(ri!scores), false, ri!scores > cons!AS_GSS_MIN_SCORE)",

  "type_specific": {
    "inputs": [
      {"name": "scores", "type": "Number(Integer)", "description": "LPTA scores to validate"}
    ],
    "output_type": "Boolean"
  }
}
```

History files are **complete, self-contained snapshots**. They include:
- Object metadata (identity, description, hash)
- Dependency context (calls, called_by, bundles) as they were at that version
- SAIL code (the actual implementation)
- Type-specific fields (inputs, parameters, etc.)

This enables full comparison across versions — you can see what the code looked like AND how it was connected.

History files are only created for objects that **changed** between releases. An object that hasn't changed since version 1.0 has no history files — its current state in `current/objects/<uuid>.json` and `current/code/<uuid>.json` IS its state at every version.

---

## Data Flows

### First Parse (Baseline)

```
1. Parse ZIP → 2,461 ParsedObjects
2. Extract version → "25.04.01.00.00"
3. Check release_index.json → does not exist → BASELINE

4. Write to current/:
   - manifest.json (all objects, last_changed_in = "25.04.01.00.00")
   - objects/<uuid>.json (all 2,461 objects)
   - code/<uuid>.json (all objects with code)
   - bundles/<Name>.json (all bundles)
   - graph.json
   - search_index.json
   - app_overview.json
   - orphans_index.json
   - parsed_state.json

5. Create release_index.json:
   - One entry with is_baseline=true, change_summary=null

6. No changelog (baseline has nothing to compare against)
7. No release_snapshots (current IS the only release)
8. No history (nothing has changed yet)
```

### Subsequent Parse — New Release

```
1. Parse ZIP → 2,506 ParsedObjects
2. Extract version → "25.04.02.09.00"
3. Load current/manifest.json → previous version is "25.04.01.00.00"
4. Version differs → NEW RELEASE

5. Compare diff_hashes:
   For each new ParsedObject:
   ├── UUID in old manifest AND hash matches → UNCHANGED
   ├── UUID in old manifest AND hash differs → MODIFIED
   └── UUID not in old manifest → ADDED
   For full parse only — detect removals:
   └── UUID in old manifest but NOT in new ParsedObjects → REMOVED

6. PRE-WRITE: Snapshot current state
   - Copy manifest.json → release_snapshots/25.04.01.00.00/manifest.json
   - Copy app_overview.json → release_snapshots/25.04.01.00.00/app_overview.json

7. PRE-WRITE: Archive modified AND removed objects to history
   For each MODIFIED or REMOVED object:
   - Build complete snapshot from current objects/<uuid>.json + code/<uuid>.json
   - Write to history/<uuid>/25.04.01.00.00.json

8. WRITE: Update current/ (with smart write)
   - manifest.json (unchanged objects carry forward last_changed_in, changed objects get new version, removed objects deleted from manifest)
   - objects/<uuid>.json (all objects — smart write skips unchanged)
   - code/<uuid>.json (all objects — smart write skips unchanged)
   - For REMOVED objects: delete objects/<uuid>.json and code/<uuid>.json from current/
   - bundles/<Name>.json (all bundles — smart write skips unchanged)
   - graph.json, search_index.json, app_overview.json, orphans_index.json
   - parsed_state.json

9. POST-WRITE: Generate changelog
   - Write changelogs/25.04.02.09.00.json

10. POST-WRITE: Update release_index.json
    - Append new entry with change_summary

11. POST-WRITE: Prune if needed
    - If releases > max_retained_releases, delete oldest
```

### Daily Update (Delta, Same Version)

```
1. Parse delta ZIP → 3 ParsedObjects
2. Load parsed_state.json → 2,500 existing objects
3. Merge → 2,500 merged objects
4. Detect mode → version unchanged → DAILY UPDATE

5. Transform: resolve, analyze, enrich (full set)
6. Build all artifacts in memory

7. WRITE: Update current/ (with smart write)
   - ~3 object files changed
   - ~3 code files changed
   - ~5-10 bundle files changed
   - graph.json, search_index.json, app_overview.json updated
   - manifest.json, parsed_state.json updated

8. No changelog, no snapshot, no history, no release_index update
```

---

## Historical Object Lookup

When the MCP server needs to retrieve an object at a specific historical release:

```
Request: "Get object _a-0006eed1-... at release 25.04.01.00.00"

1. Read current/objects/<uuid>.json → get version_history array
2. Find the version_history entry matching the requested release
   (or the most recent entry at or before the requested release)
3. Route based on status:
   ├── "current"  → Return data from current/objects/<uuid>.json + current/code/<uuid>.json
   ├── "modified" → Read history/<uuid>/<version>.json (contains full snapshot)
   └── "added" (baseline) → No snapshot exists. Return message:
       "This is the earliest known version. Historical snapshot not available."
4. Return the object data
```

This approach requires only **1 file read** (the object file) to determine the routing, instead of loading a release snapshot manifest. The `version_history` array in the object file is the authoritative timeline.

If a `version_history` entry points to a version that has been pruned (older than retention window), the history file won't exist. The tool returns an error indicating the historical data is no longer available.

---

## Retention and Pruning

When the number of releases exceeds `max_retained_releases` (from `app_config.json`), the oldest release is pruned:

```
1. Delete release_snapshots/<oldest_version>/
2. Delete changelogs/<oldest_version>.json (if exists — baseline won't have one)
3. For each history/<uuid>/<oldest_version>.json → delete
4. Clean up empty history/<uuid>/ directories
5. Update release_index.json:
   - Remove the oldest entry
   - The next-oldest release becomes the effective baseline
   - Its change_summary is preserved for reference even though the detailed changelog is deleted
```

### Size Impact of Retention

For a ~2,500 object application with 5 retained releases and ~10% change rate per release:

| Component | Size |
|-----------|------|
| `current/` (excluding parsed_state) | ~21MB |
| `parsed_state.json` (not in git) | ~20MB |
| `release_snapshots/` (5 releases × ~1MB each) | ~5MB |
| `changelogs/` (5 releases × ~100KB each) | ~500KB |
| `history/` (~250 objects × ~2 versions × ~5KB) | ~2.5MB |
| **Total in git** | **~29MB** |
| **Total on disk** | **~49MB** |

---

## Design Decisions

### Object Removal Tracking (Full Parse Only)

Object removal is tracked **only in full parse mode**. When a full ZIP is parsed and an object exists in the previous manifest but is absent from the new parse, it is treated as removed.

**Full parse mode behavior:**
- Compare new object set against previous manifest
- Objects in old manifest but absent from new parse → status `removed`
- Before deletion: archive to `history/<uuid>/<old_version>.json` (same as modified objects)
- Delete `objects/<uuid>.json` and `code/<uuid>.json` from `current/`
- Remove from `manifest.json`, `graph.json`, `search_index.json`
- Remove from bundle `members` arrays (bundles are regenerated anyway)
- Add `"status": "removed"` entries to changelog's `object_changes`
- Add `objects_removed` count to changelog summary

**Delta parse mode behavior:**
- No deletion tracking. Absence from a delta does not mean deletion — Appian supports partial exports. An object missing from a delta package may simply not have been included in this export.
- Objects not in the delta remain as-is in `current/`

This distinction is safe because the two modes have clear semantics: a full ZIP is a complete snapshot of the application (absence = deletion), while a delta ZIP is a partial update (absence = not included).

### Linear Releases Only

Releases form a strictly ordered list. No branching (e.g., no 1.0 → 1.1 hotfix AND 1.0 → 2.0 feature branch simultaneously).

Rationale: Appian application releases are linear in practice. Supporting branching would add significant complexity with no practical benefit.

### History Files Are Complete Snapshots

History files include the full object data (code, parameters, dependencies) — not just metadata.

Rationale: The primary use case for history is "show me how this object looked in the previous release." Without the code, that question can't be fully answered. The storage cost is acceptable — only changed objects get history entries.

### Changelogs Are Precomputed

Changelogs are generated at parse time, not computed at query time.

Rationale: Computing a changelog requires loading two manifests and diffing them. This is fast (~10ms) but doing it at parse time means the MCP server can serve changelogs as a simple file read with no computation.

### Version Constant Excluded From Changelog

The application's version constant changes every release by definition. Including it in every changelog is noise.

### Graph Is Current-Release Only

`graph.json` is not included in release snapshots. Graph-level MCP tools only work for the current release.

Rationale: Graph files are 2-4MB each. Historical graph queries are extremely rare. The storage cost is not justified.

### Clean Start for Versioned Mode

When switching from flat output to versioned mode, treat it as a fresh baseline. No migration of existing flat output.

Rationale: The parser re-parses the ZIP anyway, so there's no wasted work. Migration logic would add complexity for a one-time operation.

---

## Open Questions

All questions resolved.

## Resolved Questions

1. ~~**Release snapshot scope**~~: **`app_overview.json` is sufficient.** It already contains the full bundle list with counts and key objects. No separate bundle index file needed in snapshots.

2. ~~**History file construction**~~: **From in-memory data.** During the "new release" flow, the previous `parsed_state.json` is already loaded into memory. Build history snapshots from that in-memory data — avoids the race condition of reading files about to be overwritten and avoids extra disk I/O.

3. ~~**Cross-release bundle comparison**~~: **Yes, include member diffs.** For modified bundles in the changelog, include `members_added` and `members_removed` arrays (`{name, type}` each). Computed by diffing old vs new `members` arrays by UUID. Enables "what objects joined or left this bundle in this release?" queries.

4. ~~**Retention of parsed_state.json across releases**~~: **Don't preserve.** The fallback to full parse (~2.5s) is already built into the delta command. Preserving old parsed_state files adds ~20MB per release for a rare edge case. Not worth the complexity.
