"""Record type URN resolver for SAIL code.

Resolves record type URNs to human-readable names:
  - urn:appian:record-type:v1:{rt_uuid}       → recordType!Name
  - urn:appian:record-field:v1:{rt}/{field}    → recordType!Name.fieldName
  - urn:appian:record-relationship:v1:{rt}/{rel} → recordType!Name.relName

Handles standard UUIDs, suffixed UUIDs, name-based field segments,
multi-segment relationship chains, and %40-encoded traversals.
"""

import re

from appian_parser.domain.constants import RT_UUID_PATTERN


class RecordTypeURNResolver:
    """Resolves record type URNs in SAIL code to human-readable names.

    Args:
        record_types: rt_uuid → rt_name mapping.
        fields: (rt_uuid, field_uuid) → field_name mapping.
        relationships: (rt_uuid, rel_uuid) → (rel_name, target_rt_uuid) mapping.
    """

    def __init__(
        self,
        record_types: dict[str, str],
        fields: dict[tuple[str, str], str],
        relationships: dict[tuple[str, str], tuple[str, str | None]],
    ) -> None:
        self._record_types = record_types
        self._fields = fields
        self._relationships = relationships

    def resolve_sail_code(self, code: str) -> str:
        """Resolve all record type URNs in SAIL code.

        Applies resolution passes in order:
        1. Constructor patterns: recordType!Name(
        2. Standard URNs: type/field/relationship with UUID segments
        3. Name-based field URNs: field segment is a name, not UUID
        4. Chain URNs: 2+ segments (relationship traversals)
        5. Encoded URNs: %40-encoded relationship traversals

        Args:
            code: SAIL code containing record type URNs.

        Returns:
            Code with URNs replaced by recordType!Name.field notation.
        """
        U = RT_UUID_PATTERN

        code = self._resolve_constructors(code, U)
        code = self._resolve_standard_urns(code, U)
        code = self._resolve_name_based_urns(code, U)
        code = self._resolve_chain_urns(code, U)
        code = self._resolve_encoded_urns(code, U)

        return code

    # ── Resolution Passes ────────────────────────────────────────────────

    def _resolve_constructors(self, code: str, U: str) -> str:
        """Resolve constructor patterns: #"urn:appian:record-type:v1:{uuid}"("""
        pattern = rf'#"urn:appian:record-type:v1:({U})"\s*\('
        for match in reversed(list(re.finditer(pattern, code, re.I))):
            rt_uuid = self._normalize_rt(match.group(1))
            if rt_uuid in self._record_types:
                replacement = f"recordType!{self._record_types[rt_uuid]}("
                code = code[:match.start()] + replacement + code[match.end():]
        return code

    def _resolve_standard_urns(self, code: str, U: str) -> str:
        """Resolve standard URNs with UUID-based segments."""
        pattern = rf'#"urn:appian:(record-type|record-field|record-relationship):v1:({U})(?:/({U}))?(?:/({U}))?"'
        for match in reversed(list(re.finditer(pattern, code, re.I))):
            urn_type, rt_raw, seg1, seg2 = match.groups()
            rt_uuid = self._normalize_rt(rt_raw)
            if rt_uuid not in self._record_types:
                continue

            replacement = self._resolve_urn_segments(urn_type.lower(), rt_uuid, seg1, seg2)
            if replacement:
                code = code[:match.start()] + replacement + code[match.end():]
        return code

    def _resolve_name_based_urns(self, code: str, U: str) -> str:
        """Resolve URNs where the field segment is a name, not a UUID."""
        pattern = rf'#"urn:appian:record-field:v1:({U})/([a-zA-Z_]\w*)"'
        for match in reversed(list(re.finditer(pattern, code, re.I))):
            rt_uuid = self._normalize_rt(match.group(1))
            if rt_uuid in self._record_types:
                code = (
                    code[:match.start()]
                    + f"recordType!{self._record_types[rt_uuid]}.{match.group(2)}"
                    + code[match.end():]
                )
        return code

    def _resolve_chain_urns(self, code: str, U: str) -> str:
        """Resolve multi-segment relationship traversal URNs (2+ segments)."""
        pattern = rf'#"urn:appian:record-field:v1:({U})((?:/{U}){{2,}})"'
        for match in reversed(list(re.finditer(pattern, code, re.I))):
            rt_uuid = self._normalize_rt(match.group(1))
            if rt_uuid not in self._record_types:
                continue

            full_urn = match.group(0)[1:-1]  # Strip #" and "
            separator = match.group(1) + '/'
            after_rt = full_urn.split(separator, 1)[1] if separator in full_urn else ''

            names = self._resolve_chain_segments(rt_uuid, after_rt.split('/'))
            if names:
                code = (
                    code[:match.start()]
                    + f"recordType!{self._record_types[rt_uuid]}.{'.'.join(names)}"
                    + code[match.end():]
                )
        return code

    def _resolve_encoded_urns(self, code: str, U: str) -> str:
        """Resolve %40-encoded relationship traversals (field%40subfield)."""
        pattern = rf'#"urn:appian:record-field:v1:({U})/([a-zA-Z_]\w*%40[a-zA-Z_]\w*)"'
        for match in reversed(list(re.finditer(pattern, code, re.I))):
            rt_uuid = self._normalize_rt(match.group(1))
            if rt_uuid in self._record_types:
                decoded = match.group(2).replace('%40', '.')
                code = (
                    code[:match.start()]
                    + f"recordType!{self._record_types[rt_uuid]}.{decoded}"
                    + code[match.end():]
                )
        return code

    # ── Helpers ──────────────────────────────────────────────────────────

    def _normalize_rt(self, raw: str) -> str:
        """Normalize a record type UUID, trying full then base (first 36 chars)."""
        low = raw.lower()
        if low in self._record_types:
            return low
        return low[:36]

    def _resolve_urn_segments(
        self, urn_type: str, rt_uuid: str, seg1: str | None, seg2: str | None,
    ) -> str | None:
        """Resolve a standard URN's segments to a recordType!Name.field string."""
        rt_name = self._record_types[rt_uuid]

        if urn_type == 'record-type':
            return f"recordType!{rt_name}"

        if urn_type == 'record-field':
            if seg1 and seg2:
                return self._resolve_rel_then_field(rt_uuid, rt_name, seg1, seg2)
            if seg1:
                return self._resolve_field_or_rel(rt_uuid, rt_name, seg1)
            return None

        if urn_type == 'record-relationship' and seg1:
            rel_key = (rt_uuid, seg1.lower())
            if rel_key in self._relationships:
                return f"recordType!{rt_name}.{self._relationships[rel_key][0]}"

        return None

    def _resolve_rel_then_field(
        self, rt_uuid: str, rt_name: str, rel_seg: str, field_seg: str,
    ) -> str | None:
        """Resolve a two-segment URN: relationship + field."""
        rel_key = (rt_uuid, rel_seg.lower())
        if rel_key not in self._relationships:
            return None
        rel_name, target_rt = self._relationships[rel_key]
        if not target_rt:
            return None
        field_key = (target_rt.lower(), field_seg.lower())
        if field_key not in self._fields:
            return None
        return f"recordType!{rt_name}.{rel_name}.{self._fields[field_key]}"

    def _resolve_field_or_rel(self, rt_uuid: str, rt_name: str, seg: str) -> str | None:
        """Resolve a single-segment URN: try field first, then relationship."""
        seg_lower = seg.lower()
        field_key = (rt_uuid, seg_lower)
        if field_key in self._fields:
            return f"recordType!{rt_name}.{self._fields[field_key]}"
        rel_key = (rt_uuid, seg_lower)
        if rel_key in self._relationships:
            return f"recordType!{rt_name}.{self._relationships[rel_key][0]}"
        return None

    def _resolve_chain_segments(self, rt_uuid: str, segments: list[str]) -> list[str] | None:
        """Resolve a chain of relationship/field segments."""
        names: list[str] = []
        current_rt = rt_uuid
        for seg in segments:
            seg_lower = seg.lower()
            rel_key = (current_rt, seg_lower)
            if rel_key in self._relationships:
                rel_name, target_rt = self._relationships[rel_key]
                names.append(rel_name)
                if target_rt:
                    current_rt = self._normalize_rt(target_rt)
            elif (current_rt, seg_lower) in self._fields:
                names.append(self._fields[(current_rt, seg_lower)])
            else:
                return None
        return names or None
