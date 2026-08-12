"""Context query routes for the browser extension.

Serves the parsed application context to the extension for:
- Validating rule!/const!/recordType! references
- Autocomplete suggestions
- Dependency lookups ("who calls this?")
- Enriching AI prompts with app-specific knowledge

All reads hit the in-memory store (no file I/O).
"""

from fastapi import APIRouter, HTTPException, Query

from app.context_store import (
    get_meta,
    get_search_index,
    get_by_type,
    get_object,
    search_objects,
    get_dependencies_for,
    is_loaded,
)

router = APIRouter(prefix="/api/v1/context")


@router.get("/status")
async def context_status():
    """Check if parsed context is loaded. Extension calls this on startup."""
    meta = get_meta()
    if not meta:
        return {"loaded": False}
    return {
        "loaded": True,
        "source_filename": meta.get("source_filename"),
        "parsed_at": meta.get("parsed_at"),
        "total_objects": meta.get("total_objects"),
        "total_dependencies": meta.get("total_dependencies"),
        "object_counts": meta.get("object_counts", {}),
    }


@router.get("/search")
async def search_context(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
):
    """Fuzzy search across all object names. Used for autocomplete + validation."""
    if not is_loaded():
        return {"query": q, "count": 0, "results": []}
    results = search_objects(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@router.get("/validate-name/{name}")
async def validate_name(name: str):
    """Check if an object name exists. Fast single-name validation.

    Extension uses this when it sees rule!X or const!X in the editor.
    Returns found=true with type info, or found=false.
    """
    index = get_search_index()
    if name in index:
        return {"found": True, "name": name, **index[name]}
    return {"found": False, "name": name}


@router.get("/object/{uuid}")
async def get_object_detail(uuid: str):
    """Full object detail + dependencies by UUID."""
    obj = get_object(uuid)
    if not obj:
        raise HTTPException(status_code=404, detail=f"Object {uuid} not found")
    deps = get_dependencies_for(uuid)
    return {**obj, "calls": deps["calls"], "called_by": deps["called_by"]}


@router.get("/object-by-name/{name}")
async def get_object_by_name(name: str):
    """Full object detail by name (exact match)."""
    index = get_search_index()
    if name not in index:
        raise HTTPException(status_code=404, detail=f"'{name}' not found")
    uuid = index[name]["uuid"]
    obj = get_object(uuid)
    if not obj:
        raise HTTPException(status_code=404, detail=f"'{name}' in index but data missing")
    deps = get_dependencies_for(uuid)
    return {**obj, "calls": deps["calls"], "called_by": deps["called_by"]}


@router.get("/rules")
async def get_all_rules():
    """All expression rules with signatures. For rule! validation."""
    rules = get_by_type("Expression Rule")
    return {"count": len(rules), "rules": rules}


@router.get("/constants")
async def get_all_constants():
    """All constants with types/values. For const! validation."""
    constants = get_by_type("Constant")
    return {"count": len(constants), "constants": constants}


@router.get("/record-types")
async def get_all_record_types():
    """All record types + fields. For recordType! validation."""
    record_types = get_by_type("Record Type")
    return {"count": len(record_types), "record_types": record_types}


@router.get("/interfaces")
async def get_all_interfaces():
    """All interfaces with inputs."""
    interfaces = get_by_type("Interface")
    return {"count": len(interfaces), "interfaces": interfaces}


@router.get("/dependencies/{uuid}")
async def get_object_dependencies(uuid: str):
    """Calls and called_by for a specific object."""
    return get_dependencies_for(uuid)
