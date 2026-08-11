# Phase 5 — MCP Server

**Goal**: Build the new MCP server (`solutions-atlas-mcp-server`) with all 19 tools, graph queries, version queries, enhanced existing tools, and cache invalidation. This phase can start in parallel with Phase 4 — graph tools and enhanced existing tools only need Phase 3 output.

**Prerequisite**: Phase 3 complete (versioned output with graph.json). Phase 4 needed for version tools.

---

## 5.1 Architecture Overview

The new MCP server replaces the current `solutions-atlas-mcp-server`. Key changes:

| Component | Current | New |
|-----------|---------|-----|
| Data source | GitLab API (unchanged) | GitLab API (unchanged) |
| Tool count | 9 | 19 |
| Graph support | None | In-memory graph with adjacency lists |
| Version support | None | Release index, changelogs, history |
| Caching | Pinned files + LRU(500) | Pinned + LRU + per-app graph cache + staleness check |
| Bundle loading | 2 files (structure + code) | 1 file (bundle.json) + selective object reads |

---

## 5.2 Graph Engine

**New file**: `atlas_mcp/graph_engine.py`

**Purpose**: Load `graph.json`, build adjacency structures, answer graph queries.

**Class**: `GraphEngine`

```python
class GraphEngine:
    def __init__(self, graph_data: dict):
        self._metadata = graph_data["_metadata"]
        self._nodes = {n["id"]: n for n in graph_data["nodes"]}
        self._name_index = {n["name"].lower(): n["id"] for n in graph_data["nodes"]}
        self._adj_out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._adj_in: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for edge in graph_data["edges"]:
            self._adj_out[edge["from"]].append((edge["to"], edge["type"]))
            self._adj_in[edge["to"]].append((edge["from"], edge["type"]))

    def resolve_name(self, name: str) -> str | None:
        """Case-insensitive name → UUID."""
        return self._name_index.get(name.lower())

    def get_node(self, uuid: str) -> dict | None:
        return self._nodes.get(uuid)

    def shortest_path(self, from_uuid: str, to_uuid: str,
                      max_hops: int = 6, direction: str = "outbound") -> dict:
        """BFS shortest path. Returns {found, hops, path, edge_types}."""
        adj = self._adj_out if direction == "outbound" else self._adj_in
        # Standard BFS with parent tracking
        queue = deque([(from_uuid, 0)])
        visited = {from_uuid}
        parent = {}  # uuid → (prev_uuid, edge_type)

        while queue:
            current, depth = queue.popleft()
            if current == to_uuid:
                return self._reconstruct_path(from_uuid, to_uuid, parent)
            if depth >= max_hops:
                continue
            for neighbor, edge_type in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = (current, edge_type)
                    queue.append((neighbor, depth + 1))

        return {"found": False, "hops": None, "path": [], "message": f"No path within {max_hops} hops"}

    def transitive_deps(self, start_uuid: str, max_hops: int = 3,
                        edge_types: list[str] | None = None,
                        direction: str = "outbound") -> dict:
        """BFS transitive dependencies with hub pruning."""
        adj = self._adj_out if direction == "outbound" else self._adj_in
        queue = deque([(start_uuid, 0)])
        visited = {start_uuid}
        results = []

        while queue:
            current, depth = queue.popleft()
            if current != start_uuid:
                node = self._nodes.get(current, {})
                results.append({**node, "depth": depth})

            if depth >= max_hops:
                continue
            # Hub pruning: don't follow hub edges
            if current != start_uuid and self._nodes.get(current, {}).get("is_hub", False):
                continue

            for neighbor, etype in adj.get(current, []):
                if neighbor not in visited:
                    if edge_types and etype not in edge_types:
                        continue
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        # Build by_type summary
        by_type = {}
        for r in results:
            t = r.get("type", "Unknown")
            by_type[t] = by_type.get(t, 0) + 1

        truncated = len(results) > 200
        return {
            "root": self._nodes.get(start_uuid),
            "max_hops": max_hops,
            "total_reachable": len(results),
            "by_type": by_type,
            "objects": results[:200],
            **({"truncated": True} if truncated else {}),
        }

    def hub_objects(self, top_n: int = 20, object_type: str | None = None) -> list[dict]:
        """Top N nodes by inbound_count."""
        nodes = list(self._nodes.values())
        if object_type:
            nodes = [n for n in nodes if n["type"] == object_type]
        nodes.sort(key=lambda n: n.get("inbound_count", 0), reverse=True)
        return nodes[:top_n]
```

**Tests**: `tests/test_graph_engine.py`
- Test shortest_path finds correct path
- Test shortest_path returns not found when no path
- Test transitive_deps with hub pruning
- Test transitive_deps with edge_type filter
- Test transitive_deps inbound direction
- Test hub_objects sorting
- Test name resolution case-insensitive

---

## 5.3 Cache Manager

**New file**: `atlas_mcp/cache_manager.py`

**Purpose**: Manages all caching with manifest-based staleness detection.

**Class**: `CacheManager`

```python
class CacheManager:
    STALENESS_CHECK_INTERVAL = 300  # 5 minutes
    STALENESS_CHECK_CALL_COUNT = 10

    def __init__(self, datasource: GitLabDataSource):
        self._ds = datasource
        self._graphs: dict[str, GraphEngine] = {}           # per-app graph cache
        self._last_generated_at: dict[str, str] = {}        # per-app timestamp
        self._last_check_time: dict[str, float] = {}        # per-app last check
        self._call_count: dict[str, int] = defaultdict(int) # per-app call counter

    def get_graph(self, app_name: str) -> GraphEngine:
        """Get or load graph for app. Checks staleness."""
        self._maybe_check_staleness(app_name)
        if app_name not in self._graphs:
            data = self._ds.read_json(app_name, "current/graph.json")
            self._graphs[app_name] = GraphEngine(data)
        return self._graphs[app_name]

    def record_tool_call(self, app_name: str) -> None:
        """Track tool calls for staleness check trigger."""
        self._call_count[app_name] += 1

    def _maybe_check_staleness(self, app_name: str) -> None:
        """Check if data has been refreshed. Flush caches if so."""
        now = time.monotonic()
        last = self._last_check_time.get(app_name, 0)
        calls = self._call_count.get(app_name, 0)

        if (now - last) < self.STALENESS_CHECK_INTERVAL and calls < self.STALENESS_CHECK_CALL_COUNT:
            return

        self._call_count[app_name] = 0
        self._last_check_time[app_name] = now

        try:
            manifest = self._ds.read_json(app_name, "current/manifest.json")
            generated_at = manifest.get("_metadata", {}).get("generated_at", "")
        except FileNotFoundError:
            return

        if generated_at != self._last_generated_at.get(app_name):
            self._flush_app(app_name)
            self._last_generated_at[app_name] = generated_at

    def _flush_app(self, app_name: str) -> None:
        """Flush all caches for an app."""
        self._graphs.pop(app_name, None)
        self._ds._pinned.clear()
        # Clear LRU entries for this app
        keys_to_remove = [k for k in self._ds._cache if app_name in k]
        for k in keys_to_remove:
            del self._ds._cache[k]
```

**Tests**: `tests/test_cache_manager.py`
- Test graph loaded on first access
- Test graph cached on second access (no reload)
- Test staleness check triggers flush when timestamp changes
- Test staleness check skipped when within interval
- Test call count trigger

---

## 5.4 Tool Implementations — Graph Tools

**New file**: `atlas_mcp/tools/graph.py`

**Class**: `GraphTools`

```python
class GraphTools:
    @staticmethod
    async def get_dependency_path(arguments: dict) -> list[types.TextContent]:
        app_name = arguments["app_name"]
        graph = _cache_manager().get_graph(app_name)
        from_uuid = graph.resolve_name(arguments["from_name"])
        to_uuid = graph.resolve_name(arguments["to_name"])
        if not from_uuid or not to_uuid:
            return format_json_response({"error": "Object not found"})
        result = graph.shortest_path(
            from_uuid, to_uuid,
            max_hops=min(arguments.get("max_hops", 6), 10),
            direction=arguments.get("direction", "outbound"),
        )
        return format_json_response(result)

    @staticmethod
    async def get_transitive_dependencies(arguments: dict) -> list[types.TextContent]:
        # Similar pattern — resolve name, call graph.transitive_deps()

    @staticmethod
    async def get_hub_objects(arguments: dict) -> list[types.TextContent]:
        # Call graph.hub_objects()
```

**Tests**: `tests/test_graph_tools.py` — integration tests with mock datasource

---

## 5.5 Tool Implementations — Code Tool

**New file**: `atlas_mcp/tools/code.py`

**Class**: `CodeTools`

```python
class CodeTools:
    @staticmethod
    async def get_object_code(arguments: dict) -> list[types.TextContent]:
        app_name = arguments["app_name"]
        object_name = arguments["object_name"]
        release = arguments.get("release")

        ds = _datasource()
        # Resolve name to UUID
        index = ds.read_json(app_name, "current/search_index.json")
        uuid = None
        for name, info in index.items():
            if name.lower() == object_name.lower():
                uuid = info["uuid"]
                break
        if not uuid:
            return format_json_response({"error": f"Object '{object_name}' not found"})

        if not release or release == "latest":
            try:
                data = ds.read_json(app_name, f"current/code/{uuid}.json")
                return format_json_response(data)
            except FileNotFoundError:
                return format_json_response({"message": "No code available for this object type"})
        else:
            # Historical — read from history file
            obj = ds.read_json(app_name, f"current/objects/{uuid}.json")
            # Find version in version_history, route to history file
            ...
```

---

## 5.6 Tool Implementations — Version Tools

**New file**: `atlas_mcp/tools/version.py`

**Class**: `VersionTools`

Implements 6 tools:

| Tool | Data Source | Complexity |
|------|-----------|------------|
| `list_releases` | `release_index.json` | Simple file read |
| `get_changelog` | `changelogs/<version>.json` | File read + optional filtering |
| `compare_releases` | Two manifests from `release_snapshots/` | Manifest diff |
| `get_object_history` | `objects/<uuid>.json` → `version_history` | 1 file read |
| `get_object_at_release` | `objects/<uuid>.json` → route to history | 1-2 file reads |
| `get_release_impact` | `changelogs/<version>.json` | File read, extract bundle_changes |

Each tool follows the same pattern: validate params → read file(s) → transform → return JSON.

---

## 5.7 Enhanced Existing Tools

**Modified files**: `atlas_mcp/tools/bundle.py`, `atlas_mcp/tools/object.py`, `atlas_mcp/tools/application.py`, `atlas_mcp/tools/orphan.py`

### `get_bundle` (enhanced)

```python
@staticmethod
async def get_bundle(arguments: dict) -> list[types.TextContent]:
    app_name = arguments["app_name"]
    bundle_id = arguments["bundle_id"]
    object_type = arguments.get("object_type")
    limit = min(arguments.get("limit", 50), 200)

    ds = _datasource()
    resolved_id = _resolve_bundle_id(ds, app_name, bundle_id)
    bundle = ds.read_json(app_name, f"current/bundles/{resolved_id}.json")

    # Filter members
    members = bundle.get("members", [])
    if object_type:
        members = [m for m in members if m["type"] == object_type]

    # Build by_type summary (always from full members, before filtering)
    all_members = bundle.get("members", [])
    by_type = {}
    for m in all_members:
        by_type[m["type"]] = by_type.get(m["type"], 0) + 1

    total = len(members)
    members = members[:limit]

    result = {
        "_metadata": bundle.get("_metadata"),
        "entry_point": bundle.get("entry_point"),
        "flow": bundle.get("flow"),
        "members": members,
        "key_objects": bundle.get("key_objects"),
        "member_summary": {
            "total": total,
            "returned": len(members),
            "by_type": by_type,
        },
    }
    return format_json_response(result)
```

### `search_objects` (enhanced)

Add `description` to results, `limit` parameter, `total_matches` in response.

### `list_orphans` (enhanced)

Add `object_type` filter, `limit` parameter, `by_type` summary always included.

### All tools

Add `release` parameter handling where specified in Spec 05.

---

## 5.8 Tool Registration

**Modified file**: `atlas_mcp/server.py`

Update `tool_handlers` dict to include all 19 tools:

```python
self.tool_handlers = {
    # Existing (enhanced)
    "list_applications": ApplicationTools.list_applications,
    "get_app_overview": ApplicationTools.get_app_overview,
    "search_bundles": BundleTools.search_bundles,
    "get_bundle": BundleTools.get_bundle,
    "search_objects": ObjectTools.search_objects,
    "get_dependencies": ObjectTools.get_dependencies,
    "get_object_detail": ObjectTools.get_object_detail,
    "list_orphans": OrphanTools.list_orphans,
    "get_orphan": OrphanTools.get_orphan,
    # New — Graph
    "get_dependency_path": GraphTools.get_dependency_path,
    "get_transitive_dependencies": GraphTools.get_transitive_dependencies,
    "get_hub_objects": GraphTools.get_hub_objects,
    # New — Code
    "get_object_code": CodeTools.get_object_code,
    # New — Version
    "list_releases": VersionTools.list_releases,
    "get_changelog": VersionTools.get_changelog,
    "compare_releases": VersionTools.compare_releases,
    "get_object_history": VersionTools.get_object_history,
    "get_object_at_release": VersionTools.get_object_at_release,
    "get_release_impact": VersionTools.get_release_impact,
}
```

**Modified file**: `atlas_mcp/models.py`

Add tool schemas for all 10 new tools. Each tool needs a `types.Tool` definition with `name`, `description`, and `inputSchema`.

---

## 5.9 Data Source Path Updates

**Modified file**: `atlas_mcp/datasource.py`

The data source currently reads from `data/<AppName>/` directly. With the versioned structure, most reads go through `data/<AppName>/current/`. Update the path construction:

```python
def read_json(self, app_name: str, rel_path: str) -> dict | list:
    """Read JSON file. rel_path is relative to app root (e.g., 'current/objects/uuid.json')."""
    full_path = f"{self._prefix}/{app_name}/{rel_path}"
    return self._fetch_json(full_path)
```

The tool implementations pass the full relative path including `current/` when needed. This keeps the datasource generic.

**Backward compatibility**: If `current/` doesn't exist (old flat format), tools fall back to reading from the app root directly. Check for `release_index.json` to detect versioned vs flat mode.

---

## 5.10 Integration Testing

**New file**: `tests/test_mcp_integration.py`

End-to-end test using the test packages from `test_files/source_selection_v1/`:

```python
def test_full_pipeline_and_mcp():
    """Parse real packages, then verify MCP tools return correct data."""
    # 1. Parse v2.7.0 as baseline
    dump_package("SourceSelectionv2.7.0 - FULL.zip", data_dir="./test_data/GSS")

    # 2. Parse v2.8.0 as new release
    dump_package("SourceSelectionv2.8.0 - FULL.zip", data_dir="./test_data/GSS")

    # 3. Delta parse v2.9.0
    delta_package("SourceSelection-2.9.0-21 - Delta.zip", data_dir="./test_data/GSS")

    # 4. Verify MCP tools
    ds = LocalDataSource("./test_data")

    # list_releases → 3 releases
    # get_changelog("25.04.02.09.00") → has object_changes
    # get_dependency_path("AS_GSS_PM_...", "AS_GSS_BL_...") → found
    # get_object_code("AS_GSS_BL_validateLPTAScores") → has sail_code
    # get_bundle("AS_GSS_Complete_LPTA_Evaluation", object_type="Interface") → filtered
    # search_objects("validate", limit=5) → has description
```

---

## Phase 5 Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `GraphEngine` | New class | In-memory graph with BFS queries |
| `CacheManager` | New class | Staleness detection + cache flush |
| `GraphTools` | New class | 3 graph query tools |
| `CodeTools` | New class | get_object_code tool |
| `VersionTools` | New class | 6 version query tools |
| `BundleTools` | Enhanced | Filtering, pagination, member_summary |
| `ObjectTools` | Enhanced | Description in search, release param |
| `OrphanTools` | Enhanced | Type filter, pagination |
| Tool schemas | Enhanced | 10 new tool definitions in models.py |
| `datasource.py` | Enhanced | Versioned path support, backward compat |

## Phase 5 Verification

After Phase 5:
- All 19 tools registered and callable
- Graph tools: path finding, transitive deps (both directions), hub detection
- Version tools: release list, changelogs, object history, cross-release comparison
- Enhanced tools: bundle filtering, search with description, orphan filtering
- Cache invalidation: manifest staleness check flushes caches on data refresh
- Backward compatible: works with both flat (legacy) and versioned output
- Integration test passes with real package data
