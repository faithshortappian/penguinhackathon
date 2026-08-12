"""Persistent context store for parsed Appian application data.

Strategy: memory-first, disk as persistence.
- On parse: data goes into a module-level dict (instant queries) AND is
  written to disk (survives restarts).
- On server startup: if parsed_context/ exists on disk, it's loaded into
  memory automatically.
- Queries hit the in-memory dict (no file I/O per request).

Storage layout on disk:
  backend/parsed_context/
  ├── meta.json
  ├── search_index.json
  ├── by_type/
  │   ├── expression_rules.json
  │   ├── constants.json
  │   ├── record_types.json
  │   └── ...
  └── dependencies.json
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONTEXT_DIR = Path(__file__).parent.parent / "parsed_context"

# ─── In-memory store ─────────────────────────────────────────────

_store: dict = {
    "meta": None,
    "search_index": {},       # name → {uuid, type}
    "by_type": {},            # type_key → [list of summary dicts]
    "dependencies": [],       # flat list of dep dicts
    "objects": {},            # uuid → full object dict
}


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*{}]', '_', name)


def _type_key(type_name: str) -> str:
    return type_name.lower().replace(" ", "_")


# ─── Save (parse → memory + disk) ────────────────────────────────

def save_parsed_context(
    parsed_objects: list,
    dependencies: list,
    source_filename: str,
    bundle_dicts: list | None = None,
) -> dict:
    """Save parsed objects into memory and persist to disk."""

    # Build object counts
    by_type_counts: dict[str, int] = {}
    for obj in parsed_objects:
        by_type_counts[obj.object_type] = by_type_counts.get(obj.object_type, 0) + 1

    # Meta
    meta = {
        "source_filename": source_filename,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "total_objects": len(parsed_objects),
        "total_dependencies": len(dependencies),
        "total_bundles": len(bundle_dicts) if bundle_dicts else 0,
        "object_counts": dict(sorted(by_type_counts.items())),
    }

    # Search index
    search_index = {}
    for obj in parsed_objects:
        search_index[obj.name] = {"uuid": obj.uuid, "type": obj.object_type}

    # Objects dict (uuid → full data)
    objects_dict = {}
    for obj in parsed_objects:
        objects_dict[obj.uuid] = {
            "uuid": obj.uuid,
            "name": obj.name,
            "type": obj.object_type,
            "data": obj.data,
            "diff_hash": obj.diff_hash,
        }

    # By-type summaries
    type_groups: dict[str, list] = {}
    for obj in parsed_objects:
        key = _type_key(obj.object_type)
        if key not in type_groups:
            type_groups[key] = []

        summary = {"uuid": obj.uuid, "name": obj.name}
        data = obj.data or {}

        if obj.object_type == "Expression Rule":
            summary["inputs"] = data.get("inputs", data.get("parameters", []))
            summary["description"] = data.get("description", "")
            summary["sail_code"] = data.get("sail_code", "")
        elif obj.object_type == "Constant":
            summary["constant_type"] = data.get("type", data.get("data_type", ""))
            summary["value"] = str(data.get("value", ""))[:500]
            summary["description"] = data.get("description", "")
        elif obj.object_type == "Record Type":
            summary["fields"] = data.get("fields", [])
            summary["relationships"] = data.get("relationships", [])
            summary["description"] = data.get("description", "")
        elif obj.object_type == "Interface":
            summary["inputs"] = data.get("inputs", data.get("parameters", []))
            summary["description"] = data.get("description", "")
        elif obj.object_type == "Integration":
            summary["description"] = data.get("description", "")
            summary["connected_system"] = data.get("connected_system_name", "")
        elif obj.object_type == "Process Model":
            summary["description"] = data.get("description", "")
            summary["process_variables"] = data.get("process_variables", [])

        type_groups[key].append(summary)

    # Dependencies as dicts
    dep_list = []
    for dep in dependencies:
        dep_list.append({
            "source_uuid": dep.source_uuid,
            "source_name": dep.source_name,
            "source_type": dep.source_type,
            "target_uuid": dep.target_uuid,
            "target_name": dep.target_name,
            "target_type": dep.target_type,
            "dependency_type": dep.dependency_type,
        })

    # Write to memory
    _store["meta"] = meta
    _store["search_index"] = search_index
    _store["by_type"] = type_groups
    _store["dependencies"] = dep_list
    _store["objects"] = objects_dict

    # Persist to disk (non-blocking for the response — if it fails, memory still has it)
    try:
        _persist_to_disk(meta, search_index, type_groups, dep_list)
    except Exception as e:
        logger.warning(f"Failed to persist context to disk: {e}")

    logger.info(f"Context saved: {len(parsed_objects)} objects, {len(dep_list)} deps from {source_filename}")

    return {
        "path": str(CONTEXT_DIR),
        "total_objects": len(parsed_objects),
        "total_dependencies": len(dep_list),
    }


def _persist_to_disk(meta, search_index, type_groups, dep_list):
    """Write context to disk for persistence across restarts."""
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    by_type_dir = CONTEXT_DIR / "by_type"
    by_type_dir.mkdir(exist_ok=True)

    _write_json(CONTEXT_DIR / "meta.json", meta)
    _write_json(CONTEXT_DIR / "search_index.json", search_index)
    _write_json(CONTEXT_DIR / "dependencies.json", dep_list)

    for type_key, items in type_groups.items():
        _write_json(by_type_dir / f"{type_key}s.json", items)


# ─── Load from disk (on startup) ─────────────────────────────────

def load_from_disk():
    """Load persisted context from disk into memory. Called on startup."""
    meta_path = CONTEXT_DIR / "meta.json"
    if not meta_path.exists():
        logger.info("No parsed context on disk — extension context will be empty until a ZIP is parsed.")
        return

    try:
        _store["meta"] = _read_json(meta_path)
        _store["search_index"] = _read_json(CONTEXT_DIR / "search_index.json") if (CONTEXT_DIR / "search_index.json").exists() else {}
        _store["dependencies"] = _read_json(CONTEXT_DIR / "dependencies.json") if (CONTEXT_DIR / "dependencies.json").exists() else []

        by_type_dir = CONTEXT_DIR / "by_type"
        if by_type_dir.exists():
            for f in by_type_dir.iterdir():
                if f.suffix == ".json":
                    key = f.stem.rstrip("s")  # expression_rules.json → expression_rule
                    _store["by_type"][key] = _read_json(f)

        logger.info(f"Loaded parsed context from disk: {_store['meta']['total_objects']} objects")
    except Exception as e:
        logger.warning(f"Failed to load context from disk: {e}")


# ─── Query API (reads from memory) ───────────────────────────────

def get_meta() -> dict | None:
    return _store["meta"]


def get_search_index() -> dict:
    return _store["search_index"]


def get_by_type(type_name: str) -> list:
    key = _type_key(type_name)
    return _store["by_type"].get(key, [])


def get_object(uuid: str) -> dict | None:
    return _store["objects"].get(uuid)


def get_dependencies() -> list:
    return _store["dependencies"]


def search_objects(query: str, limit: int = 20) -> list:
    """Substring match on object names. Case-insensitive."""
    query_lower = query.lower()
    results = []
    for name, info in _store["search_index"].items():
        if query_lower in name.lower():
            results.append({"name": name, **info})
            if len(results) >= limit:
                break
    return results


def get_dependencies_for(uuid: str) -> dict:
    """Get calls and called_by for a specific object."""
    calls = [d for d in _store["dependencies"] if d["source_uuid"] == uuid]
    called_by = [d for d in _store["dependencies"] if d["target_uuid"] == uuid]
    return {"calls": calls, "called_by": called_by}


def is_loaded() -> bool:
    return _store["meta"] is not None


# ─── Utility ──────────────────────────────────────────────────────

def _write_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
