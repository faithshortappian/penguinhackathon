"""
Parser for Appian Web API objects.

This module provides the WebAPIParser class for extracting data from
Web API XML files. Extracts all fields including SAIL expression,
HTTP configuration, security roles, and test requests.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class WebAPIParser(BaseParser):
    """
    Enhanced parser for Appian Web API objects.

    Extracts:
    - Core identification (uuid, name, version_uuid, description)
    - SAIL expression (the API definition code)
    - HTTP configuration (url_alias, http_method, request_body_type)
    - Settings (is_system, logging_enabled)
    - Security roles (administrator, viewer with users/groups)
    - Test request configuration (path, headers, body)
    """

    # XML namespace for Appian types
    APPIAN_NS = {'a': 'http://www.appian.com/ae/types/2009'}

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Web API XML file and extract all relevant data.

        Args:
            xml_path: Path to the Web API XML file

        Returns:
            Dict containing:
            - uuid: Web API UUID
            - name: Web API name
            - version_uuid: Version UUID
            - description: Web API description
            - sail_code: Cleaned SAIL code (from expression element)
            - url_alias: URL endpoint alias
            - http_method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            - request_body_type: Request body type (NONE, JSON, XML, etc.)
            - is_system: System flag
            - logging_enabled: Logging flag
            - security: List of security role configurations
            - test_requests: List of test request configurations
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = self.APPIAN_NS

        # Find the webApi element - try multiple patterns
        web_api_elem = self._find_web_api_element(root, ns)
        if web_api_elem is None:
            raise ValueError(f"No webApi element found in {xml_path}")

        # Extract basic info - UUID and name are attributes with namespace
        data = {
            'uuid': self._extract_uuid(web_api_elem, ns),
            'name': web_api_elem.get('name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_namespaced_text(web_api_elem, 'description', ns)
        }

        # Extract SAIL code from expression element (NOT definition)
        data['sail_code'] = self._extract_sail_code(web_api_elem, ns)

        # Extract HTTP configuration
        data['url_alias'] = self._get_namespaced_text(web_api_elem, 'urlAlias', ns)
        data['http_method'] = self._get_namespaced_text(web_api_elem, 'httpMethod', ns)
        data['request_body_type'] = self._get_namespaced_text(
            web_api_elem, 'requestBodyType', ns
        )

        # Extract settings
        data['is_system'] = self._get_namespaced_boolean(web_api_elem, 'system', ns)
        data['logging_enabled'] = self._get_namespaced_boolean(
            web_api_elem, 'loggingEnabled', ns
        )

        # Extract security roles
        data['security'] = self._extract_role_map(root)

        # Extract test requests
        data['test_requests'] = self._extract_test_requests(root, ns)

        return data

    def _find_web_api_element(
        self,
        root: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[ET.Element]:
        """
        Find the webApi element using multiple search patterns.

        Args:
            root: Root XML element
            ns: Namespace dictionary

        Returns:
            webApi element or None if not found
        """
        # Try with namespace prefix
        web_api_elem = root.find('.//webApi', ns)
        if web_api_elem is not None:
            return web_api_elem

        # Try with explicit namespace prefix
        web_api_elem = root.find('.//a:webApi', ns)
        if web_api_elem is not None:
            return web_api_elem

        # Try without namespace
        web_api_elem = root.find('.//webApi')
        if web_api_elem is not None:
            return web_api_elem

        # Try as direct child
        for child in root:
            tag = child.tag
            # Remove namespace prefix if present
            if '}' in tag:
                tag = tag.split('}')[1]
            if tag == 'webApi':
                return child

        return None

    def _extract_uuid(self, web_api_elem: ET.Element, ns: Dict[str, str]) -> Optional[str]:
        """
        Extract UUID from webApi element.

        The UUID can be in different attribute formats depending on the XML.

        Args:
            web_api_elem: webApi XML element
            ns: Namespace dictionary

        Returns:
            UUID string or None
        """
        # Try with full namespace URI
        uuid = web_api_elem.get('{http://www.appian.com/ae/types/2009}uuid')
        if uuid:
            return uuid

        # Try without namespace
        uuid = web_api_elem.get('uuid')
        if uuid:
            return uuid

        # Try a:uuid attribute
        uuid = web_api_elem.get(f'{{{ns["a"]}}}uuid')
        return uuid

    def _extract_sail_code(
        self,
        web_api_elem: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[str]:
        """
        Extract SAIL code from expression element.

        Web APIs store their SAIL code in the a:expression element,
        NOT in a definition element like interfaces.

        Args:
            web_api_elem: webApi XML element
            ns: Namespace dictionary

        Returns:
            Cleaned SAIL code or None
        """
        # Try with namespace prefix (most common)
        expression_elem = web_api_elem.find('a:expression', ns)

        if expression_elem is None:
            # Try with full namespace URI
            expression_elem = web_api_elem.find(
                f'{{{ns["a"]}}}expression'
            )

        if expression_elem is None:
            # Try without namespace
            expression_elem = web_api_elem.find('expression')

        if expression_elem is not None and expression_elem.text:
            return self._clean_sail_code(expression_elem.text)

        return None

    def _get_namespaced_text(
        self,
        element: ET.Element,
        tag: str,
        ns: Dict[str, str]
    ) -> Optional[str]:
        """
        Get text from element with namespace support.

        Tries multiple namespace patterns to find the element.

        Args:
            element: Parent XML element
            tag: Tag name without namespace prefix
            ns: Namespace dictionary

        Returns:
            Text content or None
        """
        # Try with namespace prefix
        elem = element.find(f'a:{tag}', ns)

        if elem is None:
            # Try with full namespace URI
            elem = element.find(f'{{{ns["a"]}}}{tag}')

        if elem is None:
            # Try without namespace
            elem = element.find(tag)

        return elem.text if elem is not None and elem.text else None

    def _get_namespaced_boolean(
        self,
        element: ET.Element,
        tag: str,
        ns: Dict[str, str],
        default: bool = False
    ) -> bool:
        """
        Get boolean value from element with namespace support.

        Args:
            element: Parent XML element
            tag: Tag name without namespace prefix
            ns: Namespace dictionary
            default: Default value if element not found

        Returns:
            Boolean value
        """
        text = self._get_namespaced_text(element, tag, ns)
        if text is None:
            return default
        return text.lower() in ('true', '1', 'yes')

    def _extract_test_requests(
        self,
        root: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract test request configurations from typedValue element.

        Web APIs can have test request configurations that include:
        - path: URL path parameters
        - headers: HTTP headers (name-value pairs)
        - body: Request body content

        Args:
            root: Root XML element
            ns: Namespace dictionary

        Returns:
            List of test request dictionaries with:
            - path: URL path
            - headers: List of header name-value pairs
            - body: Request body content
            - display_order: Order of the test request
        """
        test_requests = []

        # Find typedValue element containing WebApiRequest
        typed_value = root.find('.//typedValue')
        if typed_value is None:
            return test_requests

        # Check if this is a WebApiRequest list
        type_elem = typed_value.find('type/name')
        if type_elem is None or 'WebApiRequest' not in (type_elem.text or ''):
            return test_requests

        # Find the value element containing test request elements
        value_elem = typed_value.find('value')
        if value_elem is None:
            return test_requests

        # Find all test request elements (el)
        for idx, el in enumerate(value_elem.findall('el')):
            test_request = self._parse_test_request_element(el, idx, ns)
            if test_request:
                test_requests.append(test_request)

        return test_requests

    def _parse_test_request_element(
        self,
        el: ET.Element,
        display_order: int,
        ns: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Parse a single test request element.

        Args:
            el: Test request XML element (el)
            display_order: Order of this test request
            ns: Namespace dictionary

        Returns:
            Test request dictionary with path, headers, body, display_order
        """
        # Extract path - try multiple namespace patterns
        path = self._get_element_text_with_ns(el, 'path', ns)

        # Extract body
        body = self._get_element_text_with_ns(el, 'body', ns)

        # Extract headers
        headers = self._extract_headers(el, ns)

        return {
            'path': path,
            'headers': headers,
            'body': body,
            'display_order': display_order
        }

    def _get_element_text_with_ns(
        self,
        parent: ET.Element,
        tag: str,
        ns: Dict[str, str]
    ) -> Optional[str]:
        """
        Get element text trying multiple namespace patterns.

        Args:
            parent: Parent XML element
            tag: Tag name without namespace
            ns: Namespace dictionary

        Returns:
            Element text or None
        """
        # Try with full namespace URI
        elem = parent.find(f'{{{ns["a"]}}}{tag}')
        if elem is not None:
            return elem.text

        # Try with namespace prefix
        elem = parent.find(f'a:{tag}', ns)
        if elem is not None:
            return elem.text

        # Try without namespace
        elem = parent.find(tag)
        if elem is not None:
            return elem.text

        return None

    def _extract_headers(
        self,
        el: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract headers from a test request element.

        Headers are stored as a:headers elements with a:name and a:value children.

        Args:
            el: Test request XML element
            ns: Namespace dictionary

        Returns:
            List of header dictionaries with header_name, header_value, display_order
        """
        headers = []

        # Try with full namespace URI
        header_elements = el.findall(f'{{{ns["a"]}}}headers')

        # If not found, try with namespace prefix
        if not header_elements:
            header_elements = el.findall('a:headers', ns)

        # If still not found, try without namespace
        if not header_elements:
            header_elements = el.findall('headers')

        for idx, header_elem in enumerate(header_elements):
            header = self._parse_header_element(header_elem, idx, ns)
            if header:
                headers.append(header)

        return headers

    def _parse_header_element(
        self,
        header_elem: ET.Element,
        display_order: int,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a single header element.

        Args:
            header_elem: Header XML element (a:headers)
            display_order: Order of this header
            ns: Namespace dictionary

        Returns:
            Header dictionary with header_name, header_value, display_order
            or None if invalid
        """
        # Get header name
        header_name = self._get_element_text_with_ns(header_elem, 'name', ns)

        if not header_name:
            return None

        # Get header value
        header_value = self._get_element_text_with_ns(header_elem, 'value', ns)

        return {
            'header_name': header_name,
            'header_value': header_value,
            'display_order': display_order
        }
