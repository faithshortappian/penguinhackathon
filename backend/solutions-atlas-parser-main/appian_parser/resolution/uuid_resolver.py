"""UUID reference resolver for SAIL code.

Resolves prefixed UUIDs (#"_a-uuid_suffix") and bare UUIDs (#"uuid")
to human-readable names like rule!Name, cons!Name, type!Name.
"""

import re
from typing import Any

from appian_parser.domain.constants import CANONICAL_RE
from appian_parser.resolution.uuid_utils import UUIDUtils

# Object type → SAIL prefix mapping
_TYPE_PREFIX: dict[str, str] = {
    'Expression Rule': 'rule!',
    'Interface': 'rule!',
    'Constant': 'cons!',
    'CDT': 'type!',
    'Data Type': 'type!',
}


class UUIDResolver:
    """Resolves UUID references in SAIL code to human-readable names.

    Handles three resolution strategies:
    1. Full UUID match (exact lookup)
    2. Canonical prefix match (strips app suffix for cross-app references)
    3. Base UUID match (strips all prefixes/suffixes)

    Args:
        object_lookup: UUID → {name, object_type} mapping.
    """

    def __init__(self, object_lookup: dict[str, dict[str, Any]]) -> None:
        self._lookup = object_lookup
        self._prefixed_re = re.compile(r'#"(_[ae]-[\w-]+)"')
        self._bare_re = re.compile(r'#"([a-f0-9\-]{36})"')

        # Build canonical prefix index for cross-app-suffix matching
        self._canonical: dict[str, dict[str, Any]] = {}
        for uid, entry in object_lookup.items():
            m = CANONICAL_RE.match(uid)
            if m:
                self._canonical.setdefault(m.group(1), entry)

    def resolve_sail_code(self, code: str) -> str:
        """Resolve all UUID references in SAIL code.

        Args:
            code: SAIL code containing #"uuid" references.

        Returns:
            Code with UUIDs replaced by rule!/cons!/type! names.
        """
        code = self._prefixed_re.sub(self._replace_prefixed, code)
        code = self._bare_re.sub(self._replace_bare, code)
        return code

    def resolve_uuid(self, uuid_value: str) -> str:
        """Resolve a single UUID to its SAIL-prefixed name.

        Args:
            uuid_value: UUID string to resolve.

        Returns:
            Resolved name (e.g., 'rule!MyRule') or original UUID if not found.
        """
        entry = self._lookup.get(uuid_value)
        if not entry:
            return uuid_value
        return self._format_entry(entry)

    # ── Private Methods ──────────────────────────────────────────────────

    def _replace_prefixed(self, match: re.Match) -> str:
        """Replace a prefixed UUID match (#"_a-uuid_suffix")."""
        uuid = match.group(1)

        # Try full UUID
        entry = self._lookup.get(uuid)
        if entry:
            return self._format_entry(entry)

        # Try canonical prefix (strips app suffix)
        m = CANONICAL_RE.match(uuid)
        if m:
            entry = self._canonical.get(m.group(1))
            if entry:
                return self._format_entry(entry)

        # Try base UUID
        base = UUIDUtils.extract_base_uuid(uuid)
        if base:
            entry = self._lookup.get(base)
            if entry:
                return self._format_entry(entry)

        return match.group(0)

    def _replace_bare(self, match: re.Match) -> str:
        """Replace a bare UUID match (#"uuid")."""
        entry = self._lookup.get(match.group(1))
        return self._format_entry(entry) if entry else match.group(0)

    @staticmethod
    def _format_entry(entry: dict[str, Any]) -> str:
        """Format a lookup entry as a SAIL-prefixed name."""
        prefix = _TYPE_PREFIX.get(entry.get('object_type', ''), 'rule!')
        return f"{prefix}{entry.get('name', '')}"
