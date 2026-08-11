"""
UUID utilities for Appian object handling.

This module provides utilities for detecting and resolving Appian UUIDs.
Appian uses several UUID formats that need to be recognized and resolved
to human-readable object names.

UUID Formats Supported:
1. _a-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX_XXXXX (with _a- or _e- prefix and suffix)
2. XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX (standard UUID)
3. XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX-suffix (with suffix only)
"""

import re
from typing import Dict, Any, Optional


class UUIDUtils:
    """
    Utilities for Appian UUID handling.

    This class provides static methods for detecting and resolving
    Appian UUIDs. It supports multiple UUID formats used by Appian
    for different object types.

    Example:
        >>> UUIDUtils.is_appian_uuid('_a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398')
        True
        >>> UUIDUtils.is_appian_uuid('not-a-uuid')
        False
    """

    # Compiled regex patterns for performance
    # Pattern 1: _a- or _e- prefix with _suffix
    # e.g., _a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398
    _PATTERN_PREFIXED = re.compile(
        r'^_[ae]-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_[\w-]+$',
        re.IGNORECASE
    )

    # Pattern 2: Standard UUID
    # e.g., 0006eed1-0f7f-8000-0020-7f0000014e7a
    _PATTERN_STANDARD = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    # Pattern 3: UUID with suffix
    # e.g., 82127412-76f3-43c7-9b98-c2201b1e158b-as_rm_pro
    _PATTERN_SUFFIXED = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[\w-]+$',
        re.IGNORECASE
    )

    @staticmethod
    def is_appian_uuid(value: Optional[str]) -> bool:
        """
        Check if a value looks like an Appian UUID.

        Supports multiple Appian UUID formats:
        1. _a-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX_XXXXX (prefixed with suffix)
        2. XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX (standard UUID)
        3. XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX-suffix (with suffix only)

        Args:
            value: String value to check

        Returns:
            True if value matches any Appian UUID pattern, False otherwise

        Examples:
            >>> UUIDUtils.is_appian_uuid('_a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398')
            True
            >>> UUIDUtils.is_appian_uuid('_e-0000e4ea-0367-8000-9af4-01075c01075c_322')
            True
            >>> UUIDUtils.is_appian_uuid('0006eed1-0f7f-8000-0020-7f0000014e7a')
            True
            >>> UUIDUtils.is_appian_uuid('82127412-76f3-43c7-9b98-c2201b1e158b-as_rm_pro')
            True
            >>> UUIDUtils.is_appian_uuid('not-a-uuid')
            False
            >>> UUIDUtils.is_appian_uuid(None)
            False
            >>> UUIDUtils.is_appian_uuid('')
            False
        """
        if not value or not isinstance(value, str):
            return False

        return bool(
            UUIDUtils._PATTERN_PREFIXED.match(value) or
            UUIDUtils._PATTERN_STANDARD.match(value) or
            UUIDUtils._PATTERN_SUFFIXED.match(value)
        )

    @staticmethod
    def resolve_uuid(
        uuid_value: Optional[str],
        object_lookup: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Resolve UUID to object name if found in lookup.

        Looks up the UUID in the provided object lookup dictionary
        and returns the object name if found. If not found, returns
        the original UUID value.

        Args:
            uuid_value: Appian UUID to resolve
            object_lookup: Dict mapping UUID -> {name, object_type}

        Returns:
            Object name if found in lookup, otherwise the original value

        Examples:
            >>> lookup = {'uuid-1': {'name': 'MyInterface', 'object_type': 'Interface'}}
            >>> UUIDUtils.resolve_uuid('uuid-1', lookup)
            'MyInterface'
            >>> UUIDUtils.resolve_uuid('unknown-uuid', lookup)
            'unknown-uuid'
            >>> UUIDUtils.resolve_uuid(None, lookup)
            ''
        """
        if not uuid_value:
            return ''

        obj_info = object_lookup.get(uuid_value)
        if obj_info:
            return obj_info.get('name', uuid_value)

        return uuid_value

    @staticmethod
    def resolve_uuid_with_type(
        uuid_value: Optional[str],
        object_lookup: Dict[str, Dict[str, Any]]
    ) -> tuple:
        """
        Resolve UUID to object name and type if found in lookup.

        Similar to resolve_uuid but also returns the object type.

        Args:
            uuid_value: Appian UUID to resolve
            object_lookup: Dict mapping UUID -> {name, object_type}

        Returns:
            Tuple of (name, object_type) if found, otherwise (uuid_value, None)

        Examples:
            >>> lookup = {'uuid-1': {'name': 'MyInterface', 'object_type': 'Interface'}}
            >>> UUIDUtils.resolve_uuid_with_type('uuid-1', lookup)
            ('MyInterface', 'Interface')
            >>> UUIDUtils.resolve_uuid_with_type('unknown', lookup)
            ('unknown', None)
        """
        if not uuid_value:
            return ('', None)

        obj_info = object_lookup.get(uuid_value)
        if obj_info:
            return (
                obj_info.get('name', uuid_value),
                obj_info.get('object_type')
            )

        return (uuid_value, None)

    @staticmethod
    def extract_base_uuid(value: Optional[str]) -> Optional[str]:
        """
        Extract the base UUID from an Appian UUID with prefix/suffix.

        Strips the _a-/_e- prefix and _XXXXX suffix to get the core UUID.

        Args:
            value: Appian UUID string

        Returns:
            Base UUID without prefix/suffix, or None if not a valid UUID

        Examples:
            >>> UUIDUtils.extract_base_uuid('_a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398')
            '0000e6a4-3c85-8000-9ba5-011c48011c48'
            >>> UUIDUtils.extract_base_uuid('0006eed1-0f7f-8000-0020-7f0000014e7a')
            '0006eed1-0f7f-8000-0020-7f0000014e7a'
        """
        if not value or not isinstance(value, str):
            return None

        # Handle prefixed format: _a-UUID_suffix or _e-UUID_suffix
        if value.startswith('_a-') or value.startswith('_e-'):
            # Remove prefix and find the underscore suffix
            stripped = value[3:]  # Remove _a- or _e-
            underscore_pos = stripped.rfind('_')
            if underscore_pos > 0:
                return stripped[:underscore_pos]

        # Handle suffixed format: UUID-suffix
        if UUIDUtils._PATTERN_SUFFIXED.match(value):
            # Find the position after the standard UUID (36 chars)
            return value[:36]

        # Handle standard format
        if UUIDUtils._PATTERN_STANDARD.match(value):
            return value

        return None

    @staticmethod
    def format_uuid_with_name(
        uuid_value: str,
        name: str,
        include_uuid: bool = True
    ) -> str:
        """
        Format a UUID with its resolved name for display.

        Creates a human-readable string combining the name and UUID.

        Args:
            uuid_value: The original UUID
            name: The resolved object name
            include_uuid: Whether to include the UUID in parentheses

        Returns:
            Formatted string like "ObjectName (uuid)" or just "ObjectName"

        Examples:
            >>> UUIDUtils.format_uuid_with_name('uuid-1', 'MyInterface')
            'MyInterface (uuid-1)'
            >>> UUIDUtils.format_uuid_with_name('uuid-1', 'MyInterface', include_uuid=False)
            'MyInterface'
        """
        if include_uuid and uuid_value != name:
            return f"{name} ({uuid_value})"
        return name
