"""
Parser for unrecognized Appian object types.

This module provides the UnknownObjectParser class for handling objects
that don't have a dedicated parser.
"""

from typing import Dict, Any
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class UnknownObjectParser(BaseParser):
    """
    Parser for unrecognized object types.

    This parser extracts only basic information and stores the raw XML
    for objects that don't have a dedicated parser.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse unknown object type.

        Args:
            xml_path: Path to the XML file

        Returns:
            Dict with basic object information and raw XML
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Try to extract basic info from root or first child
        data = {}

        # Strategy 1: Try to find any element with both uuid and name attributes
        for elem in root.iter():
            if elem.get('uuid') and elem.get('name'):
                data = self._extract_basic_info(elem)
                break

        # Strategy 2: If no element has both, look for uuid attribute anywhere
        # and try to find name separately
        if not data or not data.get('uuid'):
            uuid_value = None
            name_value = None
            version_uuid_value = None
            description_value = None

            for elem in root.iter():
                # Capture first uuid found
                if not uuid_value and elem.get('uuid'):
                    uuid_value = elem.get('uuid')
                    version_uuid_value = elem.get('versionUuid')
                    # Also check if name is an attribute on this element
                    if elem.get('name'):
                        name_value = elem.get('name')
                    # Or check for name as a child element
                    name_elem = elem.find('name')
                    if name_elem is not None and name_elem.text:
                        name_value = name_elem.text
                    # Check for description
                    desc_elem = elem.find('description')
                    if desc_elem is not None and desc_elem.text:
                        description_value = desc_elem.text

                # If we found uuid, also look for name in child elements
                if uuid_value and not name_value:
                    name_elem = elem.find('name')
                    if name_elem is not None and name_elem.text:
                        name_value = name_elem.text

                if uuid_value:
                    break

            if uuid_value:
                data = {
                    'uuid': uuid_value,
                    'name': name_value,
                    'version_uuid': version_uuid_value,
                    'description': description_value
                }

        # If no basic info found, create minimal data
        if not data:
            data = {
                'uuid': None,
                'name': None,
                'version_uuid': None,
                'description': None
            }

        # Store raw XML for unknown objects
        with open(xml_path, 'r', encoding='utf-8') as f:
            data['raw_xml'] = f.read()

        return data
