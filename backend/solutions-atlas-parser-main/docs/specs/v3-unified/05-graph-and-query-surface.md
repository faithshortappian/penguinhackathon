# 05 — Graph and Query Surface

This document describes the dependency graph artifact and the complete MCP server tool surface — both new tools and enhancements to existing tools. The graph enables a new class of queries that were previously impossible without loading and stitching together dozens of files.

---

## The Dependency Graph

### Why a Graph File?

Today, dependency information is scattered across individual `objects/<uuid>.json` files. Each file lists its own `calls` and `called_by`. To answer "what is the path from A to B?", the MCP server would need to:

1. Load A's object file → get its calls
2. For each call, load that object's file → get its calls
3. Repeat until B is found or depth limit reached

This is O(n) file reads for an n-hop path. For a 3-hop path in a 2,500-object app, that could mean loading hundreds of files.

With `graph.json`, the MCP server loads one file (~3MB), builds an in-memory adjacency structure, and answers any graph query in milliseconds.

### Graph Structure

The graph is a flat property graph with two arrays: `nodes` and `edges`. See [02-data-layer.md](./02-data-layer.md) for the full schema.

Key properties:
- Every parsed object is a node
- Every dependency is a directed, typed edge
- Nodes carry summary metadata (name, type, bundle membership, hub/orphan flags)
- Nodes do NOT carry code or full object data — the graph is for traversal, not display

### Hub Detection

Hub objects are Expression Rules with an inbound dependency count above a threshold (the same `_HUB_CALLER_THRESHOLD` used in `BundleCoordinator`). Hubs are utility rules like `AS_CO_UT_isBlank` that are called by hundreds of objects.

Hubs are important for two reasons:
1. **Bundle generation**: Hub outbound edges are not followed during BFS (prevents utility rules from pulling the entire app into every bundle)
2. **Graph queries**: Transitive dependency queries should treat hubs as leaf nodes to prevent result explosion

The `is_hub` flag on graph nodes enables the MCP server to apply the same pruning logic.

### Graph Loading Strategy

The graph is loaded lazily on first tool call and cached in memory for the session. The MCP server builds two derived structures from the raw graph:

```
node_index:  {uuid → node_dict}           # O(1) node lookup
name_index:  {lowercase_name → uuid}       # O(1) name resolution
adj_out:     {uuid → [(target_uuid, edge_type), ...]}  # outbound adjacency
adj_in:      {uuid → [(source_uuid, edge_type), ...]}  # inbound adjacency
```

These are built once per app per session. Subsequent graph queries reuse them.

---

## New MCP Tools: Graph Queries

### `get_dependency_path`

Find the shortest dependency path between two objects.

**Use cases**:
- `outbound`: "How does process model X end up calling expression rule Y?"
- `inbound`: "What entry points eventually reach this utility rule?"

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `from_name` | string | yes | | Source object name |
| `to_name` | string | yes | | Target object name |
| `max_hops` | int | no | 6 | Maximum path length (capped at 10) |
| `direction` | string | no | `outbound` | `outbound` follows calls (A→B→C), `inbound` follows callers (A←B←C) |

**Algorithm**: BFS over outbound or inbound edges (based on `direction`) from source to target. Returns the first (shortest) path found.

**Response**:
```json
{
  "found": true,
  "hops": 3,
  "path": [
    {"uuid": "_a-...", "name": "AS_GSS_PM_CompleteLPTAEvaluation", "type": "Process Model"},
    {"uuid": "_b-...", "name": "AS_GSS_IF_CompleteLPTAEvaluation", "type": "Interface"},
    {"uuid": "_c-...", "name": "AS_GSS_BL_validateLPTAScores", "type": "Expression Rule"}
  ],
  "edge_types": ["CALLS", "CALLS"]
}
```

If no path exists within `max_hops`:
```json
{
  "found": false,
  "hops": null,
  "path": [],
  "message": "No path found within 6 hops"
}
```

---

### `get_transitive_dependencies`

Get all objects reachable from a given object up to N hops.

**Use cases**:
- `outbound`: "What does this process model transitively touch?"
- `inbound`: "What would break if I changed this object?"

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `object_name` | string | yes | | Starting object name |
| `max_hops` | int | no | 3 | Maximum traversal depth (capped at 5) |
| `edge_types` | list[str] | no | all | Filter by edge type (e.g., only `CALLS`) |
| `direction` | string | no | `outbound` | `outbound` follows calls (what does X depend on?), `inbound` follows callers (what depends on X?) |

**Algorithm**: BFS from the named object over outbound or inbound edges (based on `direction`). Hub objects are included as leaf nodes but their edges in the traversal direction are NOT followed (same pruning as bundle generation).

**Response**:
```json
{
  "root": {"uuid": "_a-...", "name": "AS_GSS_PM_CompleteLPTAEvaluation", "type": "Process Model"},
  "max_hops": 3,
  "total_reachable": 47,
  "by_type": {
    "Expression Rule": 28,
    "Interface": 12,
    "Constant": 5,
    "Integration": 2
  },
  "objects": [
    {"uuid": "_b-...", "name": "AS_GSS_IF_CompleteLPTAEvaluation", "type": "Interface", "depth": 1},
    {"uuid": "_c-...", "name": "AS_GSS_BL_validateLPTAScores", "type": "Expression Rule", "depth": 2}
  ]
}
```

Result `objects` list capped at 200 entries. If exceeded, a `"truncated": true` flag is added.

---

### `get_hub_objects`

Return the most-depended-on objects in the application.

**Use case**: "What are the shared utility rules I should know about?"

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `top_n` | int | no | 20 | Number of results (capped at 100) |
| `object_type` | string | no | all | Filter by object type |

**Algorithm**: Sort graph nodes by `inbound_count` descending, optionally filter by type.

**Response**:
```json
[
  {
    "uuid": "_a-...",
    "name": "AS_CO_UT_isBlank",
    "type": "Expression Rule",
    "inbound_count": 1247,
    "outbound_count": 3,
    "is_hub": true,
    "bundles_count": 89
  }
]
```

---

### `get_object_code`

Get the SAIL code for a specific object by name.

**Use case**: "Show me the implementation of this expression rule."

This is the tool that closes the biggest gap in the current MCP server. Today, to see one object's code, the agent must load an entire bundle's `code.json` (50-228KB) and extract one entry. With the new `code/<uuid>.json` separation, this tool loads a single small file.

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `object_name` | string | yes | | Object name (case-insensitive) |
| `release` | string | no | latest | Version string for historical lookup |

**Algorithm**:
1. Resolve name to UUID via `search_index.json`
2. If `release` is latest or omitted → read `current/code/<uuid>.json`
3. If `release` is historical → read `history/<uuid>/<last_changed_in>.json` and extract `sail_code`
4. If the object has no code (Constants, Groups, CDTs, Translation Sets) → return a message indicating no code is available for this object type

**Response**:
```json
{
  "uuid": "_a-0006eed1-...",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "sail_code": "if(rule!AS_CO_UT_isBlank(ri!scores), false, ri!scores > cons!AS_GSS_MIN_SCORE)"
}
```

**Why a separate tool (not a parameter on `get_object_detail`):**
- `get_object_detail` returns metadata (~2KB) — fast, always useful as a first step
- SAIL code can be 2-50KB — loading it when the agent only needs parameters or dependencies wastes context
- The agent explicitly decides when to load code, preventing accidental context bloat
- Matches the file separation: `objects/<uuid>.json` (metadata) vs `code/<uuid>.json` (code)

---

## New MCP Tools: Version Queries

These tools enable the MCP server to answer questions about release history, changes, and object evolution. They read from `release_index.json`, `changelogs/`, `release_snapshots/`, and `history/`.

### `list_releases`

List all releases for an application with metadata and change summaries.

**Use case**: "What releases exist for this app? What changed in each?"

**Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | yes | Application name |

**Response**:
```json
{
  "application": "GSS",
  "total_releases": 3,
  "latest_release": "25.04.03.00.00",
  "releases": [
    {
      "version": "25.04.03.00.00",
      "solution_version": "03.00.00",
      "parsed_at": "2026-03-26T16:00:00Z",
      "total_objects": 2520,
      "total_bundles": 220,
      "is_baseline": false,
      "change_summary": {
        "objects_added": 14,
        "objects_modified": 52,
        "objects_unchanged": 2454
      }
    }
  ]
}
```

---

### `get_changelog`

Get detailed changes for a specific release.

**Use case**: "What exactly changed in release 25.04.02.09.00?"

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `release` | string | yes | | Version string |
| `filter_type` | string | no | all | Filter object changes by type |
| `filter_status` | string | no | all | Filter by status: `added` or `modified` |
| `filter_bundle` | string | no | all | Filter to changes affecting a specific bundle |

**Response**: The changelog JSON (see [04-versioning-and-history.md](./04-versioning-and-history.md)), optionally filtered.

---

### `compare_releases`

Compare any two releases, not just adjacent ones.

**Use case**: "What changed between version 1.0 and version 3.0?"

**Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | yes | Application name |
| `from_release` | string | yes | Older version string |
| `to_release` | string | yes | Newer version string |

**Algorithm**:
- If adjacent releases: return the precomputed changelog
- If non-adjacent: load both manifests, diff the `objects` dicts by comparing diff_hashes

**Response**:
```json
{
  "from_release": "25.04.01.00.00",
  "to_release": "25.04.03.00.00",
  "is_adjacent": false,
  "summary": {
    "objects_added": 59,
    "objects_modified": 124,
    "objects_unchanged": 2337
  },
  "object_changes": [...]
}
```

Non-adjacent comparisons only include object-level diffs (not bundle-level), since bundle structures are only captured in adjacent changelogs.

---

### `get_object_history`

View how a specific object evolved across releases.

**Use case**: "How has this expression rule changed over time?"

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `object_name` | string | yes | | Object name |
| `include_data` | bool | no | false | Include full object data for each changed version |

**Algorithm**:
1. Resolve name to UUID via search index
2. Read `objects/<uuid>.json` → get `version_history` array
3. The timeline is already built — `version_history` contains every release where this object changed, with status and diff_hash
4. If `include_data=true`: for each non-baseline entry, read `history/<uuid>/<version>.json`; for the `current` entry, return data from the object file itself

This is **1 file read** for the basic timeline (no manifest walking needed), plus N reads only if `include_data=true`.

**Response**:
```json
{
  "uuid": "_a-0006eed1-...",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "first_seen": "25.04.01.00.00",
  "last_changed": "25.04.03.00.00",
  "total_versions": 3,
  "history": [
    {
      "version": "25.04.03.00.00",
      "status": "current",
      "diff_hash": "b7d1e4..."
    },
    {
      "version": "25.04.02.09.00",
      "status": "modified",
      "diff_hash": "a3f9c2..."
    },
    {
      "version": "25.04.01.00.00",
      "status": "added",
      "diff_hash": "x1y2z3..."
    }
  ]
}
```

---

### `get_object_at_release`

Get the full object data as it was at a specific release.

**Use case**: "Show me what this rule looked like in version 1.0"

**Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | yes | Application name |
| `object_name` | string | yes | Object name |
| `release` | string | yes | Version string |

**Algorithm**:
1. Resolve name to UUID via search index
2. Read `objects/<uuid>.json` → get `version_history` array
3. Find the entry matching the requested release, or the most recent entry at or before the requested release
4. If the matching entry has `"status": "current"` → return data from `current/objects/<uuid>.json` + `current/code/<uuid>.json`
5. If the matching entry has `"status": "modified"` → return data from `history/<uuid>/<version>.json`
6. If the matching entry has `"status": "added"` and it's the baseline → return a message: "This is the earliest known version. No historical snapshot exists for the baseline release. The object may have been modified since — check `version_history` for later versions."
7. If the requested release predates the object's `first_seen` → return: "Object did not exist in this release."

---

### `get_release_impact`

Bundle-focused view of a release's changes.

**Use case**: "Which functional flows were affected by this release?"

**Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | yes | Application name |
| `release` | string | yes | Version string |

**Response**:
```json
{
  "release": "25.04.02.09.00",
  "total_bundles_affected": 27,
  "bundles_added": [...],
  "bundles_modified": [
    {
      "bundle_id": "AS_GSS_Complete_LPTA_Evaluation",
      "bundle_type": "action",
      "objects_added": 2,
      "objects_modified": 8,
      "changed_objects": [
        {"name": "AS_GSS_BL_validateLPTAScores", "type": "Expression Rule", "status": "modified"}
      ]
    }
  ],
  "bundles_removed": [...]
}
```

---

## Enhanced Existing Tools

All existing MCP tools gain an optional `release` parameter. When omitted, they read from `current/` (latest release). When provided, they read from the appropriate historical location.

### Routing Logic

```
release = None or latest  → read from current/
release = older version   → depends on file type:
  - manifest, app_overview → read from release_snapshots/<version>/
  - objects/<uuid>.json    → historical lookup via manifest's last_changed_in
  - bundles, graph, orphans → NOT AVAILABLE for historical releases
```

### Enhanced Tools Summary

| Tool | Change | Historical Support |
|------|--------|-------------------|
| `get_app_overview` | Add optional `release` param | Yes — from release snapshot |
| `search_objects` | Add `release`, `limit` params; response includes `description` | Yes — from snapshot's search index or manifest |
| `search_bundles` | Add optional `release` param | Current release only (full bundles not in snapshots) |
| `get_bundle` | Add `release`, `object_type`, `limit` params | Current release only |
| `get_dependencies` | Add optional `release` param | Yes — from history files |
| `get_object_detail` | Add optional `release` param | Yes — from history files |
| `get_object_code` | **New tool** — dedicated code retrieval | Yes — from history files |
| `list_orphans` | Add `object_type`, `limit` params | Current release only |

**Important limitation**: `get_bundle`, `search_bundles` (full content), `list_orphans`, and graph tools are only available for the current release. Release snapshots don't include full bundle, orphan, or graph data. If a user requests these for an old release, the tool returns an error explaining the limitation.

### Backward Compatibility

If an application has NOT been parsed in versioned mode (no `release_index.json`), the MCP server falls back to the current behavior — reading directly from the flat output directory. The `release` parameter is ignored with a warning.

### Enhanced `get_bundle`

The current `get_bundle` tool has three detail levels (`summary`, `structure`, `full`) but no way to filter or paginate the object list. For a 282-object bundle, even the summary dumps all 282 entries into the agent's context. The enhanced version adds filtering and pagination.

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `bundle_id` | string | yes | | Bundle ID or root name (same resolution as today) |
| `object_type` | string | no | all | Filter members by Appian type (e.g. `Interface`, `Expression Rule`, `Process Model`) |
| `limit` | int | no | 50 | Max members to return in response (capped at 200) |
| `release` | string | no | latest | Version string (current release only for bundles) |

**Response**:
```json
{
  "_metadata": {
    "bundle_id": "AS_GSS_Complete_LPTA_Evaluation",
    "bundle_type": "action",
    "root_name": "AS GSS Complete LPTA Evaluation",
    "parent_name": "AS GSS Evaluation RECORD",
    "object_count": 282
  },
  "entry_point": { ... },
  "flow": { ... },
  "members": [
    {"uuid": "_a-...", "name": "AS_GSS_IF_CompleteLPTAEvaluation", "type": "Interface"},
    {"uuid": "_b-...", "name": "AS_GSS_IF_ScoreEntry", "type": "Interface"}
  ],
  "key_objects": ["AS_GSS_PM_CompleteLPTAEvaluation", ...],
  "member_summary": {
    "total": 282,
    "returned": 50,
    "by_type": {
      "Expression Rule": 180,
      "Interface": 45,
      "Constant": 30,
      "Process Model": 12,
      "Record Type": 8,
      "Integration": 5,
      "CDT": 2
    }
  }
}
```

The `member_summary` field is always included and shows the full breakdown by type, even when `object_type` or `limit` filters are applied. This lets the agent know what's available without loading everything. For example, the agent sees `"Interface": 45` and can follow up with `get_bundle(..., object_type="Interface")` to see just those.

**Filtering is in-memory**: the MCP server reads the single bundle file, filters the `members` array by type, truncates to `limit`, and returns. No additional file reads.

---

### Enhanced `search_objects`

The current `search_objects` tool returns `{name, uuid, type, bundles, inbound_count, outbound_count}` — no description. The agent always needs a follow-up `get_object_detail` call just to understand what an object does. The enhanced version includes `description` from the enriched search index and adds pagination control.

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `query` | string | yes | | Case-insensitive substring match against object names |
| `object_type` | string | no | all | Filter by Appian type (e.g. `Interface`, `Expression Rule`) |
| `limit` | int | no | 20 | Max results to return (capped at 100) |
| `release` | string | no | latest | Version string for historical lookup |

**Response**:
```json
{
  "total_matches": 47,
  "returned": 20,
  "results": [
    {
      "name": "AS_GSS_BL_validateLPTAScores",
      "uuid": "_a-0006eed1-...",
      "type": "Expression Rule",
      "description": "Validates LPTA scores against minimum thresholds",
      "bundle_count": 2,
      "deps_in": 12,
      "deps_out": 4
    }
  ]
}
```

The `description` field eliminates the need for a follow-up call in most cases — the agent can see what each matching object does directly from the search results. The `total_matches` field tells the agent if there are more results beyond the `limit`.

---

### Enhanced `list_orphans`

The current `list_orphans` tool dumps the entire orphan index (81KB, 573 objects) with no filtering. The enhanced version adds type filtering and pagination.

**Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_name` | string | yes | | Application name |
| `object_type` | string | no | all | Filter by Appian type |
| `limit` | int | no | 50 | Max results to return (capped at 200) |

**Response**:
```json
{
  "total_orphans": 563,
  "returned": 50,
  "by_type": {
    "Expression Rule": 342,
    "Interface": 156,
    "Constant": 65
  },
  "orphans": [
    {"uuid": "_orphan-1-...", "name": "AS_GSS_DEPRECATED_OldRule", "type": "Expression Rule"}
  ]
}
```

The `by_type` summary is always returned regardless of filters, so the agent can see the full breakdown and decide which types to drill into. Filtering and pagination are in-memory on the `orphans_index.json` data.

---

## How the MCP Server Loads Bundles (New Pattern)

The biggest change for the MCP server is how bundles are loaded. Today, a bundle is self-contained — `structure.json` has all object metadata and `code.json` has all code. The MCP server reads two files and has everything.

In the new system, a bundle file contains structure and UUID references. The MCP server must join bundle data with object data.

### Loading Strategy

**For "show me this bundle" queries (summary):**

1. Read `bundles/<BundleName>.json` → get entry_point, flow, and `members` array
2. Return bundle structure + member list (name, type for each object)

This is **1 file read** — the same cost as today's summary mode. The `members` array in the bundle file contains `{uuid, name, type}` for every member object, so the MCP server can list and filter objects without loading individual object files.

**For "tell me about object X in this bundle" queries (drill-down):**

1. Read `objects/<uuid>.json` for the specific object → get full metadata, dependencies, type-specific fields

This is **1 file read**. The agent drills into specific objects selectively, not all 282 at once.

**For "show me the code for object X" queries:**

1. Read `code/<uuid>.json` → get SAIL code

This is **1 file read**. Each code file contains a single object's SAIL code, so the agent loads exactly what it needs.

**For "list objects of type Interface in this bundle" queries (filtered):**

1. Read `bundles/<BundleName>.json` → get `members` array
2. Filter in-memory by `type == "Interface"`
3. Return filtered list

This is **1 file read** with in-memory filtering. No need to load individual object files.

### Comparison with Current System

| Query | Current System | New System |
|-------|---------------|------------|
| Bundle summary | 1 read (structure.json, 143KB) | 1 read (bundle.json, ~30KB) |
| Bundle + all object details | 1 read (structure.json, 143KB) | 1 + N reads (selective) |
| Bundle + code | 2 reads (structure.json + code.json, 371KB) | 1 + N reads (selective) |
| Single object code | 1 read (code.json, 228KB, extract 1 entry) | 1 read (code/uuid.json, ~5KB) |
| Single object metadata | Not available separately | 1 read (objects/uuid.json, ~2KB) |

The new system trades "load everything in 1-2 large reads" for "load exactly what you need in 1+ small reads." For the most common query (bundle summary), the cost is identical: 1 read. For drill-down queries, the new system is more efficient because it loads only the requested object instead of the entire bundle.

### Caching

The MCP server should cache frequently-accessed object files in memory. A simple LRU cache keyed by `(app_name, uuid)` would eliminate repeated reads for objects that appear in multiple queries or bundles.

### Cache Invalidation

When the data layer is refreshed (new parse pushed to GitLab), the MCP server's in-memory caches become stale. The invalidation strategy uses **manifest-based staleness detection**:

1. The MCP server stores `last_known_generated_at` per `app_name` (from `manifest.json`'s `_metadata.generated_at` field).
2. Every 5 minutes (or every 10th tool call, whichever comes first), the server fetches `manifest.json`'s `_metadata` for each active app — one lightweight GitLab API call per app.
3. If `generated_at` differs from `last_known_generated_at` → flush all caches for that app:
   - Pinned files (`app_overview.json`, `search_index.json`, `orphans_index.json`)
   - LRU object/code/bundle cache
   - In-memory graph (`adj_out`, `adj_in`, `node_index`, `name_index`)
4. Caches repopulate lazily on the next tool call.

**Why this approach:**
- No infrastructure changes — works with the existing GitLab API data source
- `manifest.json` already exists and has a timestamp — no new files needed
- One small API call every 5 minutes is negligible overhead
- Works identically for Docker-based and local MCP server deployments
- When nothing changed (the common case), the check is a single API call that returns the same timestamp — no cache flush, no reloads

---

## Future: Community Detection (Phase 2)

Community detection groups tightly-connected objects into named functional clusters. This is a lower-priority enhancement that builds on the graph.

### Concept

A community is a group of objects that are more connected to each other than to the rest of the application. Communities correspond to functional areas — "LPTA Evaluation," "Vendor Management," "Document Generation."

### Algorithm (No External Dependencies)

Since the project has a zero-runtime-dependencies constraint, community detection uses a BFS-based approach:

1. Start from each entry point (action, process, site, web API, dashboard)
2. BFS to collect all reachable objects (same as bundle generation)
3. Group objects by which entry points they belong to
4. Objects belonging to multiple entry points are assigned to the entry point with the most members in common
5. Compute cohesion score: `internal_edges / (internal_edges + external_edges)`

### Output

`current/communities.json`:
```json
{
  "_metadata": {
    "total_communities": 24,
    "detection_method": "entry_point_bfs"
  },
  "communities": [
    {
      "id": "community_001",
      "name": "LPTA Evaluation Flow",
      "entry_point_name": "AS GSS Complete LPTA Evaluation",
      "entry_point_type": "action",
      "member_count": 47,
      "members": [
        {"uuid": "_a-...", "name": "LPTA_Evaluation_Flow_Rule1", "type": "Expression Rule"},
        {"uuid": "_b-...", "name": "LPTA_Evaluation_Flow_IF1", "type": "Interface"}
      ],
      "dominant_type": "Expression Rule",
      "cohesion_score": 0.85
    }
  ]
}
```

### MCP Tools

```
get_communities(app_name) → list of all communities
get_community(app_name, community_id_or_name) → single community with members
```

### Priority

Phase 2. Depends on `graph.json` being available. Should not block the core implementation.

---

## Resolved Questions

1. **Object code as a separate tool**: **Dedicated `get_object_code` tool.** A separate tool keeps `get_object_detail` lightweight (metadata only, ~2KB) and lets the agent explicitly decide when to load code (2-50KB). This prevents accidental context bloat and matches the file separation (`objects/` vs `code/`). See the tool definition above.

2. **Bundle loading performance**: **Solved by `members` array in bundle files.** Bundle summary queries require 1 file read (same as today). Drill-down into specific objects requires 1 additional read per object. No pre-loading needed. See Spec 02 bundle schema and the loading strategy section above.

3. **Graph tool — reverse path**: **Yes, via `direction` parameter.** Both `get_dependency_path` and `get_transitive_dependencies` accept `direction: outbound|inbound`. Outbound follows calls (A→B→C), inbound follows callers (A←B←C). This enables "what entry points reach this rule?" and "what would break if I changed this?" queries. The graph already stores both `adj_out` and `adj_in` adjacency structures.

4. **Graph caching in MCP server**: **Cache per `app_name`.** ~3MB per app × 3 apps = ~9MB, trivial memory cost. Graph queries go from ~100ms (file read + parse) to <1ms (in-memory traversal). The graph only changes when a new parse runs; the MCP server is typically restarted after a parse.

---

## Open Questions

All questions resolved.
