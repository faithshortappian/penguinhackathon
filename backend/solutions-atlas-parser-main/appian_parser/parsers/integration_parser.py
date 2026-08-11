"""
Parser for Appian Integration objects.

This module provides the IntegrationParser class for extracting data from
Integration XML files with full normalization of all configuration parameters.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class IntegrationParser(BaseParser):
    """
    Parser for Appian Integration objects.

    Extracts rule inputs, shared config parameters, config parameters,
    headers, query parameters, test inputs, and security settings.
    """

    # XML namespaces used in integration files
    NS = {
        'a': 'http://www.appian.com/ae/types/2009',
        'xsd': 'http://www.w3.org/2001/XMLSchema',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Integration XML file and extract all relevant data.

        Args:
            xml_path: Path to the Integration XML file

        Returns:
            Dict containing all normalized integration data
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the integration element (could be outboundIntegration or integration)
        integration_elem = root.find('.//outboundIntegration')
        if integration_elem is None:
            integration_elem = root.find('.//integration')
        if integration_elem is None:
            raise ValueError(f"No integration element found in {xml_path}")

        # Extract basic info
        data = {
            'uuid': self._get_text(integration_elem, 'uuid'),
            'name': self._get_text(integration_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(integration_elem, 'description'),
            'integration_type': self._get_text(integration_elem, 'integrationType'),
            'connected_system_uuid': self._get_text(integration_elem, 'connectedSystemUuid'),
            'is_write': self._get_boolean(integration_elem, 'isWrite', False),
        }

        # Extract rule inputs (namedTypedValue elements)
        data['rule_inputs'] = self._extract_rule_inputs(integration_elem)

        # Extract shared config parameters (URL, auth, etc.)
        shared_config = self._extract_shared_config(integration_elem)
        data.update(shared_config)

        # Extract config parameters (method, headers, query params, body, etc.)
        config_params = self._extract_config_parameters(integration_elem)
        data.update(config_params)

        # Extract security settings
        data['security'] = self._extract_role_map(root)

        # Extract test inputs
        data['test_inputs'] = self._extract_test_inputs(root)

        return data

    def _extract_rule_inputs(self, integration_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract rule inputs (parameters) from namedTypedValue elements.

        Args:
            integration_elem: Integration XML element

        Returns:
            List of rule input dictionaries
        """
        rule_inputs = []

        for idx, ntv in enumerate(integration_elem.findall('namedTypedValue')):
            name_elem = ntv.find('name')
            type_elem = ntv.find('type')

            if name_elem is not None and name_elem.text:
                rule_input = {
                    'input_name': name_elem.text,
                    'input_type': None,
                    'type_namespace': None,
                    'display_order': idx
                }

                if type_elem is not None:
                    type_name = type_elem.find('name')
                    type_ns = type_elem.find('namespace')

                    if type_name is not None:
                        rule_input['input_type'] = type_name.text
                    if type_ns is not None:
                        rule_input['type_namespace'] = type_ns.text

                rule_inputs.append(rule_input)

        return rule_inputs

    def _extract_shared_config(self, integration_elem: ET.Element) -> Dict[str, Any]:
        """
        Extract shared configuration parameters (URL, auth settings).

        Args:
            integration_elem: Integration XML element

        Returns:
            Dict with shared config fields
        """
        result = {
            'url': None,
            'url_is_expression': False,
            'relative_path': None,
            'is_inherited_url': False,
            'auth_type': None,
            'auth_details': None,
        }

        shared_config = integration_elem.find('sharedConfigParameters')
        if shared_config is None:
            return result

        # Find the Dictionary element (with namespace)
        dict_elem = shared_config.find('a:Dictionary', self.NS)
        if dict_elem is None:
            # Try without namespace
            dict_elem = shared_config.find('.//{http://www.appian.com/ae/types/2009}Dictionary')
        if dict_elem is None:
            # Try direct children
            dict_elem = shared_config

        # Extract URL - check if it's an expression
        url_elem = dict_elem.find('url')
        if url_elem is not None:
            xsi_type = url_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
            if 'Expression' in xsi_type:
                result['url'] = self._clean_sail_code(url_elem.text) if url_elem.text else None
                result['url_is_expression'] = True
            else:
                result['url'] = url_elem.text

        # Extract other shared config fields
        result['is_inherited_url'] = self._get_dict_boolean(dict_elem, 'isInheritedUrlOptionSelected')
        result['relative_path'] = self._get_dict_text(dict_elem, 'relativePath')
        result['auth_type'] = self._get_dict_text(dict_elem, 'authType')
        result['auth_details'] = self._get_dict_text(dict_elem, 'authDetails')

        return result

    def _extract_config_parameters(self, integration_elem: ET.Element) -> Dict[str, Any]:
        """
        Extract configuration parameters (method, headers, query params, body).

        Args:
            integration_elem: Integration XML element

        Returns:
            Dict with config fields and nested lists for headers/params
        """
        result = {
            'http_method': None,
            'content_type': None,
            'body_parse_type': None,
            'timeout': None,
            'automatically_convert': True,
            'exclude_null_params': True,
            'exclude_null_headers': True,
            'remove_null_json_fields': True,
            'request_body': None,
            'request_body_is_expression': False,
            'query_parameters': [],
            'headers': [],
        }

        config_params = integration_elem.find('configParameters')
        if config_params is None:
            return result

        # Find the Dictionary element
        dict_elem = config_params.find('a:Dictionary', self.NS)
        if dict_elem is None:
            dict_elem = config_params.find('.//{http://www.appian.com/ae/types/2009}Dictionary')
        if dict_elem is None:
            dict_elem = config_params

        # Extract scalar config values
        result['http_method'] = self._get_dict_text(dict_elem, 'method')
        result['content_type'] = self._get_dict_text(dict_elem, 'contentType')
        result['body_parse_type'] = self._get_dict_text(dict_elem, 'bodyParseType')
        result['timeout'] = self._get_dict_int(dict_elem, 'timeout')
        result['automatically_convert'] = self._get_dict_boolean(dict_elem, 'automaticallyConvert', True)
        result['exclude_null_params'] = self._get_dict_boolean(dict_elem, 'excludeNullParams', True)
        result['exclude_null_headers'] = self._get_dict_boolean(dict_elem, 'excludeNullHeaders', True)
        result['remove_null_json_fields'] = self._get_dict_boolean(dict_elem, 'removeNullOrEmptyJsonFields', True)

        # Extract request body
        body_elem = dict_elem.find('body')
        if body_elem is not None:
            xsi_type = body_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
            if 'Expression' in xsi_type:
                result['request_body'] = self._clean_sail_code(body_elem.text) if body_elem.text else None
                result['request_body_is_expression'] = True
            else:
                result['request_body'] = body_elem.text

        # Extract query parameters
        result['query_parameters'] = self._extract_name_value_list(dict_elem, 'parameters')

        # Extract headers
        result['headers'] = self._extract_name_value_list(dict_elem, 'headers')

        return result

    def _extract_name_value_list(self, dict_elem: ET.Element, list_name: str) -> List[Dict[str, Any]]:
        """
        Extract a list of name-value pairs (used for parameters and headers).

        Args:
            dict_elem: Dictionary XML element
            list_name: Name of the list element (e.g., 'parameters', 'headers')

        Returns:
            List of dicts with name, value, is_expression, display_order
        """
        items = []

        list_elem = dict_elem.find(list_name)
        if list_elem is None:
            return items

        for idx, item in enumerate(list_elem.findall('item')):
            name_elem = item.find('{http://www.appian.com/ae/types/2009}name')
            if name_elem is None:
                name_elem = item.find('a:name', self.NS)

            value_elem = item.find('{http://www.appian.com/ae/types/2009}value')
            if value_elem is None:
                value_elem = item.find('a:value', self.NS)

            if name_elem is not None and name_elem.text:
                item_data = {
                    'name': name_elem.text,
                    'value': None,
                    'is_expression': False,
                    'display_order': idx
                }

                if value_elem is not None:
                    xsi_type = value_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
                    if 'Expression' in xsi_type:
                        item_data['value'] = self._clean_sail_code(value_elem.text) if value_elem.text else None
                        item_data['is_expression'] = True
                    else:
                        item_data['value'] = value_elem.text

                items.append(item_data)

        return items

    def _extract_test_inputs(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract test input configurations from typedValue element.

        Args:
            root: Root XML element

        Returns:
            List of test input dictionaries
        """
        test_inputs = []

        typed_value = root.find('.//typedValue')
        if typed_value is None:
            return test_inputs

        type_elem = typed_value.find('type/name')
        if type_elem is None or 'RuleTestConfig' not in (type_elem.text or ''):
            return test_inputs

        value_elem = typed_value.find('value')
        if value_elem is None:
            return test_inputs

        el = value_elem.find('el')
        if el is None:
            return test_inputs

        ns = '{http://www.appian.com/ae/types/2009}'
        xsi_ns = '{http://www.w3.org/2001/XMLSchema-instance}'

        for idx, input_config in enumerate(el.findall(f'{ns}ruleInputTestConfigs')):
            name_ref_elem = input_config.find(f'{ns}nameRef')
            value_elem = input_config.find(f'{ns}value')
            id_elem = input_config.find(f'{ns}id')

            # Skip if no valid input_name_ref (required field)
            input_name_ref = None
            if name_ref_elem is not None and name_ref_elem.text:
                input_name_ref = name_ref_elem.text.strip()

            if not input_name_ref:
                continue  # Skip test inputs without a name reference

            input_order = idx
            if id_elem is not None and id_elem.text:
                try:
                    input_order = int(id_elem.text) - 1
                except ValueError:
                    pass

            input_value = None
            value_type = None
            is_null = False

            if value_elem is not None:
                nil_attr = value_elem.get(f'{xsi_ns}nil')
                if nil_attr == 'true':
                    is_null = True
                    value_type = 'nil'
                else:
                    type_attr = value_elem.get(f'{xsi_ns}type')
                    if type_attr:
                        value_type = type_attr.split(':')[1] if ':' in type_attr else type_attr
                    input_value = value_elem.text.strip() if value_elem.text else None

            test_inputs.append({
                'input_name_ref': input_name_ref,
                'input_value': input_value,
                'value_type': value_type,
                'is_null': is_null,
                'input_order': input_order
            })

        return test_inputs

    def _get_dict_text(self, dict_elem: ET.Element, field_name: str) -> Optional[str]:
        """Get text value from a dictionary element field."""
        elem = dict_elem.find(field_name)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    def _get_dict_boolean(self, dict_elem: ET.Element, field_name: str, default: bool = False) -> bool:
        """Get boolean value from a dictionary element field."""
        elem = dict_elem.find(field_name)
        if elem is not None and elem.text:
            return elem.text.lower() == 'true'
        return default

    def _get_dict_int(self, dict_elem: ET.Element, field_name: str, default: int = None) -> Optional[int]:
        """Get integer value from a dictionary element field."""
        elem = dict_elem.find(field_name)
        if elem is not None and elem.text:
            try:
                return int(elem.text)
            except ValueError:
                pass
        return default
