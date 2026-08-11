"""
Parser for Appian Connected System objects.

This module provides the ConnectedSystemParser class for extracting data from
Connected System XML files.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class ConnectedSystemParser(BaseParser):
    """
    Parser for Appian Connected System objects.

    Extracts URL configuration, authentication details, and security settings
    from Connected System XML files.
    """

    # XML namespaces used in Connected System files
    NAMESPACES = {
        'a': 'http://www.appian.com/ae/types/2009',
        'xsd': 'http://www.w3.org/2001/XMLSchema',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Connected System XML file and extract all relevant data.

        Args:
            xml_path: Path to the Connected System XML file

        Returns:
            Dict containing:
            - uuid: Connected System UUID
            - name: Connected System name
            - version_uuid: Version UUID
            - description: Connected System description
            - integration_type: Type of integration (e.g., system.http)
            - url: URL configuration
            - base_url: Base URL for the connected system
            - is_inherited_url: Whether URL is inherited
            - auth_type: Authentication type (e.g., API Key, Basic Auth)
            - auth_details: List of auth detail key-value pairs
            - security: List of security role assignments
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the connectedSystem element
        connected_system_elem = root.find('.//connectedSystem')
        if connected_system_elem is None:
            raise ValueError(f"No connectedSystem element found in {xml_path}")

        # Extract basic info
        data = {
            'uuid': self._get_text(connected_system_elem, 'uuid'),
            'name': self._get_text(connected_system_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(connected_system_elem, 'description')
        }

        # Extract integration type
        data['integration_type'] = self._get_text(connected_system_elem, 'integrationType')

        # Extract shared config parameters (URL, auth, etc.)
        self._extract_shared_config(connected_system_elem, data)

        # Extract security settings from roleMap
        data['security'] = self._extract_role_map(root)

        return data

    def _extract_shared_config(self, connected_system_elem: ET.Element, data: Dict[str, Any]) -> None:
        """
        Extract shared configuration parameters including URL and auth details.

        Args:
            connected_system_elem: Connected System XML element
            data: Dictionary to populate with extracted data
        """
        # Initialize defaults
        data['url'] = None
        data['base_url'] = None
        data['is_inherited_url'] = False
        data['auth_type'] = None
        data['auth_details'] = []

        # Find sharedConfigParameters element
        shared_config = connected_system_elem.find('sharedConfigParameters')
        if shared_config is None:
            return

        # Find the Dictionary element (may have namespace prefix)
        dict_elem = shared_config.find('a:Dictionary', self.NAMESPACES)
        if dict_elem is None:
            # Try without namespace
            dict_elem = shared_config.find('.//Dictionary')
        if dict_elem is None:
            # Try direct children
            for child in shared_config:
                if 'Dictionary' in child.tag:
                    dict_elem = child
                    break

        if dict_elem is None:
            return

        # Extract URL configuration
        data['url'] = self._get_element_text(dict_elem, 'url')
        data['base_url'] = self._get_element_text(dict_elem, 'baseUrl')

        # Extract inherited URL flag
        inherited_url_elem = self._find_element(dict_elem, 'isInheritedUrlOptionSelected')
        if inherited_url_elem is not None and inherited_url_elem.text:
            data['is_inherited_url'] = inherited_url_elem.text.lower() == 'true'

        # Extract auth type
        data['auth_type'] = self._get_element_text(dict_elem, 'authType')

        # Extract auth details
        data['auth_details'] = self._extract_auth_details(dict_elem)

    def _extract_auth_details(self, dict_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract authentication details from the authDetails Dictionary element.

        Args:
            dict_elem: The parent Dictionary element containing authDetails

        Returns:
            List of auth detail dictionaries with key, value, value_type
        """
        auth_details = []

        # Find authDetails element
        auth_details_elem = self._find_element(dict_elem, 'authDetails')
        if auth_details_elem is None:
            return auth_details

        # Process all child elements as key-value pairs
        display_order = 0
        for child in auth_details_elem:
            # Get the tag name (remove namespace if present)
            tag = child.tag
            if '}' in tag:
                tag = tag.split('}')[1]

            # Get the value type from xsi:type attribute
            value_type = self._get_xsi_type(child)

            # Get the value
            value = child.text.strip() if child.text else None

            # Handle encrypted values (they're typically empty)
            if value_type and 'EncryptedText' in value_type:
                value = '[ENCRYPTED]'

            auth_details.append({
                'key': tag,
                'value': value,
                'value_type': value_type,
                'display_order': display_order
            })
            display_order += 1

        return auth_details

    def _find_element(self, parent: ET.Element, tag_name: str) -> Optional[ET.Element]:
        """
        Find an element by tag name, handling namespaces.

        Args:
            parent: Parent element to search in
            tag_name: Tag name to find (without namespace)

        Returns:
            Found element or None
        """
        # Try with namespace
        for ns_prefix, ns_uri in self.NAMESPACES.items():
            elem = parent.find(f'{{{ns_uri}}}{tag_name}')
            if elem is not None:
                return elem

        # Try without namespace
        elem = parent.find(tag_name)
        if elem is not None:
            return elem

        # Try searching all children
        for child in parent:
            child_tag = child.tag
            if '}' in child_tag:
                child_tag = child_tag.split('}')[1]
            if child_tag == tag_name:
                return child

        return None

    def _get_element_text(self, parent: ET.Element, tag_name: str) -> Optional[str]:
        """
        Get text content of an element by tag name.

        Args:
            parent: Parent element to search in
            tag_name: Tag name to find

        Returns:
            Text content or None
        """
        elem = self._find_element(parent, tag_name)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    def _get_xsi_type(self, element: ET.Element) -> Optional[str]:
        """
        Get the xsi:type attribute value from an element.

        Args:
            element: XML element

        Returns:
            Type value (without namespace prefix) or None
        """
        xsi_ns = '{http://www.w3.org/2001/XMLSchema-instance}'
        type_attr = element.get(f'{xsi_ns}type')

        if type_attr:
            # Remove namespace prefix if present (e.g., "xsd:string" -> "string")
            if ':' in type_attr:
                return type_attr.split(':')[1]
            return type_attr

        return None
