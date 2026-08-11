"""
Parser for Appian Interface objects.

This module provides the InterfaceParser class for extracting data from
Interface XML files.

Note: Parameter types are stored as raw values during parsing. Type resolution
to user-friendly display names is performed in post-extraction processing
when the record type cache is available.
"""

from typing import Dict, Any, List
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class InterfaceParser(BaseParser):
    """
    Parser for Appian Interface objects.

    Extracts SAIL code, parameters, and security settings from Interface XML files.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Interface XML file and extract all relevant data.

        Args:
            xml_path: Path to the Interface XML file

        Returns:
            Dict containing:
            - uuid: Interface UUID
            - name: Interface name
            - version_uuid: Version UUID
            - description: Interface description
            - sail_code: Cleaned SAIL code
            - parameters: List of parameter definitions
            - security: List of security role assignments
            - test_inputs: List of default input values
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the interface element
        interface_elem = root.find('.//interface')
        if interface_elem is None:
            raise ValueError(f"No interface element found in {xml_path}")

        # Extract basic info - UUID and name are child elements, not attributes
        data = {
            'uuid': self._get_text(interface_elem, 'uuid'),
            'name': self._get_text(interface_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(interface_elem, 'description')
        }

        # Extract SAIL code from definition element
        definition_elem = interface_elem.find('definition')
        if definition_elem is not None and definition_elem.text:
            data['sail_code'] = self._clean_sail_code(definition_elem.text)
        else:
            data['sail_code'] = None

        # Extract parameters
        data['parameters'] = self._extract_parameters(interface_elem)

        # Extract security settings
        data['security'] = self._extract_role_map(root)

        # Extract test inputs (default values for parameters)
        data['test_inputs'] = self._extract_test_inputs(root)

        return data

    def _extract_parameters(self, interface_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract parameter definitions from interface element.

        Args:
            interface_elem: Interface XML element

        Returns:
            List of parameter dictionaries with name, type, required, default_value
        """
        parameters = []

        for param_elem in interface_elem.findall('.//namedTypedValue'):
            name_elem = param_elem.find('name')
            type_elem = param_elem.find('type')

            if name_elem is not None and name_elem.text:
                param = {
                    'name': name_elem.text,
                    'type': None,
                    'raw_type': None,  # Keep original for debugging
                    'required': False,  # Default, Appian doesn't explicitly mark this
                    'default_value': None,
                    'description': None,
                    'display_order': len(parameters)
                }

                # Extract description
                desc_elem = param_elem.find('description')
                if desc_elem is not None and desc_elem.text:
                    param['description'] = desc_elem.text

                # Extract type information
                if type_elem is not None:
                    type_name_elem = type_elem.find('name')
                    type_namespace_elem = type_elem.find('namespace')

                    if type_name_elem is not None and type_name_elem.text:
                        raw_type = type_name_elem.text

                        # Build full raw type with namespace
                        if type_namespace_elem is not None and type_namespace_elem.text:
                            raw_type = f"{type_namespace_elem.text}:{raw_type}"

                        # Store raw type - will be resolved in post-extraction
                        # with record type cache
                        param['raw_type'] = raw_type
                        param['type'] = raw_type

                parameters.append(param)

        return parameters

    def _extract_test_inputs(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract test input configurations (default values) from typedValue element.

        Interfaces have a single set of default values for their parameters,
        stored in the typedValue element containing RuleTestConfig.

        Args:
            root: Root XML element

        Returns:
            List of test input dictionaries with input_name_ref, input_value, value_type, is_null
        """
        test_inputs = []

        # Find typedValue element containing RuleTestConfig
        typed_value = root.find('.//typedValue')
        if typed_value is None:
            return test_inputs

        # Check if this is a RuleTestConfig list
        type_elem = typed_value.find('type/name')
        if type_elem is None or 'RuleTestConfig' not in (type_elem.text or ''):
            return test_inputs

        # Find the value element containing test configurations
        value_elem = typed_value.find('value')
        if value_elem is None:
            return test_inputs

        # Interfaces typically have a single test case (el element)
        el = value_elem.find('el')
        if el is None:
            return test_inputs

        # Extract test inputs from ruleInputTestConfigs
        ns = '{http://www.appian.com/ae/types/2009}'

        for input_config in el.findall(f'{ns}ruleInputTestConfigs'):
            test_input = self._parse_test_input(input_config, len(test_inputs))
            if test_input:
                test_inputs.append(test_input)

        return test_inputs

    def _parse_test_input(self, input_config: ET.Element, input_order: int) -> Dict[str, Any]:
        """
        Parse a test input configuration element.

        Args:
            input_config: The ruleInputTestConfigs XML element
            input_order: Default order if not specified in XML

        Returns:
            Dictionary with input_name_ref, input_value, value_type, is_null, input_order
        """
        ns = '{http://www.appian.com/ae/types/2009}'
        xsi_ns = '{http://www.w3.org/2001/XMLSchema-instance}'

        # Get input name reference
        name_ref_elem = input_config.find(f'{ns}nameRef')
        input_name_ref = name_ref_elem.text if name_ref_elem is not None else ''

        # Get input ID (order)
        id_elem = input_config.find(f'{ns}id')
        if id_elem is not None and id_elem.text:
            try:
                input_order = int(id_elem.text) - 1  # Convert to 0-based
            except ValueError:
                pass

        # Get value element
        value_elem = input_config.find(f'{ns}value')
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
                    # Extract type from qualified name (e.g., "a:Expression" -> "Expression")
                    value_type = type_attr.split(':')[1] if ':' in type_attr else type_attr
                input_value = value_elem.text.strip() if value_elem.text else None

        return {
            'input_name_ref': input_name_ref,
            'input_value': input_value,
            'value_type': value_type,
            'is_null': is_null,
            'input_order': input_order
        }
