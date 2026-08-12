"""
Appian Atlas — MCP Server.

Exposes parsed Appian application data (bundles, manifests, dependencies)
to LLM clients via the Model Context Protocol. Designed as a universal
knowledge base for Appian applications across all solutions.

Usage:
    # Local mode (reads from filesystem)
    python -m mcp_server --data-dir /path/to/data

    # GitHub mode (reads from a GitHub repo)
    python -m mcp_server --github owner/repo [--branch main] [--data-prefix data]

    Requires GITHUB_TOKEN env var for private repos (or to avoid rate limits).
"""

from __future__ import annotations

import json
import sys

from mcp.server.fastmcp import FastMCP

from mcp_server.datasource import DataSource, GitHubDataSource, LocalDataSource

# ── Globals ─────────────────────────────────────────────────────────────

_ds: DataSource | None = None
mcp = FastMCP("appian-atlas")


def _datasource() -> DataSource:
    if _ds is None:
        raise RuntimeError("Data source not initialized")
    return _ds


def _truncate(data: dict | list, max_chars: int = 80_000) -> dict | list | str:
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= max_chars:
        return data
    return {
        "_truncated": True,
        "_message": f"Response too large ({len(text):,} chars). Use get_bundle with detail_level='summary'.",
    }


# ── Tools ───────────────────────────────────────────────────────────────


@mcp.tool()
def list_applications() -> list[dict]:
    """List all GAM Appian applications available in the knowledge base.

    Returns application names, object counts, and bundle coverage stats.
    Call this first to discover what's available.
    """
    ds = _datasource()
    apps = []
    for name in ds.list_apps():
        overview = ds.read_json(name, "app_overview.json")
        info = overview.get("package_info", {})
        coverage = overview.get("coverage", {})
        bundles = overview.get("bundles", [])
        bundle_types: dict[str, int] = {}
        for b in bundles:
            bt = b.get("bundle_type", "unknown")
            bundle_types[bt] = bundle_types.get(bt, 0) + 1
        apps.append({
            "name": name,
            "total_objects": info.get("total_parsed_objects"),
            "total_errors": info.get("total_errors"),
            "bundle_coverage": coverage,
            "bundles_by_type": bundle_types,
        })
    return apps


@mcp.tool()
def get_app_overview(app_name: str) -> dict:
    """Get a comprehensive overview of a GAM application in a single call.

    Returns package metadata, object counts by type, bundle index with key objects,
    dependency summary (top shared utilities, dependency type breakdown), coverage,
    and enrichment metadata if available.
    Use this as the starting point before drilling into specific bundles or objects.

    Args:
        app_name: Application folder name (from list_applications).
    """
    ds = _datasource()
    overview = ds.read_json(app_name, "app_overview.json")
    
    # Add enrichment metadata if available
    if ds.file_exists(app_name, "enrichment/metadata.json"):
        try:
            enrichment_meta = ds.read_json(app_name, "enrichment/metadata.json")
            overview["enrichment"] = enrichment_meta
        except:
            pass
    
    return overview


@mcp.tool()
def search_bundles(app_name: str, query: str, bundle_type: str | None = None) -> list[dict]:
    """Search bundles by name within a GAM application.

    Use this to quickly find relevant bundles instead of browsing the full list.

    Args:
        app_name: Application folder name.
        query: Case-insensitive substring to match against bundle root names.
        bundle_type: Optional filter — one of: action, process, page, site, dashboard, web_api.
    """
    overview = _datasource().read_json(app_name, "app_overview.json")
    query_lower = query.lower()
    results = []
    for b in overview.get("bundles", []):
        if bundle_type and b.get("bundle_type") != bundle_type:
            continue
        name = b.get("root_name", "")
        parent = b.get("parent_name", "") or ""
        if query_lower in name.lower() or query_lower in parent.lower():
            results.append(b)
    return results


@mcp.tool()
def search_objects(app_name: str, query: str, object_type: str | None = None) -> list[dict]:
    """Search parsed objects by name within a GAM application.

    Args:
        app_name: Application folder name.
        query: Case-insensitive substring to match against object names.
        object_type: Optional filter (e.g. "Interface", "Expression Rule", "Process Model",
                     "Record Type", "CDT", "Integration", "Web API", "Constant").
    """
    ds = _datasource()
    index = ds.read_json(app_name, "search_index.json")
    query_lower = query.lower()
    results = []
    for name, info in index.items():
        if object_type and info.get("type") != object_type:
            continue
        if query_lower in name.lower():
            results.append({"name": name, **info})
    return results[:50]


@mcp.tool()
def get_bundle(app_name: str, bundle_id: str, detail_level: str = "summary") -> dict | str:
    """Get a bundle's content at the requested detail level.

    Args:
        app_name: Application folder name.
        bundle_id: Bundle ID from search_bundles/get_app_overview (e.g. "AS_GSS_Complete_LPTA_Evaluation").
                   Also accepts root_name with spaces — it will be resolved automatically.
        detail_level: "summary" for metadata + object names + flow (small, fast),
                      "structure" for full structure.json (no code),
                      "full" for structure + SAIL code merged together.
    """
    ds = _datasource()
    resolved_id = _resolve_bundle_id(ds, app_name, bundle_id)

    structure = ds.read_json(app_name, f"bundles/{resolved_id}/structure.json")

    if detail_level == "summary":
        # Lightweight: metadata + entry_point + flow + object names only
        summary: dict = {
            "_metadata": structure.get("_metadata", {}),
            "entry_point": structure.get("entry_point", {}),
            "flow": structure.get("flow"),
            "objects": [
                {"name": o["name"], "type": o["type"], "description": o.get("description")}
                for o in structure.get("objects", [])
            ],
        }
        return summary

    if detail_level == "structure":
        return _truncate(structure)

    # Full: merge code into structure
    code = ds.read_json(app_name, f"bundles/{resolved_id}/code.json")
    code_map = code.get("objects", {})
    for obj in structure.get("objects", []):
        uuid = obj.get("uuid")
        if uuid and uuid in code_map:
            obj["sail_code"] = code_map[uuid].get("sail_code")
    return _truncate(structure)


def _resolve_bundle_id(ds: DataSource, app_name: str, bundle_id: str) -> str:
    """Resolve a bundle_id that might be an id, root_name, or old-style path."""
    # Try as-is first (the happy path)
    if ds.file_exists(app_name, f"bundles/{bundle_id}/structure.json"):
        return bundle_id

    # Try stripping old-style path prefix and .json suffix
    stripped = bundle_id
    for prefix in ("actions/", "processes/", "pages/", "sites/", "web_apis/", "dashboards/"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
    if stripped.endswith(".json"):
        stripped = stripped[:-5]
    if stripped != bundle_id and ds.file_exists(app_name, f"bundles/{stripped}/structure.json"):
        return stripped

    # Try matching by root_name from the overview
    overview = ds.read_json(app_name, "app_overview.json")
    bundle_id_lower = bundle_id.lower()
    for b in overview.get("bundles", []):
        if b.get("root_name", "").lower() == bundle_id_lower:
            return b["id"]

    # Give up — return original, will produce a clear FileNotFoundError
    return bundle_id


@mcp.tool()
def get_dependencies(app_name: str, object_name: str) -> dict:
    """Get the dependency subgraph for a specific object (by name).

    Returns what the object calls (outbound) and what calls it (inbound).

    Args:
        app_name: Application folder name.
        object_name: Case-insensitive object name to look up.
    """
    ds = _datasource()
    # Look up UUID from search index
    index = ds.read_json(app_name, "search_index.json")
    name_lower = object_name.lower()
    uuid = None
    for name, info in index.items():
        if name.lower() == name_lower:
            uuid = info.get("uuid")
            break

    if not uuid:
        return {"error": f"Object '{object_name}' not found", "object_name": object_name}

    obj_data = ds.read_json(app_name, f"objects/{uuid}.json")
    return obj_data


@mcp.tool()
def get_object_detail(app_name: str, object_uuid: str) -> dict:
    """Get full dependency and bundle info for a specific object by UUID.

    Args:
        app_name: Application folder name.
        object_uuid: The object's UUID.
    """
    return _datasource().read_json(app_name, f"objects/{object_uuid}.json")


@mcp.tool()
def list_orphans(app_name: str) -> dict:
    """List all orphaned objects (not reachable from any entry point).

    Args:
        app_name: Application folder name.
    """
    return _datasource().read_json(app_name, "orphans/_index.json")


@mcp.tool()
def get_orphan(app_name: str, object_uuid: str) -> dict:
    """Get full detail (including code) for an orphaned object.

    Args:
        app_name: Application folder name.
        object_uuid: The orphan object's UUID.
    """
    return _datasource().read_json(app_name, f"orphans/{object_uuid}.json")


@mcp.tool()
def get_enrichment_metadata(app_name: str) -> dict:
    """Get enrichment metadata for an application.
    
    Returns summary statistics about the enrichment including total objects enriched,
    objects with calculated dependency depth, and enrichment version.
    
    Args:
        app_name: Application folder name.
    """
    ds = _datasource()
    if not ds.file_exists(app_name, "enrichment/metadata.json"):
        return {"error": "Enrichment data not available for this application"}
    return ds.read_json(app_name, "enrichment/metadata.json")


@mcp.tool()
def get_object_enrichment(app_name: str, object_uuid: str) -> dict:
    """Get enrichment data for a specific object.
    
    Returns dependency depth, classification tags, and statistics for the object.
    
    Args:
        app_name: Application folder name.
        object_uuid: The object's UUID.
    """
    ds = _datasource()
    if not ds.file_exists(app_name, "enrichment/object_enrichments.json"):
        return {"error": "Enrichment data not available for this application"}
    
    enrichments = ds.read_json(app_name, "enrichment/object_enrichments.json")
    if object_uuid not in enrichments:
        return {"error": f"No enrichment data found for object {object_uuid}"}
    
    return enrichments[object_uuid]


@mcp.tool()
def get_dependency_depths(app_name: str, max_depth: int | None = None) -> dict:
    """Get dependency depth information for all objects.
    
    Returns a mapping of object UUIDs to their calculated depth from entry points.
    Optionally filter to only objects at or below a certain depth.
    
    Args:
        app_name: Application folder name.
        max_depth: Optional maximum depth to include (e.g., 2 for entry points and first two levels).
    """
    ds = _datasource()
    if not ds.file_exists(app_name, "enrichment/object_depths.json"):
        return {"error": "Enrichment data not available for this application"}
    
    depths = ds.read_json(app_name, "enrichment/object_depths.json")
    
    if max_depth is not None:
        depths = {uuid: depth for uuid, depth in depths.items() if depth <= max_depth}
    
    return depths


@mcp.tool()
def search_by_depth(app_name: str, depth: int) -> list[dict]:
    """Find all objects at a specific dependency depth.
    
    Useful for finding entry points (depth 0) or exploring architecture layers.
    
    Args:
        app_name: Application folder name.
        depth: The dependency depth to search for (0 = entry points).
    """
    ds = _datasource()
    if not ds.file_exists(app_name, "enrichment/object_depths.json"):
        return [{"error": "Enrichment data not available for this application"}]
    
    depths = ds.read_json(app_name, "enrichment/object_depths.json")
    index = ds.read_json(app_name, "search_index.json")
    
    results = []
    for uuid, obj_depth in depths.items():
        if obj_depth == depth:
            # Find object info from index
            for name, info in index.items():
                if info.get("uuid") == uuid:
                    results.append({
                        "name": name,
                        "uuid": uuid,
                        "type": info.get("type"),
                        "depth": depth
                    })
                    break
    
    return results[:100]  # Limit to 100 results


@mcp.tool()
def search_by_tags(app_name: str, tags: list[str]) -> list[dict]:
    """Find objects with specific classification tags.
    
    Tags include: record_driven, integration_heavy, conditional_workflow, 
    approval_workflow, read_only, dashboard, form_interface, etc.
    
    Args:
        app_name: Application folder name.
        tags: List of tags to search for (objects must have ALL specified tags).
    """
    ds = _datasource()
    if not ds.file_exists(app_name, "enrichment/object_enrichments.json"):
        return [{"error": "Enrichment data not available for this application"}]
    
    enrichments = ds.read_json(app_name, "enrichment/object_enrichments.json")
    index = ds.read_json(app_name, "search_index.json")
    
    results = []
    for uuid, enrich_data in enrichments.items():
        obj_tags = enrich_data.get("tags", [])
        if all(tag in obj_tags for tag in tags):
            # Find object info from index
            for name, info in index.items():
                if info.get("uuid") == uuid:
                    results.append({
                        "name": name,
                        "uuid": uuid,
                        "type": info.get("type"),
                        "tags": obj_tags,
                        "depth": enrich_data.get("dependency_depth")
                    })
                    break
    
    return results[:100]  # Limit to 100 results


# ── Phase 1 Efficiency Tools ────────────────────────────────────────────


@mcp.tool()
def get_statistics(app_name: str, stat_type: str, filters: dict | None = None) -> dict:
    """Get aggregated statistics without loading full data.
    
    Provides instant answers to "how many" questions and distribution analysis.
    
    Args:
        app_name: Application folder name.
        stat_type: Type of statistics to retrieve:
            - "tag_distribution": Count of objects per classification tag
            - "depth_distribution": Count of objects per dependency depth
            - "type_distribution": Count of objects per type
            - "bundle_complexity": Bundles sorted by object count
            - "object_reuse": Objects sorted by dependent_count (most reused first)
            - "orphan_summary": Orphan counts by type
        filters: Optional filters (e.g., {"min_count": 5, "max_depth": 3})
    """
    ds = _datasource()
    filters = filters or {}
    
    if stat_type == "tag_distribution":
        if not ds.file_exists(app_name, "enrichment/object_enrichments.json"):
            return {"error": "Enrichment data not available"}
        enrichments = ds.read_json(app_name, "enrichment/object_enrichments.json")
        tag_counts: dict[str, int] = {}
        for enrich_data in enrichments.values():
            for tag in enrich_data.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return {"tag_distribution": dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True))}
    
    elif stat_type == "depth_distribution":
        if not ds.file_exists(app_name, "enrichment/object_depths.json"):
            return {"error": "Enrichment data not available"}
        depths = ds.read_json(app_name, "enrichment/object_depths.json")
        depth_counts: dict[int, int] = {}
        for depth in depths.values():
            depth_counts[depth] = depth_counts.get(depth, 0) + 1
        return {"depth_distribution": dict(sorted(depth_counts.items()))}
    
    elif stat_type == "type_distribution":
        index = ds.read_json(app_name, "search_index.json")
        type_counts: dict[str, int] = {}
        for info in index.values():
            obj_type = info.get("type", "unknown")
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        return {"type_distribution": dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True))}
    
    elif stat_type == "bundle_complexity":
        overview = ds.read_json(app_name, "app_overview.json")
        bundles = overview.get("bundles", [])
        sorted_bundles = sorted(bundles, key=lambda b: b.get("object_count", 0), reverse=True)
        limit = filters.get("limit", 20)
        return {
            "bundle_complexity": [
                {
                    "id": b["id"],
                    "root_name": b.get("root_name"),
                    "bundle_type": b.get("bundle_type"),
                    "object_count": b.get("object_count", 0)
                }
                for b in sorted_bundles[:limit]
            ]
        }
    
    elif stat_type == "object_reuse":
        index = ds.read_json(app_name, "search_index.json")
        objects_with_deps = [
            {"name": name, "type": info.get("type"), "dependent_count": info.get("dependent_count", 0)}
            for name, info in index.items()
        ]
        sorted_objects = sorted(objects_with_deps, key=lambda o: o["dependent_count"], reverse=True)
        limit = filters.get("limit", 20)
        min_count = filters.get("min_count", 1)
        filtered = [o for o in sorted_objects if o["dependent_count"] >= min_count]
        return {"object_reuse": filtered[:limit]}
    
    elif stat_type == "orphan_summary":
        orphans = ds.read_json(app_name, "orphans/_index.json")
        type_counts: dict[str, int] = {}
        for orphan in orphans.get("orphans", []):
            obj_type = orphan.get("type", "unknown")
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        return {
            "orphan_summary": {
                "total_orphans": len(orphans.get("orphans", [])),
                "by_type": dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True))
            }
        }
    
    else:
        return {"error": f"Unknown stat_type: {stat_type}"}


@mcp.tool()
def batch_get(app_name: str, operation: str, identifiers: list[str], options: dict | None = None) -> list[dict]:
    """Get multiple objects/bundles in one call.
    
    Reduces N individual calls to 1 batch operation.
    
    Args:
        app_name: Application folder name.
        operation: Type of batch operation:
            - "objects": Get multiple object details by UUID
            - "bundles": Get multiple bundles by ID
            - "enrichments": Get enrichment data for multiple objects
            - "dependencies": Get dependencies for multiple objects by name
        identifiers: List of UUIDs, bundle IDs, or object names (depending on operation)
        options: Optional settings (e.g., {"detail_level": "summary"} for bundles)
    """
    ds = _datasource()
    options = options or {}
    results = []
    
    if operation == "objects":
        for uuid in identifiers:
            try:
                obj = ds.read_json(app_name, f"objects/{uuid}.json")
                results.append({"uuid": uuid, "data": obj})
            except Exception as e:
                results.append({"uuid": uuid, "error": str(e)})
    
    elif operation == "bundles":
        detail_level = options.get("detail_level", "summary")
        for bundle_id in identifiers:
            try:
                bundle = get_bundle(app_name, bundle_id, detail_level)
                results.append({"bundle_id": bundle_id, "data": bundle})
            except Exception as e:
                results.append({"bundle_id": bundle_id, "error": str(e)})
    
    elif operation == "enrichments":
        if not ds.file_exists(app_name, "enrichment/object_enrichments.json"):
            return [{"error": "Enrichment data not available"}]
        enrichments = ds.read_json(app_name, "enrichment/object_enrichments.json")
        for uuid in identifiers:
            if uuid in enrichments:
                results.append({"uuid": uuid, "data": enrichments[uuid]})
            else:
                results.append({"uuid": uuid, "error": "Not found"})
    
    elif operation == "dependencies":
        for obj_name in identifiers:
            try:
                deps = get_dependencies(app_name, obj_name)
                results.append({"object_name": obj_name, "data": deps})
            except Exception as e:
                results.append({"object_name": obj_name, "error": str(e)})
    
    else:
        return [{"error": f"Unknown operation: {operation}"}]
    
    return results


@mcp.tool()
def smart_query(app_name: str, query_type: str, **params) -> dict:
    """Intelligent query tool that handles common patterns in one call.
    
    Combines multiple operations to reduce round trips for frequent use cases.
    
    Args:
        app_name: Application folder name.
        query_type: Type of smart query:
            - "find_and_load_bundle": Search for bundle by name and load it
            - "find_and_get_object": Search for object by name and get full details
            - "get_bundle_summary": Get just bundle metadata without loading full data
            - "count_by_tag": Count objects with specific tags
            - "most_reused": Get top N most-reused objects with details
        **params: Query-specific parameters:
            - query: Search query string (for find_* operations)
            - bundle_type: Bundle type filter (optional)
            - object_type: Object type filter (optional)
            - detail_level: Detail level for bundles (default: "summary")
            - tags: List of tags (for count_by_tag)
            - limit: Result limit (for most_reused)
    """
    ds = _datasource()
    
    if query_type == "find_and_load_bundle":
        query = params.get("query", "")
        bundle_type = params.get("bundle_type")
        detail_level = params.get("detail_level", "summary")
        
        # Search for bundle
        bundles = search_bundles(app_name, query, bundle_type)
        if not bundles:
            return {"error": f"No bundles found matching '{query}'"}
        
        # Load first match
        bundle_id = bundles[0]["id"]
        bundle_data = get_bundle(app_name, bundle_id, detail_level)
        
        return {
            "search_results": bundles,
            "loaded_bundle": bundle_data,
            "bundle_id": bundle_id
        }
    
    elif query_type == "find_and_get_object":
        query = params.get("query", "")
        object_type = params.get("object_type")
        
        # Search for object
        objects = search_objects(app_name, query, object_type)
        if not objects:
            return {"error": f"No objects found matching '{query}'"}
        
        # Get details for first match
        uuid = objects[0].get("uuid")
        if not uuid:
            return {"error": "Object UUID not found"}
        
        obj_data = get_object_detail(app_name, uuid)
        
        return {
            "search_results": objects,
            "loaded_object": obj_data,
            "uuid": uuid
        }
    
    elif query_type == "get_bundle_summary":
        bundle_id = params.get("bundle_id", "")
        if not bundle_id:
            return {"error": "bundle_id parameter required"}
        
        # Get just the summary without loading full data
        return get_bundle(app_name, bundle_id, "summary")
    
    elif query_type == "count_by_tag":
        tags = params.get("tags", [])
        if not tags:
            return {"error": "tags parameter required"}
        
        # Search by tags and return count
        objects = search_by_tags(app_name, tags)
        return {
            "tags": tags,
            "count": len(objects),
            "sample_objects": objects[:10]  # First 10 as sample
        }
    
    elif query_type == "most_reused":
        limit = params.get("limit", 10)
        
        # Get most reused objects
        stats = get_statistics(app_name, "object_reuse", {"limit": limit})
        if "error" in stats:
            return stats
        
        # Get enrichment data for each
        top_objects = stats.get("object_reuse", [])
        index = ds.read_json(app_name, "search_index.json")
        
        enriched_results = []
        for obj in top_objects:
            name = obj["name"]
            # Find UUID from index
            for idx_name, info in index.items():
                if idx_name == name:
                    uuid = info.get("uuid")
                    if uuid and ds.file_exists(app_name, "enrichment/object_enrichments.json"):
                        enrichments = ds.read_json(app_name, "enrichment/object_enrichments.json")
                        enrich_data = enrichments.get(uuid, {})
                        obj["depth"] = enrich_data.get("dependency_depth")
                        obj["tags"] = enrich_data.get("tags", [])
                    break
            enriched_results.append(obj)
        
        return {"most_reused": enriched_results}
    
    else:
        return {"error": f"Unknown query_type: {query_type}"}


# ── Entry point ─────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Appian Atlas MCP Server")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--data-dir", help="Local directory containing parsed application folders")
    group.add_argument("--github", metavar="OWNER/REPO", help="GitHub repository (e.g. myorg/appian-atlas)")
    parser.add_argument("--branch", default="main", help="Git branch (default: main)")
    parser.add_argument("--data-prefix", default="data", help="Path prefix in repo for app folders (default: data)")

    args = parser.parse_args()

    global _ds
    if args.data_dir:
        import os
        data_dir = os.path.abspath(args.data_dir)
        if not os.path.isdir(data_dir):
            print(f"Error: {data_dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        _ds = LocalDataSource(data_dir)
    else:
        parts = args.github.split("/", 1)
        if len(parts) != 2:
            print("Error: --github must be OWNER/REPO format", file=sys.stderr)
            sys.exit(1)
        _ds = GitHubDataSource(
            owner=parts[0],
            repo=parts[1],
            branch=args.branch,
            data_prefix=args.data_prefix,
        )

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
