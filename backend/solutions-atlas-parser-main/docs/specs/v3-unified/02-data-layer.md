# 02 — Data Layer

The data layer is the on-disk data model that sits between the parser (writer) and the MCP server (reader). It defines where every piece of data lives, how files reference each other, and how duplication is eliminated.

---

## Design Principles

1. **Each object stored exactly once.** Object metadata lives in `objects/<uuid>.json`. SAIL code lives in `code/<uuid>.json`. No other file embeds or copies this data.

2. **Bundles are views, not copies.** A bundle file contains the entry point, the flow visualization, and a list of member UUIDs. It does not contain object metadata or code. The MCP server joins bundle data with object data via UUID lookup.

3. **The graph is a first-class artifact.** The complete dependency graph is persisted as `graph.json` — a single file with all nodes and all edges. It is not derived at query time from scattered object files.

4. **Current state is the fast path.** Everything the MCP server needs for the latest release lives under `current/`. Historical data lives in separate directories and is accessed only on demand.

5. **The manifest is the table of contents.** `manifest.json` maps every UUID to its core metadata (name, type, hash, version). It is the authoritative index of what exists and when it last changed.

6. **Parsed state is an internal cache.** `parsed_state.json` holds the full resolved object data for delta merging. The MCP server never reads it. It is not committed to git.

---

## Directory Layout

```
data/<AppName>/
│
├── app_config.json                    # App identity and settings
├── release_index.json                 # Ordered release history
│
├── current/                           # Source of truth for latest state
│   │
│   ├── manifest.json                  # Master index: uuid → metadata + hash + version
│   ├── parsed_state.json              # Full parsed data for delta merge (NOT in git)
│   │
│   ├── objects/                       # One file per object — canonical metadata
│   │   └── <uuid>.json
│   │
│   ├── code/                          # SAIL code separated from metadata
│   │   └── <uuid>.json
│   │
│   ├── bundles/                       # Lightweight bundle views
│   │   └── <BundleName>.json
│   │
│   ├── graph.json                     # Complete dependency graph
│   │
│   ├── search_index.json              # Name → uuid fast lookup
│   ├── app_overview.json              # Package metadata + summary stats
│   │
│   └── orphans_index.json             # Orphan UUID catalog
│
├── history/                           # Previous versions of changed objects
│   └── <uuid>/
│       └── <version>.json
│
├── changelogs/                        # Precomputed diffs between releases
│   └── <version>.json
│
└── release_snapshots/                 # Lightweight metadata from old releases
    └── <version>/
        ├── manifest.json
        └── app_overview.json
```

---

## File Schemas

### `app_config.json`

Per-application configuration. Lives alongside the data, not in the parser source. Created once per application and rarely modified.

```json
{
  "application_name": "GSS",
  "version_constant": "AS_GSS_CO_APP_VERSION",
  "max_retained_releases": 5
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `application_name` | string | yes | Human-readable application name |
| `version_constant` | string | yes | Name of the Appian constant that holds the version string. The parser finds this constant in the parsed objects and extracts the version. |
| `max_retained_releases` | int | yes | Maximum number of old releases to retain in history and snapshots. When exceeded, the oldest is pruned. |

---

### `current/manifest.json`

The master index. Maps every UUID to its core metadata and content hash. This is the single file that answers "what exists, what is it, and when did it last change?"

Used by:
- Delta parsing: compare diff_hashes to detect what changed
- Version history: `last_changed_in` tells you when each object was last modified
- MCP server: quick metadata lookup without loading individual object files

```json
{
  "_metadata": {
    "version": "25.04.03.00.00",
    "total_objects": 2520,
    "generated_at": "2026-03-26T16:00:00Z"
  },
  "objects": {
    "_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398": {
      "name": "AS_GSS_BL_validateLPTAScores",
      "type": "Expression Rule",
      "diff_hash": "b7d1e4a9c3f2...",
      "last_changed_in": "25.04.02.09.00"
    },
    "_a-0007aab2-1234-5678-9abc-def000012345_43398": {
      "name": "AS_GSS_CO_APP_VERSION",
      "type": "Constant",
      "diff_hash": "e8f3a1b2c4d5...",
      "last_changed_in": "25.04.03.00.00"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Object name |
| `type` | string | Appian object type |
| `diff_hash` | string | SHA-512 content hash (from `DiffHashService`) |
| `last_changed_in` | string | Version where this object was last added or modified |

---

### `current/objects/<uuid>.json`

The canonical metadata file for each object. This is the **single source of truth** for an object's structured data — everything except SAIL code.

This file is richer than the current `objects/<uuid>.json` (which only has dependency data). It now includes all the metadata that bundles currently embed inline: description, parameters, inputs, test cases, hub/orphan flags, and full dependency info with UUIDs.

```json
{
  "uuid": "_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "description": "Validates LPTA scores against minimum thresholds",
  "diff_hash": "b7d1e4a9c3f2...",

  "bundles": ["AS_GSS_Complete_LPTA_Evaluation", "AS_GSS_Review_Scores"],
  "is_hub": false,
  "is_orphan": false,
  "inbound_count": 12,
  "outbound_count": 4,

  "calls": [
    {
      "uuid": "_b-0007ffa2-...",
      "name": "AS_CO_UT_isBlank",
      "type": "Expression Rule",
      "dep_type": "CALLS"
    }
  ],
  "called_by": [
    {
      "uuid": "_c-0008aab3-...",
      "name": "AS_GSS_PM_CompleteLPTAEvaluation",
      "type": "Process Model",
      "dep_type": "CALLS"
    }
  ],

  "type_specific": {
    "inputs": [
      {"name": "scores", "type": "Number(Integer)", "description": "LPTA scores to validate"}
    ],
    "output_type": "Boolean",
    "test_cases": []
  },

  "version_history": [
    {"version": "25.04.03.00.00", "status": "current", "diff_hash": "b7d1e4a9c3f2..."},
    {"version": "25.04.02.09.00", "status": "modified", "diff_hash": "a3f9c2e1b4d7..."},
    {"version": "25.04.01.00.00", "status": "added", "diff_hash": "x1y2z3a4b5c6..."}
  ]
}
```

**Field groups:**

| Group | Fields | Description |
|-------|--------|-------------|
| Identity | `uuid`, `name`, `type`, `description`, `diff_hash` | Core identity, same across all object types |
| Bundle membership | `bundles`, `is_hub`, `is_orphan` | Which bundles contain this object, classification flags |
| Dependencies | `calls`, `called_by`, `inbound_count`, `outbound_count` | Full dependency info with UUIDs for direct navigation |
| Type-specific | `type_specific` | Fields that vary by object type (see below) |
| Version history | `version_history` | Lightweight timeline of all releases where this object was added or modified. Each entry has `version`, `status` (`added`, `modified`, or `current`), and `diff_hash`. The `current` entry always comes first and matches the top-level `diff_hash`. Full historical snapshots (metadata + code) live in `history/<uuid>/<version>.json` — loaded only when the agent requests a specific historical version. |

**Version history details:**

The `version_history` array is ordered newest-first. It only contains entries for releases where the object changed — unchanged releases are not listed. At ~70 bytes per entry with 5 retained releases, this adds at most ~350 bytes to the object file.

**Important: daily updates do NOT add version_history entries.** When a delta parse runs within the same release version (daily update), the `current` entry's `diff_hash` is updated in place if the object changed, but no new entry is appended. Version history tracks *releases*, not individual parses. This prevents the array from growing unboundedly during active development within a sprint.

This solves two problems:
1. **Self-describing objects**: the MCP server can answer "when was this object last changed?" and "how many times has it changed?" from a single file read, without loading manifests or history files.
2. **Baseline gap**: the baseline entry has `"status": "added"`. There is no snapshot file for the baseline version (nothing existed before it). The `get_object_at_release` tool can detect this and return a clear message: "This is the earliest known version of this object."

**Type-specific fields by object type:**

| Object Type | `type_specific` Contents |
|-------------|--------------------------|
| Expression Rule | `inputs`, `output_type`, `test_cases` |
| Interface | `parameters` (name, type, default_value) |
| Process Model | `variables`, `total_nodes`, `complexity_score`, `start_form_interface` |
| Record Type | `fields`, `relationships`, `views`, `actions`, `data_source` |
| CDT | `namespace`, `fields` |
| Integration | `connected_system`, `http_method`, `url` |
| Web API | `http_method`, `url_alias`, `security` |
| Site | `pages` (hierarchical structure) |
| Constant | `value`, `value_type`, `scope` |
| Connected System | `base_url`, `auth_type` |
| Control Panel | `interfaces`, `primary_record_type` |
| Group | `group_type`, `parent_group` |
| Translation Set | `default_locale`, `enabled_locales` |
| Translation String | `translations` (locale → text) |

The `type_specific` field is a dict whose schema depends on the object type. This keeps the top-level schema consistent across all types while allowing type-specific richness.

---

### `current/code/<uuid>.json`

SAIL code for a single object. Separated from metadata so the MCP server can load metadata without paying the cost of loading code.

Only objects that have code get a file here. Constants, Groups, Translation Sets, and CDTs typically have no SAIL code.

```json
{
  "uuid": "_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "sail_code": "if(rule!AS_CO_UT_isBlank(ri!scores), false, ri!scores > cons!AS_GSS_MIN_SCORE)"
}
```

For Process Models, the `sail_code` field contains the concatenated node expressions (same extraction logic as the current `BundleCodeBuilder._extract_code()`).

**Size characteristics:**
- Expression Rules: 0.5-5KB typical
- Interfaces: 2-50KB (complex forms can be large)
- Process Models: 1-20KB (concatenated node expressions)
- Web APIs: 1-10KB

---

### `current/bundles/<BundleName>.json`

A bundle is now a **lightweight view** — it describes a functional flow and lists its member objects by UUID. It does not embed any object data.

This is the most significant structural change from the current system. Today, a bundle is two files (`structure.json` + `code.json`) that together contain complete copies of all member objects. In the new system, a bundle is a single file that references objects.

```json
{
  "_metadata": {
    "bundle_id": "AS_GSS_Complete_LPTA_Evaluation",
    "bundle_type": "action",
    "root_name": "AS GSS Complete LPTA Evaluation",
    "parent_name": "AS GSS Evaluation RECORD",
    "object_count": 282
  },

  "entry_point": {
    "action_type": "START_PROCESS",
    "record_type": "AS GSS Evaluation RECORD",
    "target_process": "AS_GSS_PM_CompleteLPTAEvaluation",
    "form_interface": "AS_GSS_IF_CompleteLPTAEvaluation",
    "expressions": {
      "TITLE": "Complete LPTA Evaluation"
    }
  },

  "flow": {
    "process_model": {
      "name": "AS_GSS_PM_CompleteLPTAEvaluation",
      "complexity_score": 12,
      "total_nodes": 8,
      "nodes": [
        {
          "name": "Start",
          "type": "START",
          "next": ["Complete LPTA Evaluation"]
        },
        {
          "name": "Complete LPTA Evaluation",
          "type": "USER_INPUT",
          "interface": "AS_GSS_IF_CompleteLPTAEvaluation",
          "next": ["Validate Scores"]
        }
      ]
    }
  },

  "members": [
    {"uuid": "_a-0006eed1-...", "name": "AS_GSS_PM_CompleteLPTAEvaluation", "type": "Process Model"},
    {"uuid": "_b-0007ffa2-...", "name": "AS_GSS_IF_CompleteLPTAEvaluation", "type": "Interface"},
    {"uuid": "_c-0008aab3-...", "name": "AS_GSS_BL_validateLPTAScores", "type": "Expression Rule"}
  ],

  "key_objects": [
    "AS_GSS_PM_CompleteLPTAEvaluation",
    "AS_GSS_IF_CompleteLPTAEvaluation",
    "AS_GSS_BL_validateLPTAScores"
  ]
}
```

**What's in the bundle:**
- `_metadata`: Bundle identity and summary stats
- `entry_point`: Type-specific entry point details (same as current `BundleStructureBuilder._build_entry_point()`)
- `flow`: Process model flow graph (same as current `BundleStructureBuilder._build_flow()`)
- `members`: Lightweight member catalog — `{uuid, name, type}` for every object in the bundle. This is the key field that enables the MCP server to answer "list all objects in this bundle" with a single file read, without loading individual object files. At ~60 bytes per member, a 282-object bundle adds ~17KB — a small cost that eliminates 282 API calls.
- `key_objects`: Top 5 most-connected objects by name (for quick reference)

**What's NOT in the bundle:**
- Full object metadata (description, parameters, calls, called_by, type_specific) — lives in `objects/<uuid>.json`
- SAIL code — lives in `code/<uuid>.json`

**Why `members` is not duplication:**

The `members` array contains only identity fields (`uuid`, `name`, `type`) — the minimum needed for listing and filtering. The full object data (description, dependencies, parameters, type-specific fields) exists only in `objects/<uuid>.json`. This is a deliberate denormalization for query performance: the MCP server's most common operation is "show me what's in this bundle," and it must be answerable with a single file read.

When an object is renamed or its type changes (rare), smart write detects the change and rewrites all bundles containing that object. This is the same mechanism that already rewrites bundles when member objects change.

**How the MCP server loads a bundle:**

1. **Summary query** ("show me this bundle"): Read `bundles/<BundleName>.json` — get entry_point, flow, and `members` list. **One file read.** This is the same cost as today's summary mode.
2. **Object detail** ("tell me about this rule in the bundle"): Read `objects/<uuid>.json` for the specific object — get full metadata and dependencies. **One additional file read.**
3. **Code inspection** ("show me the code for this rule"): Read `code/<uuid>.json` — get SAIL code. **One additional file read.**

The key insight: the MCP server never needs to load all 282 object files at once. It loads the bundle summary (1 read), then selectively loads individual objects as the agent drills in. This is strictly better than the current system where `detail_level=structure` loads 143KB of embedded object data whether the agent needs it or not.

**Deduplication impact:**

Consider an expression rule that appears in 50 bundles:
- **Current system**: 50 copies of full metadata in `structure.json` files + 50 copies of code in `code.json` files = 100 full copies
- **New system**: 1 copy of full metadata in `objects/<uuid>.json` + 1 copy of code in `code/<uuid>.json` + 50 lightweight references (`{uuid, name, type}`) in bundle files = 2 full copies + 50 pointers (~3KB total)

---

### `current/graph.json`

The complete dependency graph as a flat property graph. Every parsed object is a node. Every dependency is a typed edge. This is the file the MCP server loads once and traverses for graph-level queries.

```json
{
  "_metadata": {
    "schema_version": "1.0",
    "node_count": 2461,
    "edge_count": 5234,
    "hub_threshold": 10
  },
  "nodes": [
    {
      "id": "_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398",
      "name": "AS_GSS_BL_validateLPTAScores",
      "type": "Expression Rule",
      "bundles": ["AS_GSS_Complete_LPTA_Evaluation", "AS_GSS_Review_Scores"],
      "inbound_count": 12,
      "outbound_count": 4,
      "is_hub": false,
      "is_orphan": false
    }
  ],
  "edges": [
    {
      "from": "_a-0006eed1-...",
      "to": "_b-0007ffa2-...",
      "type": "CALLS"
    }
  ]
}
```

**Node fields:**

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `id` | string | `ParsedObject.uuid` | Unique identifier |
| `name` | string | `ParsedObject.name` | Human-readable name |
| `type` | string | `ParsedObject.object_type` | Appian object type |
| `bundles` | string[] | `bundle_assignments[uuid]` | Bundles containing this object |
| `inbound_count` | int | computed from edges | How many objects call this one |
| `outbound_count` | int | computed from edges | How many objects this one calls |
| `is_hub` | bool | `inbound_count >= hub_threshold` | True if widely-shared utility |
| `is_orphan` | bool | `bundles == []` | True if not reachable from any entry point |

**Edge types** (already defined in `domain/constants.py`):

| Edge Type | Description |
|-----------|-------------|
| `CALLS` | Expression rule call, interface usage, subprocess call, site page target |
| `USES_CONSTANT` | Constant reference |
| `USES_CDT` | CDT/data type reference |
| `USES_RECORD_TYPE` | Record type reference |
| `USES_INTEGRATION` | Integration call |
| `USES_CONNECTED_SYSTEM` | Connected system reference |
| `USES_GROUP` | Group reference |
| `USES_DATA_STORE` | Data store reference |

**Hub threshold**: Same constant already used in `BundleCoordinator._hub_uuids` (`_HUB_CALLER_THRESHOLD`). An Expression Rule with `inbound_count >= threshold` is classified as a hub.

**Size estimate**: For a 2,461-object app with 5,234 edges, approximately 2-4MB.

---

### `current/search_index.json`

Fast name-to-UUID lookup. Same purpose as today, with minor enrichments.

```json
{
  "AS_GSS_BL_validateLPTAScores": {
    "uuid": "_a-0006eed1-...",
    "type": "Expression Rule",
    "description": "Validates LPTA scores against minimum thresholds",
    "bundle_count": 2,
    "bundles": ["AS_GSS_Complete_LPTA_Evaluation", "AS_GSS_Review_Scores"],
    "deps_out": 4,
    "deps_in": 12
  }
}
```

No structural change from current. The MCP server uses this for name resolution before loading object files.

---

### `current/app_overview.json`

Package metadata, object counts, bundle index, dependency summary, and coverage stats. Same purpose as today.

```json
{
  "_metadata": {
    "parser_version": "3.0.0",
    "generated_at": "2026-03-26T16:00:00Z",
    "source_package": "SourceSelection v2.8.0.zip",
    "release_version": "25.04.03.00.00"
  },
  "package_info": {
    "filename": "SourceSelection v2.8.0.zip",
    "total_files_in_zip": 2639,
    "total_xml_files": 2567,
    "total_parsed_objects": 2461,
    "total_errors": 0,
    "parse_duration_seconds": 1.88
  },
  "object_counts": {
    "CDT": 107,
    "Constant": 582,
    "Expression Rule": 990,
    "Interface": 489,
    "Process Model": 117,
    "Record Type": 49
  },
  "bundles": [
    {
      "id": "AS_GSS_Complete_LPTA_Evaluation",
      "bundle_type": "action",
      "root_name": "AS GSS Complete LPTA Evaluation",
      "parent_name": "AS GSS Evaluation RECORD",
      "object_count": 282,
      "key_objects": ["AS_GSS_PM_CompleteLPTAEvaluation", "AS_GSS_IF_CompleteLPTAEvaluation"]
    }
  ],
  "dependency_summary": {
    "total": 5234,
    "by_type": {
      "CALLS": 3421,
      "USES_CONSTANT": 654,
      "USES_RECORD_TYPE": 512
    },
    "most_depended_on": [
      {"name": "AS_CO_UT_isBlank", "type": "Expression Rule", "inbound_count": 1247}
    ]
  },
  "coverage": {
    "total_objects": 2461,
    "bundled": 1898,
    "orphaned": 563
  }
}
```

The addition of `release_version` in `_metadata` ties this overview to a specific release.

---

### `current/orphans_index.json`

A flat index of orphaned objects (not reachable from any entry point). Replaces the current `orphans/` directory with individual files.

```json
{
  "_metadata": {
    "total_orphans": 563
  },
  "by_type": {
    "Expression Rule": 342,
    "Interface": 156,
    "Constant": 65
  },
  "orphans": [
    {
      "uuid": "_orphan-1-...",
      "name": "AS_GSS_DEPRECATED_OldRule",
      "type": "Expression Rule"
    }
  ]
}
```

Orphan objects are regular objects — their metadata lives in `objects/<uuid>.json` and their code lives in `code/<uuid>.json`, same as bundled objects. The `is_orphan: true` flag in the object file and the `orphans_index.json` catalog are the only things that distinguish them.

This eliminates the current duplication where orphan files contain embedded code that also exists (or should exist) in the object store.

---

### `current/parsed_state.json`

The full parsed object data for every object, serialized as a single JSON file. This is the **internal cache** that enables delta parsing. The MCP server never reads it. It is not committed to git.

```json
{
  "_metadata": {
    "version": "25.04.02.09.00",
    "total_objects": 2506,
    "generated_at": "2026-03-26T16:00:00Z"
  },
  "objects": {
    "_a-0006eed1-...": {
      "name": "AS_GSS_BL_validateLPTAScores",
      "object_type": "Expression Rule",
      "diff_hash": "b7d1e4a9c3f2...",
      "source_file": "AS_GSS_BL_validateLPTAScores.xml",
      "data": {
        "uuid": "_a-0006eed1-...",
        "name": "AS_GSS_BL_validateLPTAScores",
        "description": "Validates LPTA scores against minimum thresholds",
        "sail_code": "if(rule!AS_CO_UT_isBlank(ri!scores), false, ...)",
        "inputs": [...],
        "output_type": "Boolean"
      }
    }
  }
}
```

Key properties:
- Contains the **resolved** data (UUIDs already replaced with names in SAIL code)
- Contains the **complete** `ParsedObject.data` dict — everything the type-specific parser produced
- Single file for fast load (~0.3s for 20MB) vs loading 2,500 individual files (~3s)
- Size: 15-50MB depending on application size
- Not committed to git — cached by CI between pipeline runs

---

## How Deduplication Works

The current system has three sources of duplication:

| Duplication Source | Current | New |
|-------------------|---------|-----|
| Object metadata in bundles | Copied into every bundle's `structure.json` | Lightweight `{uuid, name, type}` in bundle's `members` array; full metadata in `objects/<uuid>.json` |
| SAIL code in bundles | Copied into every bundle's `code.json` | Stored once in `code/<uuid>.json` |
| Orphan data | Separate `orphans/<uuid>.json` with embedded code | Same `objects/` and `code/` files, flagged `is_orphan: true` |

After this change, every piece of object data exists in exactly two files:
1. `objects/<uuid>.json` — metadata and dependencies
2. `code/<uuid>.json` — SAIL code (if applicable)

Everything else (bundles, graph, search index, orphan index) references objects by UUID.

---

## File Size Estimates

For a ~2,500 object application:

| File/Directory | Count | Per-File Size | Total Size |
|---------------|-------|---------------|------------|
| `manifest.json` | 1 | ~500KB | ~500KB |
| `objects/<uuid>.json` | 2,500 | ~1-3KB | ~5MB |
| `code/<uuid>.json` | ~1,800 | ~2-10KB | ~10MB |
| `bundles/<Name>.json` | ~215 | ~5-20KB | ~2MB |
| `graph.json` | 1 | ~3MB | ~3MB |
| `search_index.json` | 1 | ~500KB | ~500KB |
| `app_overview.json` | 1 | ~50KB | ~50KB |
| `orphans_index.json` | 1 | ~30KB | ~30KB |
| `parsed_state.json` | 1 | ~20MB | ~20MB (not in git) |
| **Total (in git)** | | | **~21MB** |
| **Total (on disk)** | | | **~41MB** |

Compare to current system: ~28MB in git (with significant duplication across bundles).

The new system is slightly smaller in git despite being richer, because duplication is eliminated. The `parsed_state.json` adds ~20MB on disk but is not committed to git.

---

## Relationship Between Files

```
manifest.json ──────────────────────────────────────────────────────
  │  (uuid → name, type, hash, last_changed_in)
  │
  ├──→ objects/<uuid>.json ──→ calls[].uuid ──→ objects/<uuid>.json
  │      (metadata, deps)       (navigable dependency links)
  │
  ├──→ code/<uuid>.json
  │      (SAIL code, loaded on demand)
  │
  ├──→ bundles/<Name>.json
  │      (members[].uuid → objects/<uuid>.json)
  │
  ├──→ graph.json
  │      (nodes[].id → objects/<uuid>.json)
  │      (edges[].from/to → nodes[].id)
  │
  └──→ search_index.json
         (name → uuid → objects/<uuid>.json)
```

The manifest is the root. Every other file either contains UUIDs that can be resolved through the manifest or through direct file path construction (`objects/<uuid>.json`).

---

## Legacy Mode

When the parser is invoked without `--data-dir` (the current `dump <zip> <output_dir>` usage), it writes a flat output directory that is compatible with the current MCP server. This is the legacy mode.

Legacy mode writes the same file types but in a flat structure without versioning:

```
output_dir/
├── app_overview.json
├── search_index.json
├── graph.json                  # NEW — always written
├── orphans_index.json          # NEW — replaces orphans/ directory
├── objects/                    # ENRICHED — richer than current
│   └── <uuid>.json
├── code/                       # NEW — separated from bundles
│   └── <uuid>.json
└── bundles/                    # RESTRUCTURED — references, not copies
    └── <BundleName>.json
```

Legacy mode does not write `manifest.json`, `parsed_state.json`, or any versioning artifacts. It is a clean, non-versioned output that can be used for one-off analysis.

**Legacy mode differences from versioned mode:**
- No `manifest.json`, `parsed_state.json`, or versioning directories (`history/`, `changelogs/`, `release_snapshots/`)
- Object files do NOT include `version_history` (meaningless without versioning)
- All other schemas are identical — `search_index.json` includes `description`, `objects/<uuid>.json` includes full metadata and `type_specific`, bundles use the `members` array format

---

## Resolved Questions

1. **Bundle file format — single file vs directory**: **Single file.** Code is no longer embedded, so there's no reason for a directory. A single file is simpler to manage, atomic to write, and easier to smart-write.

2. **Bundle loading performance**: **Solved by `members` array.** Each bundle file includes a `members` array with `{uuid, name, type}` for every member object. This enables the MCP server to answer "list all objects in this bundle" with a single file read (same cost as today's summary mode), while full object metadata and code are loaded selectively on demand. See the bundle schema above for details.

---

## Open Questions

All questions resolved.

## Resolved Questions

1. ~~**Object file — `type_specific` nesting**~~: **Resolved: Keep nested.** The `type_specific` key stays. Top-level schema is identical for all object types, making parsing predictable. The key acts as a natural boundary — everything above is universal, everything inside is type-dependent.

2. ~~**Code file — include metadata?**~~: **Resolved: Include `uuid`, `name`, `type`.** The ~50 bytes per file cost is negligible. The benefit is that code files are self-describing in git diffs, debugging, and when returned directly by `get_object_code`.

3. ~~**Graph node — how much metadata?**~~: **Resolved: Exclude `description`.** The graph is for traversal, not display. Adding ~250KB of descriptions to a file loaded into memory for every graph query isn't worth it. Display queries load the object file when needed.

4. ~~**Orphans — separate index vs flag only?**~~: **Resolved: Keep `orphans_index.json`.** It's ~30KB, enables `list_orphans` with a single file read, and avoids parsing the 3MB graph at query time.
