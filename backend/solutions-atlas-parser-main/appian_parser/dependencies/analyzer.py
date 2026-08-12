"""Dependency analysis for parsed Appian objects.

Extracts inter-object dependencies by scanning SAIL code fields for
named references (rule!, cons!, type!, recordType!), UUID references,
and record type URNs, plus structural UUID fields for direct references.
"""

import re
from dataclasses import dataclass
from typing import Any

from appian_parser.domain.constants import (
    CANONICAL_RE,
    CONS_REF_RE,
    RECORD_TYPE_REF_RE,
    RT_URN_RE,
    RULE_REF_RE,
    SAIL_CODE_FIELDS,
    STRUCTURAL_FIELDS,
    TYPE_REF_RE,
    UUID_FULL_RE,
    UUID_PREFIXED_RE,
    UUID_STANDARD_RE,
    infer_dependency_type,
)
from appian_parser.domain.field_walker import walk_field_paths


@dataclass(frozen=True)
class Dependency:
    """Represents a dependency between two parsed objects."""

    source_uuid: str
    source_name: str
    source_type: str
    target_uuid: str
    target_name: str
    target_type: str
    dependency_type: str
    reference_context: str
    is_resolved: bool


class DependencyAnalyzer:
    """Extracts inter-object dependencies from parsed objects.

    Works in-memory by building UUID and name lookup tables, then scanning
    configured field paths for references.
    """

    def analyze(self, parsed_objects: list) -> list[Dependency]:
        """Analyze all parsed objects and extract dependencies.

        Args:
            parsed_objects: List of ParsedObject instances.

        Returns:
            List of Dependency instances representing all found dependencies.
        """
        uuid_lookup, name_lookup = self._build_lookups(parsed_objects)
        all_deps: list[Dependency] = []

        for obj in parsed_objects:
            all_deps.extend(self._extract_for_object(obj, uuid_lookup, name_lookup))

        return all_deps

    # ── Lookup Building ──────────────────────────────────────────────────

    @staticmethod
    def _build_lookups(parsed_objects: list) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build UUID and name lookup tables with base and canonical indexing."""
        uuid_lookup: dict[str, Any] = {}
        name_lookup: dict[str, Any] = {}

        for obj in parsed_objects:
            uuid_lookup[obj.uuid] = obj
            name_lookup[obj.name.lower()] = obj

            if obj.uuid.startswith('_') and '_' in obj.uuid[3:]:
                m = UUID_PREFIXED_RE.match(obj.uuid)
                if m:
                    uuid_lookup.setdefault(m.group(1), obj)
                cm = CANONICAL_RE.match(obj.uuid)
                if cm:
                    uuid_lookup.setdefault(cm.group(1), obj)

        return uuid_lookup, name_lookup

    # ── Per-Object Extraction ────────────────────────────────────────────

    def _extract_for_object(
        self, obj: Any, uuid_lookup: dict, name_lookup: dict,
    ) -> list[Dependency]:
        """Extract all dependencies for a single object."""
        seen: set[str] = set()
        deps: list[Dependency] = []

        # SAIL code fields — extract named refs and UUID refs
        for field_path in SAIL_CODE_FIELDS.get(obj.object_type, []):
            for value in walk_field_paths(obj.data, field_path):
                if value:
                    self._extract_from_text(value, field_path, obj, uuid_lookup, name_lookup, seen, deps)

        # Structural UUID fields — direct object references
        for field_path, dep_type in STRUCTURAL_FIELDS.get(obj.object_type, []):
            for value in walk_field_paths(obj.data, field_path):
                if value and isinstance(value, str):
                    target = uuid_lookup.get(value) or name_lookup.get(value.lower())
                    if target and target.uuid != obj.uuid and target.uuid not in seen:
                        seen.add(target.uuid)
                        deps.append(Dependency(
                            obj.uuid, obj.name, obj.object_type,
                            target.uuid, target.name, target.object_type,
                            dep_type, field_path, True,
                        ))

        return deps

    # ── Text Scanning ────────────────────────────────────────────────────

    def _extract_from_text(
        self,
        text: str,
        context: str,
        obj: Any,
        uuid_lookup: dict,
        name_lookup: dict,
        seen: set[str],
        deps: list[Dependency],
    ) -> None:
        """Extract all dependency types from a text string."""
        self._extract_named_refs(text, context, obj, name_lookup, seen, deps)
        self._extract_rt_urns(text, context, obj, uuid_lookup, seen, deps)
        self._extract_uuid_refs(text, context, obj, uuid_lookup, seen, deps)

    def _extract_named_refs(
        self, text: str, context: str, obj: Any,
        name_lookup: dict, seen: set[str], deps: list[Dependency],
    ) -> None:
        """Extract named references: rule!, cons!, type!, recordType!"""
        for pattern, dep_type in [
            (RULE_REF_RE, 'CALLS'),
            (CONS_REF_RE, 'USES_CONSTANT'),
            (TYPE_REF_RE, 'USES_CDT'),
            (RECORD_TYPE_REF_RE, 'USES_RECORD_TYPE'),
        ]:
            for m in pattern.finditer(text):
                target = name_lookup.get(m.group(1).lower())
                if target and target.uuid != obj.uuid and target.uuid not in seen:
                    seen.add(target.uuid)
                    deps.append(Dependency(
                        obj.uuid, obj.name, obj.object_type,
                        target.uuid, target.name, target.object_type,
                        dep_type, context, True,
                    ))

    @staticmethod
    def _extract_rt_urns(
        text: str, context: str, obj: Any,
        uuid_lookup: dict, seen: set[str], deps: list[Dependency],
    ) -> None:
        """Extract record type URN references."""
        for m in RT_URN_RE.finditer(text):
            uuid = m.group(1).lower()
            target = uuid_lookup.get(uuid)
            if target and target.uuid != obj.uuid and target.uuid not in seen:
                seen.add(target.uuid)
                deps.append(Dependency(
                    obj.uuid, obj.name, obj.object_type,
                    target.uuid, target.name, target.object_type,
                    'USES_RECORD_TYPE', context, True,
                ))

    @staticmethod
    def _extract_uuid_refs(
        text: str, context: str, obj: Any,
        uuid_lookup: dict, seen: set[str], deps: list[Dependency],
    ) -> None:
        """Extract UUID references (full prefixed and standard)."""
        for pattern in [UUID_FULL_RE, UUID_STANDARD_RE]:
            for m in pattern.finditer(text):
                uuid = m.group(1)
                target = uuid_lookup.get(uuid)
                if not target:
                    cm = CANONICAL_RE.match(uuid)
                    if cm:
                        target = uuid_lookup.get(cm.group(1))
                if target and target.uuid != obj.uuid and target.uuid not in seen:
                    seen.add(target.uuid)
                    deps.append(Dependency(
                        obj.uuid, obj.name, obj.object_type,
                        target.uuid, target.name, target.object_type,
                        infer_dependency_type(target.object_type), context, True,
                    ))
