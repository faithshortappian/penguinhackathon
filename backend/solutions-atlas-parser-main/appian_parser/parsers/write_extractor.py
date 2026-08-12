"""Shared extraction of data-write targets from process-model nodes.

A process-model node "writes" data when it is one of the data-service write
smart services. This module turns such a node into a structured ``writes``
list so downstream consumers (bundle structure, Atlas MCP coverage gate) get a
deterministic, machine-checkable contract instead of having to re-read raw SAIL.

Two write mechanisms are recognised:

* ``RECORD`` — the *Write Records* smart service
  (``internal3.write_records_to_source_23r3``). The target is a record type,
  referenced in the node's input/output expressions as
  ``recordType!{<uuid>}<Name>``. The physical ``table`` is intentionally **not**
  resolved here — it is resolved downstream from ``record_type_map.json``
  (which maps table → record_type_uuid). The parser only needs to record the
  record-type *identity*.

* ``CDT`` — the *Write to Data Store Entity* / *Write to Multiple DSE* smart
  services (``appian.system.smart-services.[multi-]write-to-data-store``).
  See :func:`extract_cdt_writes` — validated against real DSE packages
  (ConnectedUnderwriting, ContractWriting, VendorManagement, AwardManagement).

This module is the single source of truth for write-target extraction.
"""

from __future__ import annotations

import re
from typing import Any

# Activity-class local-ids for the data-service write smart services.
RECORD_WRITE_NODE_TYPE = "internal3.write_records_to_source_23r3"  # Write Records
DSE_WRITE_NODE_TYPES = {
    "appian.system.smart-services.write-to-data-store",        # Write to Data Store Entity
    "appian.system.smart-services.multi-write-to-data-store",  # Write to Multiple DSE
}
WRITE_NODE_TYPES = {RECORD_WRITE_NODE_TYPE} | DSE_WRITE_NODE_TYPES

# recordType!{<uuid>}<Name>  → group(1)=uuid, group(2)=name (brace form, seen in some code)
RT_PATTERN = re.compile(r"recordType!\{([^}]+)\}(\w+)")
# recordType!<Name>  → the form the reference resolver produces in process-model
# node inputs (the URN is rewritten to the record type's name). group(1)=name.
# Stops at the first non-word char so field refs (recordType!X.field) yield "X".
RECORD_TYPE_NAME_RE = re.compile(r"recordType!([a-zA-Z_][a-zA-Z0-9_]*)")
# Canonical pre-resolution URN, e.g.
# =#"urn:appian:record-type:v1:b6081510-0d11-4d51-8eba-966610b168db". group(1)=uuid.
RECORD_TYPE_URN_RE = re.compile(
    r"urn:appian:record-type:v1:"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:-[\w-]+)?)",
    re.I,
)
# cons!<NAME>  → group(1)=constant name (DataStoreEntity reference in write nodes)
CONS_NAME_RE = re.compile(r"cons!([a-zA-Z_][a-zA-Z0-9_]*)")


def _node_expressions(node: dict[str, Any]) -> list[str]:
    """Collect all input/output expression strings on a node."""
    exprs: list[str] = []
    for inp in node.get("inputs", []) or []:
        expr = inp.get("input_expression")
        if expr:
            exprs.append(expr)
    for out in node.get("outputs", []) or []:
        expr = out.get("output_expression") or out.get("save_into")
        if expr:
            exprs.append(expr)
    return exprs


def extract_record_writes(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract RECORD-mechanism writes from a Write Records node.

    The target record type is read from the node's input/output expressions. By
    the time bundles are built the reference resolver has rewritten record-type
    references to the SAIL name form ``recordType!<Name>`` (a list yields
    several). Two other forms are handled defensively: the brace form
    ``recordType!{<uuid>}<Name>`` and the pre-resolution URN
    ``urn:appian:record-type:v1:<uuid>``.

    Each entry carries whatever identity is available — ``record_type_name``
    and/or ``record_type_uuid``. The physical ``table`` (and any missing
    uuid/name) is resolved downstream from ``record_type_map.json``.
    """
    if node.get("node_type") != RECORD_WRITE_NODE_TYPE:
        return []

    by_name: dict[str, dict[str, Any]] = {}
    by_uuid: dict[str, dict[str, Any]] = {}
    via = node.get("node_type")

    for expr in _node_expressions(node):
        # Brace form: recordType!{uuid}Name  (carries both)
        for m in RT_PATTERN.finditer(expr):
            rt_uuid, rt_name = m.group(1), m.group(2)
            entry = by_uuid.setdefault(rt_uuid, {
                "mechanism": "RECORD", "record_type_uuid": rt_uuid,
                "operation": "WRITE", "via": via,
            })
            entry.setdefault("record_type_name", rt_name)
        # URN form: urn:appian:record-type:v1:uuid  (carries uuid only)
        for m in RECORD_TYPE_URN_RE.finditer(expr):
            rt_uuid = m.group(1)
            by_uuid.setdefault(rt_uuid, {
                "mechanism": "RECORD", "record_type_uuid": rt_uuid,
                "operation": "WRITE", "via": via,
            })
        # Name form: recordType!Name  (resolver output; carries name only).
        # Skip the brace form (handled above) — there '{' follows 'recordType!'.
        for m in RECORD_TYPE_NAME_RE.finditer(expr):
            rt_name = m.group(1)
            if rt_name in by_name or any(
                e.get("record_type_name") == rt_name for e in by_uuid.values()
            ):
                continue
            by_name[rt_name] = {
                "mechanism": "RECORD", "record_type_name": rt_name,
                "operation": "WRITE", "via": via,
            }

    return list(by_uuid.values()) + list(by_name.values())


def extract_cdt_writes(
    node: dict[str, Any],
    *,
    constant_entity_index: dict[str, str] | None = None,
    entity_cdt_index: dict[str, str] | None = None,
    cdt_table_index: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Extract CDT-mechanism writes from a Write-to-Data-Store node.

    Grounded against real packages (ConnectedUnderwriting): the smart service's
    ``DataStoreEntity`` input resolves to ``cons!<NAME>`` — a DataStoreEntity
    constant. The full resolution chain is::

        cons!NAME
          -> constant_entity_index[NAME]   (entity_uuid, from the constant's value @id)
          -> entity_cdt_index[entity_uuid] (cdt_type, from the Data Store)
          -> cdt_table_index[cdt_type]     (table, from the CDT @Table annotation)

    Any link that can't be resolved degrades gracefully (the entry still carries
    whatever identity is known: the constant name and/or entity uuid / cdt_type).
    """
    if node.get("node_type") not in DSE_WRITE_NODE_TYPES:
        return []

    constant_entity_index = constant_entity_index or {}
    entity_cdt_index = entity_cdt_index or {}
    cdt_table_index = cdt_table_index or {}
    via = node.get("node_type")

    # The entity is named in the "DataStoreEntity" input; fall back to scanning
    # all inputs for a cons! reference if the input name differs.
    entity_exprs = [
        inp.get("input_expression", "") or ""
        for inp in (node.get("inputs") or [])
        if inp.get("input_name") == "DataStoreEntity"
    ] or _node_expressions(node)

    writes: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for expr in entity_exprs:
        for m in CONS_NAME_RE.finditer(expr):
            const_name = m.group(1)
            entity_uuid = constant_entity_index.get(const_name)
            cdt_type = entity_cdt_index.get(entity_uuid) if entity_uuid else None
            table = cdt_table_index.get(cdt_type) if cdt_type else None
            key = entity_uuid or const_name
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entry: dict[str, Any] = {
                "mechanism": "CDT",
                "data_store_entity": const_name,
                "operation": "WRITE",
                "via": via,
            }
            if entity_uuid:
                entry["data_store_entity_uuid"] = entity_uuid
            if cdt_type:
                entry["cdt_type"] = cdt_type
            if table:
                entry["table"] = table
            writes.append(entry)
    return writes


def extract_node_writes(
    node: dict[str, Any],
    *,
    constant_entity_index: dict[str, str] | None = None,
    entity_cdt_index: dict[str, str] | None = None,
    cdt_table_index: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return the combined ``writes`` list for a node (RECORD + CDT)."""
    node_type = node.get("node_type")
    if node_type == RECORD_WRITE_NODE_TYPE:
        return extract_record_writes(node)
    if node_type in DSE_WRITE_NODE_TYPES:
        return extract_cdt_writes(
            node,
            constant_entity_index=constant_entity_index,
            entity_cdt_index=entity_cdt_index,
            cdt_table_index=cdt_table_index,
        )
    return []


def build_cdt_table_index(parsed_objects: list[Any]) -> dict[str, str]:
    """Build {cdt_type -> table} from parsed CDT objects (table from @Table)."""
    index: dict[str, str] = {}
    for obj in parsed_objects:
        if getattr(obj, "object_type", None) != "CDT":
            continue
        data = getattr(obj, "data", {}) or {}
        cdt_type = data.get("uuid")
        table = data.get("table")
        if cdt_type and table:
            index[cdt_type] = table
    return index


def build_entity_cdt_index(parsed_objects: list[Any]) -> dict[str, str]:
    """Build {data_store_entity_uuid -> cdt_type} from parsed Data Store objects."""
    index: dict[str, str] = {}
    for obj in parsed_objects:
        if getattr(obj, "object_type", None) != "Data Store":
            continue
        data = getattr(obj, "data", {}) or {}
        for entity in data.get("entities", []) or []:
            euid = entity.get("entity_uuid")
            cdt_type = entity.get("cdt_type")
            if euid and cdt_type:
                index[euid] = cdt_type
    return index


def build_constant_entity_index(parsed_objects: list[Any]) -> dict[str, str]:
    """Build {constant_name -> data_store_entity_uuid} from DataStoreEntity constants."""
    index: dict[str, str] = {}
    for obj in parsed_objects:
        if getattr(obj, "object_type", None) != "Constant":
            continue
        data = getattr(obj, "data", {}) or {}
        euid = data.get("data_store_entity_uuid")
        if euid and data.get("name"):
            index[data["name"]] = euid
        elif euid and getattr(obj, "name", None):
            index[obj.name] = euid
    return index
