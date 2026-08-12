"""
Parser for Appian Expression Rule objects.

This module provides the ExpressionRuleParser class for extracting data from
Expression Rule XML files.

Note: Input/output types are stored as raw values during parsing. Type resolution
to user-friendly display names is performed in post-extraction processing
when the record type cache is available.
"""

from typing import Dict, Any, List
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class ExpressionRuleParser(BaseParser):
    """
    Parser for Appian Expression Rule objects.

    Extracts SAIL code, inputs, output type, security settings, and test cases
    from Expression Rule XML files.
    """

    # XML namespace for Appian types
    APPIAN_NS = {'a': 'http://www.appian.com/ae/types/2009'}

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Expression Rule XML file and extract all relevant data.

        Args:
            xml_path: Path to the Expression Rule XML file

        Returns:
            Dict containing:
            - uuid: Expression Rule UUID
            - name: Expression Rule name
            - version_uuid: Version UUID
            - description: Expression Rule description
            - sail_code: Cleaned SAIL code (from definition element)
            - inputs: List of input parameter definitions
            - output_type: Output type definition
            - return_type: Alias for output_type (for compatibility)
            - definition: Raw definition text (for compatibility)
            - security: List of security role assignments
            - test_cases: List of test case configurations
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the rule element
        rule_elem = root.find('.//rule')
        if rule_elem is None:
            raise ValueError(f"No rule element found in {xml_path}")

        # Extract basic info
        data = {
            'uuid': self._get_text(rule_elem, 'uuid'),
            'name': self._get_text(rule_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(rule_elem, 'description')
        }

        # Extract SAIL code from definition element
        definition_elem = rule_elem.find('definition')
        if definition_elem is not None and definition_elem.text:
            data['sail_code'] = self._clean_sail_code(definition_elem.text)
            data['definition'] = definition_elem.text
        else:
            data['sail_code'] = None
            data['definition'] = None

        # Extract input parameters
        data['inputs'] = self._extract_inputs(rule_elem)

        # Extract output type (if specified)
        output_type = self._extract_output_type(rule_elem)
        data['output_type'] = output_type
        data['return_type'] = output_type

        # Extract security settings
        data['security'] = self._extract_role_map(root)

        # Extract test cases
        data['test_cases'] = self._extract_test_cases(root)

        return data

    def _extract_inputs(self, rule_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract input parameter definitions from rule element.

        Args:
            rule_elem: Rule XML element

        Returns:
            List of input parameter dictionaries with resolved type names
        """
        inputs = []

        for param_elem in rule_elem.findall('.//namedTypedValue'):
            name_elem = param_elem.find('name')
            type_elem = param_elem.find('type')

            if name_elem is not None and name_elem.text:
                input_param = {
                    'name': name_elem.text,
                    'type': None,
                    'data_type': None,
                    'raw_type': None,  # Keep original for debugging
                    'required': False,
                    'description': None,
                    'default_value': None,
                    'display_order': len(inputs)
                }

                if type_elem is not None:
                    type_name_elem = type_elem.find('name')
                    type_namespace_elem = type_elem.find('namespace')

                    if type_name_elem is not None and type_name_elem.text:
                        raw_type = type_name_elem.text

                        if (type_namespace_elem is not None and
                                type_namespace_elem.text):
                            ns = type_namespace_elem.text
                            raw_type = f"{ns}:{raw_type}"

                        # Store raw type - will be resolved in post-extraction
                        # with record type cache
                        input_param['raw_type'] = raw_type
                        input_param['type'] = raw_type
                        input_param['data_type'] = raw_type

                desc_elem = param_elem.find('description')
                if desc_elem is not None and desc_elem.text:
                    input_param['description'] = desc_elem.text

                inputs.append(input_param)

        return inputs

    def _extract_output_type(self, rule_elem: ET.Element) -> str:
        """
        Extract output type from rule element.

        Args:
            rule_elem: Rule XML element

        Returns:
            Raw output type string, or None if not specified.
            Type resolution is performed in post-extraction with record type cache.
        """
        output_type_elem = rule_elem.find('.//outputType')
        if output_type_elem is not None:
            type_name = output_type_elem.find('name')
            type_namespace = output_type_elem.find('namespace')

            if type_name is not None and type_name.text:
                raw_type = type_name.text
                if type_namespace is not None and type_namespace.text:
                    raw_type = f"{type_namespace.text}:{raw_type}"
                # Return raw type - will be resolved in post-extraction
                return raw_type

        return None

    def _extract_test_cases(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract test case configurations from typedValue element.

        Args:
            root: Root XML element

        Returns:
            List of test case dictionaries with:
            - test_name: Name of the test case
            - display_order: Order of the test case
            - test_inputs: List of input configurations
            - assertions: List of assertion configurations
        """
        test_cases = []

        # Find typedValue element containing RuleTestConfig
        typed_value = root.find('.//typedValue')
        if typed_value is None:
            return test_cases

        # Check if this is a RuleTestConfig list
        type_elem = typed_value.find('type/name')
        if type_elem is None or 'RuleTestConfig' not in (type_elem.text or ''):
            return test_cases

        # Find all test case elements (el)
        value_elem = typed_value.find('value')
        if value_elem is None:
            return test_cases

        for idx, el in enumerate(value_elem.findall('el')):
            test_case = self._parse_test_case_element(el, idx)
            if test_case:
                test_cases.append(test_case)

        return test_cases

    def _parse_test_case_element(
        self,
        el: ET.Element,
        display_order: int
    ) -> Dict[str, Any]:
        """
        Parse a single test case element.

        Args:
            el: Test case XML element
            display_order: Order of this test case

        Returns:
            Test case dictionary
        """
        # Extract test name (with namespace)
        name_elem = el.find('{http://www.appian.com/ae/types/2009}name')
        test_name = name_elem.text if name_elem is not None else None

        # Extract test inputs
        test_inputs = []
        for input_config in el.findall(
            '{http://www.appian.com/ae/types/2009}ruleInputTestConfigs'
        ):
            test_input = self._parse_test_input(input_config, len(test_inputs))
            if test_input:
                test_inputs.append(test_input)

        # Extract assertions
        assertions = []
        assertions_elem = el.find(
            '{http://www.appian.com/ae/types/2009}assertions'
        )
        if assertions_elem is not None:
            assertion = self._parse_assertion(assertions_elem, 0)
            if assertion:
                assertions.append(assertion)

        return {
            'test_name': test_name or f'Test Case {display_order + 1}',
            'display_order': display_order,
            'test_inputs': test_inputs,
            'assertions': assertions
        }

    def _parse_test_input(
        self,
        input_config: ET.Element,
        input_order: int
    ) -> Dict[str, Any]:
        """
        Parse a test input configuration element.

        Args:
            input_config: Test input XML element
            input_order: Order of this input

        Returns:
            Test input dictionary
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
            # Check for nil attribute
            nil_attr = value_elem.get(f'{xsi_ns}nil')
            if nil_attr == 'true':
                is_null = True
                value_type = 'nil'
            else:
                # Get value type from xsi:type attribute
                type_attr = value_elem.get(f'{xsi_ns}type')
                if type_attr:
                    # Extract type name (e.g., "a:Expression" -> "Expression")
                    if ':' in type_attr:
                        value_type = type_attr.split(':')[1]
                    else:
                        value_type = type_attr

                # Get the actual value
                input_value = value_elem.text
                if input_value:
                    input_value = input_value.strip()

        return {
            'input_name_ref': input_name_ref,
            'input_value': input_value,
            'value_type': value_type,
            'is_null': is_null,
            'input_order': input_order
        }

    def _parse_assertion(
        self,
        assertion_elem: ET.Element,
        display_order: int
    ) -> Dict[str, Any]:
        """
        Parse an assertion element.

        Args:
            assertion_elem: Assertion XML element
            display_order: Order of this assertion

        Returns:
            Assertion dictionary
        """
        xsi_ns = '{http://www.w3.org/2001/XMLSchema-instance}'

        # Check for nil attribute
        nil_attr = assertion_elem.get(f'{xsi_ns}nil')
        if nil_attr == 'true':
            return {
                'assertion_value': None,
                'is_null': True,
                'display_order': display_order
            }

        # Get assertion value
        assertion_value = assertion_elem.text
        if assertion_value:
            assertion_value = assertion_value.strip()

        return {
            'assertion_value': assertion_value,
            'is_null': False,
            'display_order': display_order
        }
