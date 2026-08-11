"""
Base parser for Appian XML files.

This module provides the abstract base class for all object-specific parsers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import xml.etree.ElementTree as ET
import re


class BaseParser(ABC):
    """
    Abstract base class for parsing Appian XML files.

    All object-specific parsers should inherit from this class and implement
    the parse() method to extract object-specific data.
    """

    def __init__(self):
        """Initialize the base parser."""
        pass

    @abstractmethod
    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse XML file and extract object data.

        Must extract ALL relevant data from XML.

        Args:
            xml_path: Path to the XML file to parse

        Returns:
            Dict with keys:
            - uuid: str
            - name: str
            - version_uuid: str
            - description: str
            - <object_specific_fields>

        Raises:
            ParsingException: If XML parsing fails
        """
        pass

    def _extract_basic_info(self, root: ET.Element) -> Dict[str, Any]:
        """
        Extract common fields from XML root element.

        Extracts uuid, name, version_uuid, and description that are common
        to all Appian objects.

        Args:
            root: Root element of the parsed XML tree

        Returns:
            Dict containing:
            - uuid: Object UUID
            - name: Object name
            - version_uuid: Version UUID
            - description: Object description (optional)
        """
        return {
            'uuid': root.get('uuid'),
            'name': root.get('name'),
            'version_uuid': root.get('versionUuid'),
            'description': self._get_text(root, 'description')
        }

    def _get_text(self, element: ET.Element, path: str) -> Optional[str]:
        """
        Safely get text from XML element.

        Args:
            element: Parent XML element
            path: XPath to the target element

        Returns:
            Text content of the element, or None if element not found
        """
        elem = element.find(path)
        return elem.text if elem is not None and elem.text else None

    def _get_attribute(
        self,
        element: ET.Element,
        path: str,
        attribute: str
    ) -> Optional[str]:
        """
        Safely get attribute from XML element.

        Args:
            element: Parent XML element
            path: XPath to the target element
            attribute: Name of the attribute to retrieve

        Returns:
            Attribute value, or None if element or attribute not found
        """
        elem = element.find(path)
        return elem.get(attribute) if elem is not None else None

    def _clean_sail_code(self, sail_code: Optional[str]) -> Optional[str]:
        """
        Clean and normalize SAIL code for comparison.

        Removes extra whitespace, normalizes line endings, and trims
        leading/trailing whitespace to ensure consistent comparison.

        Args:
            sail_code: Raw SAIL code string

        Returns:
            Cleaned SAIL code, or None if input is None or empty
        """
        if not sail_code:
            return None

        # Normalize line endings to \n
        cleaned = sail_code.replace('\r\n', '\n').replace('\r', '\n')

        # Remove leading/trailing whitespace from each line
        lines = [line.rstrip() for line in cleaned.split('\n')]

        # Remove empty lines at start and end
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        # Join lines back together
        cleaned = '\n'.join(lines)

        # Normalize multiple spaces to single space
        # (but preserve indentation)
        # This regex preserves leading whitespace but collapses
        # multiple spaces in content
        cleaned = re.sub(r'(?<=\S)  +', ' ', cleaned)

        return cleaned.strip() if cleaned else None

    def _get_boolean(
        self,
        element: ET.Element,
        path: str,
        default: bool = False
    ) -> bool:
        """
        Safely get boolean value from XML element.

        Args:
            element: Parent XML element
            path: XPath to the target element
            default: Default value if element not found

        Returns:
            Boolean value (true/false converted to True/False)
        """
        text = self._get_text(element, path)
        if text is None:
            return default
        return text.lower() in ('true', '1', 'yes')

    def _get_int(
        self,
        element: ET.Element,
        path: str,
        default: int = 0
    ) -> int:
        """
        Safely get integer value from XML element.

        Args:
            element: Parent XML element
            path: XPath to the target element
            default: Default value if element not found or conversion fails

        Returns:
            Integer value
        """
        text = self._get_text(element, path)
        if text is None:
            return default
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    # --- Shared security extraction ---

    _ROLE_PERMISSION_MAP = {
        'readers': 'VIEW',
        'authors': 'EDIT',
        'administrators': 'ADMIN',
        'denyReaders': 'DENY_VIEW',
        'denyAuthors': 'DENY_EDIT',
        'denyAdministrators': 'DENY_ADMIN',
    }

    def _extract_role_map(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract security role assignments from roleMap element.

        Standardized extraction used by all parsers. Extracts users and
        groups for each role, maps known role names to permission types.

        Args:
            root: Root XML element (or any ancestor containing roleMap)

        Returns:
            List of role dicts with: role_name, permission_type,
            inherit, allow_for_all, users (list of UUIDs),
            groups (list of UUIDs)
        """
        roles = []
        role_map = root.find('.//roleMap')
        if role_map is None:
            return roles

        for role_elem in role_map.findall('role'):
            role_name = role_elem.get('name')
            if not role_name:
                continue

            users = []
            users_elem = role_elem.find('users')
            if users_elem is not None:
                for u in users_elem.findall('userUuid'):
                    if u.text:
                        users.append(u.text.strip())

            groups = []
            groups_elem = role_elem.find('groups')
            if groups_elem is not None:
                for g in groups_elem.findall('groupUuid'):
                    if g.text:
                        groups.append(g.text.strip())

            roles.append({
                'role_name': role_name,
                'permission_type': self._ROLE_PERMISSION_MAP.get(
                    role_name, role_name.upper()
                ),
                'inherit': role_elem.get('inherit') == 'true',
                'allow_for_all': role_elem.get('allowForAll') == 'true',
                'users': users,
                'groups': groups,
            })

        return roles
