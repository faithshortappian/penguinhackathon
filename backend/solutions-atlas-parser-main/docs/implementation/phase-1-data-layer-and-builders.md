# Phase 1 — Data Layer & Builders

**Goal**: Create all new pure builder classes that produce the v3 data structures in memory. No file I/O in this phase — builders return dicts. The existing `dump_package` pipeline continues to work unchanged.

**Why first**: Every subsequent phase depends on these builders. Getting the data shapes right and tested in isolation is the foundation.

---

## 1.1 New Domain Models

**File**: `appian_parser/domain/models.py`

**Changes**: Add new dataclasses alongside existing ones (don't modify existing).

```python
@dataclass
class VersionHistoryEntry:
    version: str
    status: str          # "added", "modified", "current"
    diff_hash: str

@dataclass
class MemberEntry:
    uuid: str
    name: str
    type: str

@dataclass
class DependencyEntry:
    uuid: str
    name: str
    type: str
    dep_type: str        # "CALLS", "USES_CONSTANT", etc.

@dataclass
class GraphNode:
    id: str
    name: str
    type: str
    bundles: list[str]
    inbound_count: int
    outbound_count: int
    is_hub: bool
    is_orphan: bool

@dataclass
class GraphEdge:
    from_uuid: str
    to_uuid: str
    type: str            # edge type from DependencyTypeEnum
```

**Tests**: `tests/test_models.py` — verify dataclass creation, frozen where needed.

---

## 1.2 Object File Builder

**New file**: `appian_parser/output/object_file_builder.py`

**Purpose**: Builds the enriched `objects/<uuid>.json` dict for each object. This replaces the current `ObjectDependencyWriter` which only writes `{uuid, name, type, calls, called_by, bundles}`.

**Class**: `ObjectFileBuilder`

**Method**:
```python
def build_all(
    self,
    parsed_objects: list[ParsedObject],
    dependencies: list[Dependency],
    bundle_assignments: dict[str, list[str]],
    hub_uuids: set[str],
    orphan_uuids: set[str],
) -> dict[str, dict]:
    """Returns {uuid: object_dict} for all objects."""
```

**Per-object dict structure** (matches Spec 02 `objects/<uuid>.json`):
```python
{
    "uuid": obj.uuid,
    "name": obj.name,
    "type": obj.object_type,
    "description": obj.data.get("description", ""),
    "diff_hash": obj.diff_hash,
    "bundles": bundle_assignments.get(obj.uuid, []),
    "is_hub": obj.uuid in hub_uuids,
    "is_orphan": obj.uuid in orphan_uuids,
    "inbound_count": len(called_by_map.get(obj.uuid, [])),
    "outbound_count": len(calls_map.get(obj.uuid, [])),
    "calls": [{"uuid": d.target_uuid, "name": d.target_name, "type": d.target_type, "dep_type": d.dependency_type} for d in calls],
    "called_by": [{"uuid": d.source_uuid, "name": d.source_name, "type": d.source_type, "dep_type": d.dependency_type} for d in called_by],
    "type_specific": self._extract_type_specific(obj),
}
```

**`_extract_type_specific(obj)` method**: Extracts type-dependent fields from `obj.data` based on `obj.object_type`. This is a mapping:

| `object_type` | Fields extracted from `obj.data` |
|---------------|----------------------------------|
| `Expression Rule` | `inputs`, `output_type`, `test_cases` |
| `Interface` | `parameters` |
| `Process Model` | `variables`, `total_nodes` (len of nodes), `complexity_score`, `start_form_interface` |
| `Record Type` | `fields`, `relationships`, `views`, `actions`, `data_source` |
| `CDT` | `namespace`, `fields` |
| `Integration` | `connected_system`, `http_method`, `url` |
| `Web API` | `http_method`, `url_alias`, `security` |
| `Site` | `pages` |
| `Constant` | `value`, `value_type`, `scope` |
| `Connected System` | `base_url`, `auth_type` |
| `Control Panel` | `interfaces`, `primary_record_type` |
| `Group` | `group_type`, `parent_group` |
| `Translation Set` | `default_locale`, `enabled_locales` |
| `Translation String` | `translations` |

Implementation: a dict mapping `object_type` → list of field names to extract from `obj.data`. For each field, copy it if present, skip if absent.

**Tests**: `tests/output/test_object_file_builder.py`
- Test with sample ParsedObject for each type → verify `type_specific` fields
- Test hub/orphan flags
- Test calls/called_by population
- Test missing description defaults to ""

---

## 1.3 Code File Builder

**New file**: `appian_parser/output/code_file_builder.py`

**Purpose**: Builds the `code/<uuid>.json` dict for each object that has SAIL code.

**Class**: `CodeFileBuilder`

**Method**:
```python
def build_all(self, parsed_objects: list[ParsedObject]) -> dict[str, dict]:
    """Returns {uuid: code_dict} for objects that have code."""
```

**Logic**:
```python
for obj in parsed_objects:
    code = self._extract_code(obj)
    if code:
        result[obj.uuid] = {
            "uuid": obj.uuid,
            "name": obj.name,
            "type": obj.object_type,
            "sail_code": code,
        }
```

**`_extract_code(obj)` method**: Extracts SAIL code from `obj.data` based on type:

| `object_type` | Code source in `obj.data` |
|---------------|---------------------------|
| `Expression Rule` | `data["sail_code"]` |
| `Interface` | `data["sail_code"]` |
| `Web API` | `data["sail_code"]` |
| `Process Model` | Concatenated node expressions (reuse logic from current `BundleCodeBuilder._extract_code()`) |
| `Integration` | `data.get("sail_code")` or `data.get("request_body")` |
| All others | `None` (no code file) |

**Tests**: `tests/output/test_code_file_builder.py`
- Test Expression Rule → has code
- Test Constant → no code (returns None)
- Test Process Model → concatenated node expressions

---

## 1.4 Graph Builder

**New file**: `appian_parser/output/graph_builder.py`

**Purpose**: Builds the `graph.json` dict from parsed objects and dependencies.

**Class**: `GraphBuilder`

**Method**:
```python
def build(
    self,
    parsed_objects: list[ParsedObject],
    dependencies: list[Dependency],
    bundle_assignments: dict[str, list[str]],
    hub_uuids: set[str],
) -> dict:
    """Returns the complete graph dict."""
```

**Output structure**:
```python
{
    "_metadata": {
        "schema_version": "1.0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "hub_threshold": HUB_CALLER_THRESHOLD,
    },
    "nodes": [node.to_dict() for node in nodes],
    "edges": [edge.to_dict() for edge in edges],
}
```

**Node construction**: For each `ParsedObject`, create a `GraphNode` with:
- `id` = uuid
- `name`, `type` from object
- `bundles` from `bundle_assignments`
- `inbound_count` / `outbound_count` computed from dependency edges
- `is_hub` = `uuid in hub_uuids`
- `is_orphan` = `uuid not in bundle_assignments or bundle_assignments[uuid] == []`

**Edge construction**: For each `Dependency`, create a `GraphEdge` with:
- `from_uuid` = `source_uuid`
- `to_uuid` = `target_uuid`
- `type` = `dependency_type`

Deduplicate edges (same from/to/type should appear only once).

**Tests**: `tests/output/test_graph_builder.py`
- Test node count matches object count
- Test edge deduplication
- Test hub flag propagation
- Test orphan detection

---

## 1.5 Bundle File Builder (Refactored)

**New file**: `appian_parser/output/bundle_file_builder.py`

**Purpose**: Builds the new single-file bundle dict with `members` array. This replaces the current `BundleStructureBuilder` + `BundleCodeBuilder` pair.

**Class**: `BundleFileBuilder`

**Method**:
```python
def build(
    self,
    entry_point: EntryPoint,
    member_objects: list[ParsedObject],
    dep_lookup: dict,
    parsed_objects_map: dict[str, ParsedObject],
) -> dict:
    """Returns a single bundle dict."""
```

**Output structure** (matches Spec 02):
```python
{
    "_metadata": {
        "bundle_id": sanitized_name,
        "bundle_type": entry_point.bundle_type,
        "root_name": entry_point.root_name,
        "parent_name": entry_point.parent_name,
        "object_count": len(member_objects),
    },
    "entry_point": self._build_entry_point(entry_point, ...),
    "flow": self._build_flow(entry_point, ...),
    "members": [
        {"uuid": obj.uuid, "name": obj.name, "type": obj.object_type}
        for obj in member_objects
    ],
    "key_objects": self._get_key_objects(member_objects, dep_lookup),
}
```

**Reuse**: `_build_entry_point()` and `_build_flow()` logic is extracted from the existing `BundleStructureBuilder`. The key change is that `members` replaces the full object embedding.

**`_get_key_objects()`**: Sort member objects by `inbound_count + outbound_count` descending, return top 5 names.

**Tests**: `tests/output/test_bundle_file_builder.py`
- Test members array has correct {uuid, name, type}
- Test key_objects returns top 5
- Test entry_point structure for action bundle type
- Test flow structure for process bundle type

---

## 1.6 Orphan Index Builder

**New file**: `appian_parser/output/orphan_index_builder.py`

**Purpose**: Builds the `orphans_index.json` dict. Replaces the current `OrphanWriter` which writes individual orphan files with embedded code.

**Class**: `OrphanIndexBuilder`

**Method**:
```python
def build(
    self,
    parsed_objects: list[ParsedObject],
    bundle_assignments: dict[str, list[str]],
) -> dict:
    """Returns the orphan index dict."""
```

**Output structure**:
```python
{
    "_metadata": {"total_orphans": count},
    "by_type": {"Expression Rule": 342, ...},
    "orphans": [
        {"uuid": obj.uuid, "name": obj.name, "type": obj.object_type}
        for obj in orphans
    ],
}
```

**Tests**: `tests/output/test_orphan_index_builder.py`
- Test orphan detection (objects not in bundle_assignments)
- Test by_type counts
- Test empty case (no orphans)

---

## 1.7 Enhanced Search Index Builder

**Modified file**: `appian_parser/output/search_index_builder.py`

**Changes**: Add `description` field to each entry. The current builder already has `uuid`, `type`, `bundles`, `inbound_count`, `outbound_count`.

**Modified `build()` method**: Add `description` from `ParsedObject.data.get("description", "")`.

```python
# Current:
index[obj.name] = {"uuid": obj.uuid, "type": obj.object_type, ...}

# New:
index[obj.name] = {
    "uuid": obj.uuid,
    "type": obj.object_type,
    "description": obj.data.get("description", ""),
    "bundle_count": len(bundles),
    "bundles": bundles,
    "deps_out": outbound,
    "deps_in": inbound,
}
```

**Tests**: Update existing tests to verify `description` field.

---

## 1.8 Enhanced App Overview Builder

**Modified file**: `appian_parser/output/app_overview_builder.py`

**Changes**: Add `release_version` to `_metadata`. The version is passed in as a parameter (defaults to `None` for legacy mode).

```python
def build(self, package_info, object_counts, bundle_entries, dep_summary, coverage, release_version=None):
    result = { ... }
    if release_version:
        result["_metadata"]["release_version"] = release_version
    return result
```

**Tests**: Update existing tests to verify `release_version` when provided.

---

## 1.9 Refactored BundleCoordinator

**Modified file**: `appian_parser/output/bundle_coordinator.py`

**Changes**: The coordinator currently both builds AND writes bundles. Refactor to separate concerns:

1. **Keep**: Entry point discovery (`_discover_entry_points`), BFS traversal (`_walk_deps`), adjacency building (`_build_adjacency`), hub detection
2. **Change**: `build_all()` returns in-memory data instead of writing files
3. **Extract**: Hub UUIDs as a public property/return value (needed by ObjectFileBuilder and GraphBuilder)

**New signature**:
```python
def build_all(
    self,
    parsed_objects: list[ParsedObject],
    dependencies: list[Dependency],
) -> tuple[dict[str, list[str]], set[str], list[dict], list[dict]]:
    """Returns (bundle_assignments, hub_uuids, bundle_index_entries, bundle_dicts)."""
```

Where:
- `bundle_assignments`: `{uuid: [bundle_id, ...]}` — which bundles each object belongs to
- `hub_uuids`: `set[str]` — UUIDs classified as hubs
- `bundle_index_entries`: `list[dict]` — entries for `app_overview.json`
- `bundle_dicts`: `list[dict]` — complete bundle file dicts (built by `BundleFileBuilder`)

**Key change**: Instead of calling `BundleStructureBuilder` + `BundleCodeBuilder` + writing files, the coordinator calls `BundleFileBuilder.build()` for each entry point and collects the results.

**Tests**: Update `tests/test_cli.py` to verify the new return signature. Existing bundle logic tests should still pass since the discovery and traversal logic is unchanged.

---

## Phase 1 Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `ObjectFileBuilder` | New class | Builds enriched object dicts with type_specific |
| `CodeFileBuilder` | New class | Builds code dicts for objects with SAIL code |
| `GraphBuilder` | New class | Builds graph dict (nodes + edges) |
| `BundleFileBuilder` | New class | Builds single-file bundle dicts with members |
| `OrphanIndexBuilder` | New class | Builds orphan index dict |
| `SearchIndexBuilder` | Modified | Adds description field |
| `AppOverviewBuilder` | Modified | Adds release_version |
| `BundleCoordinator` | Modified | Returns in-memory data, no file I/O |
| Domain models | Modified | New dataclasses for graph, members, version history |

## Phase 1 Verification

After Phase 1:
- All new builders have unit tests with >90% coverage
- Existing tests still pass (no behavioral changes to the pipeline yet)
- `dump_package()` still works exactly as before (builders exist but aren't wired in yet)
- Each builder can be tested in isolation with sample `ParsedObject` data from `conftest.py`
