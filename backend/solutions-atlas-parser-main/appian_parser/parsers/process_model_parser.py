"""
Parser for Appian Process Model objects.

This module provides the ProcessModelParser class for extracting data from
Process Model XML files.

Enhanced to extract:
- Human-readable node type names and categories from the node type registry
- Gateway conditions for XOR/OR gateways
- Form expressions for User Input Tasks
- Pre-trigger rules for Timer/Rule events
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser
from appian_parser.domain.node_types import get_node_type_info


class ProcessModelParser(BaseParser):
    """
    Parser for Appian Process Model objects.

    Extracts nodes, flows, variables, and calculates complexity from Process Model XML files.
    """

    def _extract_localized_string(
        self,
        string_map_elem: ET.Element,
        ns: Dict[str, str],
        preferred_locale: str = 'en_US'
    ) -> str | None:
        """
        Extract a string value from a string-map element, handling multiple locales.

        Prioritizes en_US locale, then falls back to first non-empty value.

        Args:
            string_map_elem: The string-map XML element
            ns: Namespace dictionary for XML parsing
            preferred_locale: Preferred locale in format 'lang_COUNTRY' (default: 'en_US')

        Returns:
            The extracted string value, or None if not found
        """
        if string_map_elem is None:
            return None

        pairs = string_map_elem.findall('a:pair', ns)
        if not pairs:
            # Try without namespace (some elements aren't namespaced)
            pairs = string_map_elem.findall('pair')

        preferred_lang, preferred_country = preferred_locale.split('_')
        preferred_value = None
        fallback_value = None

        for pair in pairs:
            # Try namespaced first, then non-namespaced
            locale_elem = pair.find('a:locale', ns)
            if locale_elem is None:
                locale_elem = pair.find('locale')

            value_elem = pair.find('a:value', ns)
            if value_elem is None:
                value_elem = pair.find('value')

            if value_elem is None or not value_elem.text:
                continue

            value_text = value_elem.text.strip() if value_elem.text else None
            if not value_text:
                continue

            # Check if this is the preferred locale
            if locale_elem is not None:
                lang = locale_elem.get('lang', '')
                country = locale_elem.get('country', '')
                if lang == preferred_lang and country == preferred_country:
                    preferred_value = value_text
                    break  # Found preferred locale, no need to continue

            # Store as fallback if we haven't found one yet
            if fallback_value is None:
                fallback_value = value_text

        return preferred_value or fallback_value

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Process Model XML file and extract all relevant data.

        Args:
            xml_path: Path to the Process Model XML file

        Returns:
            Dict containing:
            - uuid: Process Model UUID
            - name: Process Model name
            - version_uuid: Version UUID
            - description: Process Model description
            - nodes: List of node definitions
            - flows: List of flow/connection definitions
            - variables: List of process variable definitions
            - total_nodes: Count of nodes
            - total_flows: Count of flows
            - complexity_score: Calculated complexity metric
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the process model element
        pm_elem = root.find('.//{http://www.appian.com/ae/types/2009}pm')
        if pm_elem is None:
            raise ValueError(f"No process model element found in {xml_path}")

        # Extract basic info from meta element
        meta_elem = pm_elem.find('.//{http://www.appian.com/ae/types/2009}meta')
        if meta_elem is None:
            raise ValueError(f"No meta element found in {xml_path}")

        data = self._extract_basic_info_from_meta(meta_elem)

        # Extract version UUID from root level
        version_uuid_elem = root.find('.//versionUuid')
        if version_uuid_elem is not None and version_uuid_elem.text:
            data['version_uuid'] = version_uuid_elem.text

        # Extract nodes
        data['nodes'] = self._extract_nodes(pm_elem)

        # Extract flows/connections
        data['flows'] = self._extract_flows(pm_elem)

        # Extract process variables
        data['variables'] = self._extract_variables(pm_elem)

        # Extract PM-level start form (configured on the process, not on a node)
        start_form = self._extract_start_form(pm_elem)
        if start_form:
            data['start_form_expression'] = start_form.get('expression')
            data['start_form_interface_uuid'] = start_form.get('interface_uuid')
            data['start_form_interface_name'] = start_form.get('interface_name')

        # Extract security roles
        data['security'] = self._extract_role_map(root)

        # Calculate statistics
        data['total_nodes'] = len(data['nodes'])
        data['total_flows'] = len(data['flows'])
        data['complexity_score'] = self._calculate_complexity(data)

        return data

    def _extract_basic_info_from_meta(self, meta_elem: ET.Element) -> Dict[str, Any]:
        """
        Extract basic information from process model meta element.

        Args:
            meta_elem: Meta XML element

        Returns:
            Dict with uuid, name, version_uuid, description
        """
        ns = {'a': 'http://www.appian.com/ae/types/2009'}

        uuid_elem = meta_elem.find('a:uuid', ns)
        uuid = uuid_elem.text if uuid_elem is not None and uuid_elem.text else None

        # Extract name from string-map (handles multiple locales)
        name = None
        name_elem = meta_elem.find('a:name', ns)
        if name_elem is not None:
            string_map = name_elem.find('a:string-map', ns)
            name = self._extract_localized_string(string_map, ns)

        # Extract description from string-map (handles multiple locales)
        description = None
        desc_elem = meta_elem.find('a:desc', ns)
        if desc_elem is not None:
            string_map = desc_elem.find('a:string-map', ns)
            description = self._extract_localized_string(string_map, ns)

        # Version UUID is at the root level - we need to pass it from parse()
        # For now, set to None and extract it in parse()
        version_uuid = None

        return {
            'uuid': uuid,
            'name': name,
            'version_uuid': version_uuid,
            'description': description
        }

    def _extract_nodes(self, pm_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract node definitions from process model with enhanced metadata.

        Extracts:
        - Basic node info (id, type, name)
        - Enhanced type info (human-readable name, category)
        - Gateway conditions for XOR/OR gateways
        - Form expressions for User Input Tasks
        - Pre-trigger rules for Timer/Rule events
        - Node inputs and outputs

        Args:
            pm_elem: Process model XML element

        Returns:
            List of node dictionaries with enhanced metadata
        """
        ns = {'a': 'http://www.appian.com/ae/types/2009'}
        nodes = []

        nodes_elem = pm_elem.find('a:nodes', ns)
        if nodes_elem is None:
            return nodes

        for node_elem in nodes_elem.findall('a:node', ns):
            node_uuid = node_elem.get('uuid')
            gui_id_elem = node_elem.find('a:guiId', ns)
            gui_id = gui_id_elem.text if gui_id_elem is not None else None

            # Extract node name from fname string-map (handles multiple locales)
            node_name = None
            fname_elem = node_elem.find('a:fname', ns)
            if fname_elem is not None:
                string_map = fname_elem.find('a:string-map', ns)
                if string_map is None:
                    string_map = fname_elem.find('string-map')
                node_name = self._extract_localized_string(string_map, ns)

            # Determine node type from activity class
            node_type = 'Unknown'
            ac_elem = node_elem.find('a:ac', ns)
            if ac_elem is not None:
                local_id_elem = ac_elem.find('a:local-id', ns)
                if local_id_elem is not None and local_id_elem.text:
                    node_type = local_id_elem.text

            # Get enhanced node type info from registry
            type_info = get_node_type_info(node_type)

            # Extract inputs (ACPs) and outputs from activity class
            inputs = []
            outputs = []
            if ac_elem is not None:
                inputs = self._extract_node_inputs(ac_elem, ns)
                outputs = self._extract_node_outputs(ac_elem, ns)

            # Extract gateway conditions for XOR/OR/Complex gateways
            gateway_conditions: List[Dict[str, Any]] = []
            if type_info.has_gateway_conditions and ac_elem is not None:
                gateway_conditions = self._extract_gateway_conditions(ac_elem, ns)

            # Extract form expression for User Input Tasks
            form_expression: Optional[str] = None
            interface_uuid: Optional[str] = None
            interface_name: Optional[str] = None
            if type_info.has_form and ac_elem is not None:
                form_expression = self._extract_form_expression(ac_elem, ns)
                interface_ref = self._extract_interface_reference(ac_elem, ns)
                if interface_ref:
                    interface_uuid = interface_ref.get('uuid')
                    interface_name = interface_ref.get('name')

            # Extract pre-triggers for Timer/Rule events
            pre_triggers: List[Dict[str, Any]] = []
            if type_info.has_pre_triggers:
                pre_triggers = self._extract_pre_triggers(node_elem, ns)

            # Extract timer configuration for Timer/Rule events (Phase 3)
            timer_config: Optional[Dict[str, Any]] = None
            if type_info.has_pre_triggers and ac_elem is not None:
                timer_config = self._extract_timer_config(ac_elem, ns)

            # Extract subprocess configuration for Subprocess/Link Process nodes (Phase 4)
            subprocess_config: Optional[Dict[str, Any]] = None
            subprocess_uuid: Optional[str] = None
            if type_info.has_subprocess_target and ac_elem is not None:
                subprocess_config = self._extract_subprocess_target(ac_elem, ns)
                if subprocess_config:
                    subprocess_uuid = subprocess_config.get('target_uuid')
                    # Use subprocess input/output mappings as node inputs/outputs
                    if subprocess_config.get('input_mappings'):
                        inputs = [
                            {
                                'input_name': m['param_name'],
                                'input_expression': m.get('expression')
                            }
                            for m in subprocess_config['input_mappings']
                        ]
                    if subprocess_config.get('output_mappings'):
                        outputs = [
                            {
                                'save_into': m.get('save_into'),
                                'output_expression': m['param_name']
                            }
                            for m in subprocess_config['output_mappings']
                        ]

            # For Timer/Rule events, use pre-triggers as inputs if no other inputs
            if type_info.has_pre_triggers and not inputs and pre_triggers:
                # Convert pre-trigger rules to inputs for display
                for trigger in pre_triggers:
                    for rule in trigger.get('rules', []):
                        if rule.get('type') == 'complex' and rule.get('expression'):
                            inputs.append({
                                'input_name': f"Rule ({trigger.get('type_name', 'Unknown')})",
                                'input_expression': rule['expression']
                            })
                        elif rule.get('type') == 'simple':
                            left = rule.get('left_operand', '')
                            op = rule.get('operator', '')
                            right = rule.get('right_operand', '')
                            expr = f"{left} {op} {right}"
                            inputs.append({
                                'input_name': f"Rule ({trigger.get('type_name', 'Unknown')})",
                                'input_expression': expr.strip()
                            })

            node = {
                'node_id': node_uuid or gui_id,
                'node_type': node_type,
                'node_name': node_name,
                'gui_id': gui_id,
                # Swim lane / attendee
                'attendee': self._extract_attendee(node_elem, ns),
                # Enhanced metadata from node type registry
                'node_type_name': type_info.name,
                'node_category': type_info.category.value,
                # Conditional metadata based on node type
                'gateway_conditions': gateway_conditions,
                'form_expression': form_expression,
                'interface_uuid': interface_uuid,
                'interface_name': interface_name,
                'pre_triggers': pre_triggers,
                'subprocess_uuid': subprocess_uuid,
                'subprocess_config': subprocess_config,  # Phase 4
                'timer_config': timer_config,  # Phase 3
                # Existing fields
                'inputs': inputs,
                'outputs': outputs,
                'properties': {}
            }

            nodes.append(node)

        return nodes

    def _extract_node_inputs(self, ac_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract input parameters (ACPs) from a node's activity class element.

        Inputs come from both <acps> and <custom-params> elements.
        Only includes parameters where input-to-activity-class is true.

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            List of input dictionaries with input_name and input_expression
        """
        inputs = []

        # Collect ACPs from both <acps> and <custom-params>
        acp_containers = []

        acps_elem = ac_elem.find('a:acps', ns)
        if acps_elem is not None:
            acp_containers.append(acps_elem)

        custom_params_elem = ac_elem.find('a:custom-params', ns)
        if custom_params_elem is not None:
            acp_containers.append(custom_params_elem)

        for container in acp_containers:
            for acp_elem in container.findall('a:acp', ns):
                input_name = acp_elem.get('name')
                if not input_name:
                    continue

                # Check if this is an input (input-to-activity-class = true)
                input_flag_elem = acp_elem.find('a:input-to-activity-class', ns)
                is_input = input_flag_elem is not None and input_flag_elem.text == 'true'

                if not is_input:
                    continue

                # Extract the expression
                expr_elem = acp_elem.find('a:expr', ns)
                input_expression = None
                if expr_elem is not None and expr_elem.text:
                    input_expression = self._clean_sail_code(expr_elem.text) or expr_elem.text.strip()

                # Only include if there's an expression (skip empty/default inputs)
                if input_expression:
                    inputs.append({
                        'input_name': input_name,
                        'input_expression': input_expression
                    })

        return inputs

    def _extract_node_outputs(self, ac_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract output expressions from a node's activity class element.

        Outputs are defined in <output-exprs> as <el> elements with format:
        "saveIntoVariable:expression"

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            List of output dictionaries with save_into and output_expression
        """
        outputs = []

        output_exprs_elem = ac_elem.find('a:output-exprs', ns)
        if output_exprs_elem is None:
            return outputs

        for el_elem in output_exprs_elem.findall('a:el', ns):
            if el_elem.text is None:
                continue

            expr_text = el_elem.text.strip()
            if not expr_text:
                continue

            # Parse the expression format: "variableName:expression"
            # The colon separates the save-into variable from the expression
            colon_idx = expr_text.find(':')
            if colon_idx == -1:
                # No colon found, treat entire text as expression with no save-into
                outputs.append({
                    'save_into': None,
                    'output_expression': self._clean_sail_code(expr_text) or expr_text
                })
            else:
                save_into = expr_text[:colon_idx].strip()
                raw_expr = expr_text[colon_idx + 1:].strip()
                outputs.append({
                    'save_into': save_into,
                    'output_expression': self._clean_sail_code(raw_expr) or raw_expr
                })

        return outputs

    def _extract_flows(self, pm_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract flow/connection definitions from process model.

        Args:
            pm_elem: Process model XML element

        Returns:
            List of flow dictionaries
        """
        ns = {'a': 'http://www.appian.com/ae/types/2009'}
        flows = []

        nodes_elem = pm_elem.find('a:nodes', ns)
        if nodes_elem is None:
            return flows

        # Flows are defined as connections within nodes
        for node_elem in nodes_elem.findall('a:node', ns):
            from_node_uuid = node_elem.get('uuid')
            from_gui_id_elem = node_elem.find('a:guiId', ns)
            from_gui_id = from_gui_id_elem.text if from_gui_id_elem is not None else None
            from_node_id = from_node_uuid or from_gui_id

            connections_elem = node_elem.find('a:connections', ns)
            if connections_elem is None:
                continue

            for conn_elem in connections_elem.findall('a:connection', ns):
                to_elem = conn_elem.find('a:to', ns)
                to_node_id = to_elem.text if to_elem is not None else None

                flow_label_elem = conn_elem.find('a:flowLabel', ns)
                flow_label = flow_label_elem.text if flow_label_elem is not None else None

                flow = {
                    'from_node_id': from_node_id,
                    'to_node_id': to_node_id,
                    'flow_label': flow_label,
                    'flow_condition': None  # Not typically in XML
                }

                flows.append(flow)

        return flows

    def _extract_variables(self, pm_elem: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract process variable definitions from process model.

        Args:
            pm_elem: Process model XML element

        Returns:
            List of variable dictionaries
        """
        ns = {'a': 'http://www.appian.com/ae/types/2009'}
        variables = []

        pvs_elem = pm_elem.find('a:pvs', ns)
        if pvs_elem is None:
            return variables

        for pv_elem in pvs_elem.findall('a:pv', ns):
            var_name = pv_elem.get('name')
            if not var_name:
                continue

            # Check if it's a parameter
            parameter_elem = pv_elem.find('a:parameter', ns)
            is_parameter = parameter_elem is not None and parameter_elem.text == 'true'

            # Extract hidden/required flags
            hidden_elem = pv_elem.find('a:hidden', ns)
            is_hidden = hidden_elem is not None and hidden_elem.text == 'true'

            required_elem = pv_elem.find('a:required', ns)
            is_required = required_elem is not None and required_elem.text == 'true'

            # Extract type information
            var_type = None
            value_elem = pv_elem.find('a:value', ns)
            if value_elem is not None:
                xsi_type = value_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                if xsi_type:
                    var_type = xsi_type

            # Extract default value from <a:value> text or <a:expr>
            default_value = None
            if value_elem is not None and value_elem.text:
                default_value = value_elem.text.strip()

            initial_expression = None
            expr_elem = pv_elem.find('a:expr', ns)
            if expr_elem is not None and expr_elem.text:
                initial_expression = self._clean_sail_code(expr_elem.text)

            variable = {
                'variable_name': var_name,
                'variable_type': var_type,
                'is_parameter': is_parameter,
                'is_hidden': is_hidden,
                'is_required': is_required,
                'default_value': default_value,
                'initial_expression': initial_expression,
            }

            variables.append(variable)

        return variables

    def _extract_attendee(
        self, node_elem: ET.Element, ns: Dict[str, str]
    ) -> Optional[str]:
        """Extract swim lane / attendee name from node element."""
        attendee_elem = node_elem.find('a:attendee', ns)
        if attendee_elem is None:
            return None
        string_map = attendee_elem.find('a:string-map', ns)
        if string_map is None:
            string_map = attendee_elem.find('string-map')
        return self._extract_localized_string(string_map, ns)

    def _calculate_complexity(self, data: Dict[str, Any]) -> float:
        """
        Calculate process model complexity score.

        Uses McCabe cyclomatic complexity: nodes + flows - 2

        Args:
            data: Process model data dict

        Returns:
            Complexity score
        """
        total_nodes = data.get('total_nodes', 0)
        total_flows = data.get('total_flows', 0)

        # McCabe complexity: nodes + flows - 2
        # Ensure minimum of 0
        complexity = max(0, total_nodes + total_flows - 2)

        return float(complexity)

    def _extract_gateway_conditions(
        self,
        ac_elem: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract gateway conditions from XOR/OR/Complex gateway nodes.

        Gateway conditions are stored in the activity class parameters (acps)
        under the 'rules' parameter. Each rule contains:
        - expression: The condition expression (e.g., '=pv!approved')
        - node: The target node GUI ID
        - label: Optional label for the condition

        The default node is stored separately in the 'defaultNode' parameter.

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            List of condition dictionaries with:
            - target_gui_id: Target node GUI ID
            - label: Condition label (if any)
            - condition: The condition expression
            - is_default: Whether this is the default path
        """
        conditions = []

        acps_elem = ac_elem.find('a:acps', ns)
        if acps_elem is None:
            return conditions

        # Find the default node
        default_node_id: Optional[str] = None
        for acp in acps_elem.findall('a:acp', ns):
            if acp.get('name') == 'defaultNode':
                value_elem = acp.find('a:value', ns)
                if value_elem is not None and value_elem.text:
                    default_node_id = value_elem.text.strip()
                break

        # Find the rules parameter
        rules_acp = None
        for acp in acps_elem.findall('a:acp', ns):
            if acp.get('name') == 'rules':
                rules_acp = acp
                break

        if rules_acp is None:
            return conditions

        # Extract rules from the nested structure
        # Structure: rules/value/acps/acp[name='rule']/value/acps/acp[name='expression|node|label']
        rules_value = rules_acp.find('a:value', ns)
        if rules_value is None:
            return conditions

        rules_acps = rules_value.find('a:acps', ns)
        if rules_acps is None:
            return conditions

        for rule_acp in rules_acps.findall('a:acp', ns):
            if rule_acp.get('name') != 'rule':
                continue

            rule_value = rule_acp.find('a:value', ns)
            if rule_value is None:
                continue

            rule_inner_acps = rule_value.find('a:acps', ns)
            if rule_inner_acps is None:
                continue

            # Extract expression, node, and label from the rule
            expression: Optional[str] = None
            target_node: Optional[str] = None
            label: Optional[str] = None

            for inner_acp in rule_inner_acps.findall('a:acp', ns):
                acp_name = inner_acp.get('name')

                if acp_name == 'expression':
                    # Expression is in the <expr> element, not <value>
                    expr_elem = inner_acp.find('a:expr', ns)
                    if expr_elem is not None and expr_elem.text:
                        expression = self._clean_sail_code(expr_elem.text) or expr_elem.text.strip()

                elif acp_name == 'node':
                    value_elem = inner_acp.find('a:value', ns)
                    if value_elem is not None and value_elem.text:
                        target_node = value_elem.text.strip()

                elif acp_name == 'label':
                    value_elem = inner_acp.find('a:value', ns)
                    if value_elem is not None and value_elem.text:
                        label = value_elem.text.strip()

            if target_node:
                is_default = (target_node == default_node_id) and not expression
                conditions.append({
                    'target_gui_id': target_node,
                    'label': label,
                    'condition': expression,
                    'is_default': is_default
                })

        # Add the default node if it wasn't already included in rules
        if default_node_id:
            default_exists = any(
                c['target_gui_id'] == default_node_id and c['is_default']
                for c in conditions
            )
            if not default_exists:
                conditions.append({
                    'target_gui_id': default_node_id,
                    'label': None,
                    'condition': None,
                    'is_default': True
                })

        return conditions

    def _extract_form_expression(
        self,
        ac_elem: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[str]:
        """
        Extract SAIL form expression for User Input Tasks.

        Form expressions are stored in the form-map structure:
        form-map/pair/form-config/form/uiExpressionForm/expression

        The form-map contains locale-specific pairs. We look for the
        en_US locale first, then fall back to any locale with content.

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            The SAIL form expression string, or None if not found
        """
        form_map = ac_elem.find('a:form-map', ns)
        if form_map is None:
            # Try without namespace
            form_map = ac_elem.find('form-map')

        if form_map is None:
            return None

        # Look through locale pairs for form expression
        preferred_expression: Optional[str] = None
        fallback_expression: Optional[str] = None

        for pair in form_map.findall('pair'):
            # Check locale
            locale_elem = pair.find('locale')
            is_preferred = False
            if locale_elem is not None:
                lang = locale_elem.get('lang', '')
                country = locale_elem.get('country', '')
                is_preferred = (lang == 'en' and country == 'US')

            # Navigate to expression
            form_config = pair.find('form-config')
            if form_config is None:
                continue

            form = form_config.find('form')
            if form is None:
                continue

            ui_expr_form = form.find('uiExpressionForm')
            if ui_expr_form is None:
                continue

            expr_elem = ui_expr_form.find('expression')
            if expr_elem is not None and expr_elem.text:
                expr_text = self._clean_sail_code(expr_elem.text) or expr_elem.text.strip()
                if expr_text:
                    if is_preferred:
                        preferred_expression = expr_text
                        break  # Found preferred, stop searching
                    elif fallback_expression is None:
                        fallback_expression = expr_text

        return preferred_expression or fallback_expression

    def _extract_interface_reference(
        self,
        ac_elem: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, str]]:
        """
        Extract interface reference for User Input Tasks.

        When a User Input Task uses an interface (rather than inline SAIL),
        the interface information is stored in the form-map structure.

        Appian stores interface references in two possible locations:
        1. Primary (modern): form-map/pair/form-config/form/interfaceInformation
           Contains: name, uuid, and ruleInputs
        2. Legacy: form-map/pair/form-config/form/uiRuleForm/rule/uuid
           Contains only the UUID

        Note: The form-map element may be namespaced (a:form-map) but its
        children (pair, form-config, form, interfaceInformation) are typically
        NOT namespaced in Appian XML exports.

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            Dictionary with 'uuid' and optionally 'name', or None if not found
        """
        # Try namespaced first, then non-namespaced
        form_map = ac_elem.find('a:form-map', ns)
        if form_map is None:
            form_map = ac_elem.find('form-map')

        if form_map is None:
            return None

        # Look through locale pairs for interface reference
        # Prefer en_US locale, then fall back to any locale with content
        preferred_result: Optional[Dict[str, str]] = None
        fallback_result: Optional[Dict[str, str]] = None

        # Try both namespaced and non-namespaced pair elements
        pairs = form_map.findall('a:pair', ns)
        if not pairs:
            pairs = form_map.findall('pair')

        for pair in pairs:
            # Check locale preference (try both namespaced and non-namespaced)
            locale_elem = pair.find('a:locale', ns)
            if locale_elem is None:
                locale_elem = pair.find('locale')

            is_preferred = False
            if locale_elem is not None:
                lang = locale_elem.get('lang', '')
                country = locale_elem.get('country', '')
                is_preferred = (lang == 'en' and country == 'US')

            # Try both namespaced and non-namespaced form-config
            form_config = pair.find('a:form-config', ns)
            if form_config is None:
                form_config = pair.find('form-config')
            if form_config is None:
                continue

            # Try both namespaced and non-namespaced form
            form = form_config.find('a:form', ns)
            if form is None:
                form = form_config.find('form')
            if form is None:
                continue

            result = self._extract_interface_from_form(form, ns)
            if result:
                if is_preferred:
                    preferred_result = result
                    break  # Found preferred locale, stop searching
                elif fallback_result is None:
                    fallback_result = result

        return preferred_result or fallback_result

    def _extract_interface_from_form(
        self,
        form: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, str]]:
        """
        Extract interface information from a form element.

        Checks both modern (interfaceInformation) and legacy (uiRuleForm)
        locations for interface references. Handles both namespaced and
        non-namespaced elements.

        Args:
            form: The form XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            Dictionary with 'uuid' and optionally 'name', or None if not found
        """
        # Primary location: interfaceInformation (modern Appian format)
        # Try both namespaced and non-namespaced
        interface_info = form.find('a:interfaceInformation', ns)
        if interface_info is None:
            interface_info = form.find('interfaceInformation')

        if interface_info is not None:
            # Try both namespaced and non-namespaced uuid/name elements
            uuid_elem = interface_info.find('a:uuid', ns)
            if uuid_elem is None:
                uuid_elem = interface_info.find('uuid')

            name_elem = interface_info.find('a:name', ns)
            if name_elem is None:
                name_elem = interface_info.find('name')

            if uuid_elem is not None and uuid_elem.text:
                result: Dict[str, str] = {'uuid': uuid_elem.text.strip()}
                if name_elem is not None and name_elem.text:
                    result['name'] = name_elem.text.strip()
                return result

        # Legacy location: uiRuleForm/rule/uuid
        # Try both namespaced and non-namespaced
        ui_rule_form = form.find('a:uiRuleForm', ns)
        if ui_rule_form is None:
            ui_rule_form = form.find('uiRuleForm')

        if ui_rule_form is not None:
            rule_elem = ui_rule_form.find('a:rule', ns)
            if rule_elem is None:
                rule_elem = ui_rule_form.find('rule')

            if rule_elem is not None:
                uuid_elem = rule_elem.find('a:uuid', ns)
                if uuid_elem is None:
                    uuid_elem = rule_elem.find('uuid')

                if uuid_elem is not None and uuid_elem.text:
                    return {'uuid': uuid_elem.text.strip()}

        return None

    def _extract_start_form(self, pm_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Extract the PM-level start form (form-map directly under pm element)."""
        ns = {'a': 'http://www.appian.com/ae/types/2009'}

        # The PM-level form-map is a direct child of the pm element (not inside a node)
        # It may be non-namespaced since it's outside the <nodes> section
        form_map = pm_elem.find('form-map')
        if form_map is None:
            form_map = pm_elem.find('a:form-map', ns)
        if form_map is None or len(list(form_map)) == 0:
            return None

        result: Dict[str, Any] = {}

        pairs = form_map.findall('pair')
        if not pairs:
            pairs = form_map.findall('a:pair', ns)

        for pair in pairs:
            locale_elem = pair.find('locale') or pair.find('a:locale', ns)
            is_preferred = False
            if locale_elem is not None:
                is_preferred = (locale_elem.get('lang', '') == 'en' and locale_elem.get('country', '') == 'US')

            form_config = pair.find('form-config') or pair.find('a:form-config', ns)
            if form_config is None:
                continue
            form = form_config.find('form') or form_config.find('a:form', ns)
            if form is None:
                continue

            # Extract expression
            ui_expr = form.find('uiExpressionForm') or form.find('a:uiExpressionForm', ns)
            if ui_expr is not None:
                expr_elem = ui_expr.find('expression') or ui_expr.find('a:expression', ns)
                if expr_elem is not None and expr_elem.text:
                    result['expression'] = self._clean_sail_code(expr_elem.text) or expr_elem.text.strip()

            # Extract interface info
            iface_info = form.find('interfaceInformation') or form.find('a:interfaceInformation', ns)
            if iface_info is not None:
                uuid_elem = iface_info.find('uuid') or iface_info.find('a:uuid', ns)
                name_elem = iface_info.find('name') or iface_info.find('a:name', ns)
                if uuid_elem is not None and uuid_elem.text:
                    result['interface_uuid'] = uuid_elem.text.strip()
                if name_elem is not None and name_elem.text:
                    result['interface_name'] = name_elem.text.strip()

            if is_preferred and result:
                return result

        return result if result else None

    def _extract_subprocess_target(
        self,
        ac_elem: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract subprocess target and configuration for Subprocess/Link Process nodes (Phase 4).

        The target process model UUID is stored in ACPs with various names:
        - pmID: Primary parameter name (UUID in a:id attribute)
        - pm: Process model UUID (text content)
        - processModel: Alternative name
        - processModelUuid: Another alternative
        - targetPm: Yet another alternative

        Additional configuration:
        - asynchronous: Whether to run asynchronously
        - inMap: Input parameter mappings

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            Subprocess configuration dictionary with target_uuid, is_asynchronous,
            and input_mappings, or None if no subprocess target found
        """
        acps_elem = ac_elem.find('a:acps', ns)
        if acps_elem is None:
            return None

        config: Dict[str, Any] = {}

        # Look for process model UUID in various parameter names
        # pmID is the primary one used in Appian, with UUID in a:id attribute
        pm_param_names = ['pmID', 'pm', 'processModel', 'processModelUuid', 'targetPm']

        for acp in acps_elem.findall('a:acp', ns):
            acp_name = acp.get('name')

            if acp_name in pm_param_names:
                value_elem = acp.find('a:value', ns)
                if value_elem is not None:
                    # First try a:id attribute (primary method for pmID)
                    uuid_from_attr = value_elem.get('{http://www.appian.com/ae/types/2009}id')
                    if uuid_from_attr:
                        config['target_uuid'] = uuid_from_attr
                    # Then try text content (fallback)
                    elif value_elem.text:
                        config['target_uuid'] = value_elem.text.strip()
                    else:
                        # Try expression element (dynamic reference)
                        expr_elem = acp.find('a:expr', ns)
                        if expr_elem is not None and expr_elem.text:
                            config['target_expression'] = expr_elem.text.strip()

            elif acp_name == 'asynchronous':
                value_elem = acp.find('a:value', ns)
                if value_elem is not None and value_elem.text:
                    config['is_asynchronous'] = value_elem.text.strip().lower() == 'true'

            elif acp_name == 'inMap':
                # Extract input mappings from nested structure
                input_mappings = self._extract_subprocess_input_mappings(acp, ns)
                if input_mappings:
                    config['input_mappings'] = input_mappings

            elif acp_name == 'outMap':
                # Extract output mappings from nested structure
                output_mappings = self._extract_subprocess_output_mappings(acp, ns)
                if output_mappings:
                    config['output_mappings'] = output_mappings

        return config if config else None

    def _extract_subprocess_input_mappings(
        self,
        inmap_acp: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract input parameter mappings from subprocess inMap ACP.

        Structure: inMap/value/acps/acp[name='oneInputMap']/value/acps/acp[name='sppn|sppv']

        Args:
            inmap_acp: The inMap ACP element
            ns: Namespace dictionary

        Returns:
            List of input mapping dictionaries with param_name and expression
        """
        mappings = []

        value_elem = inmap_acp.find('a:value', ns)
        if value_elem is None:
            return mappings

        acps_elem = value_elem.find('a:acps', ns)
        if acps_elem is None:
            return mappings

        for one_input_acp in acps_elem.findall('a:acp', ns):
            if one_input_acp.get('name') != 'oneInputMap':
                continue

            inner_value = one_input_acp.find('a:value', ns)
            if inner_value is None:
                continue

            inner_acps = inner_value.find('a:acps', ns)
            if inner_acps is None:
                continue

            param_name = None
            expression = None

            for inner_acp in inner_acps.findall('a:acp', ns):
                inner_name = inner_acp.get('name')

                if inner_name == 'sppn':
                    # Subprocess parameter name
                    val = inner_acp.find('a:value', ns)
                    if val is not None and val.text:
                        param_name = val.text.strip()

                elif inner_name == 'sppv':
                    # Subprocess parameter value (expression)
                    expr = inner_acp.find('a:expr', ns)
                    if expr is not None and expr.text:
                        expression = self._clean_sail_code(expr.text) or expr.text.strip()

            if param_name:
                mappings.append({
                    'param_name': param_name,
                    'expression': expression
                })

        return mappings

    def _extract_subprocess_output_mappings(
        self,
        outmap_acp: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract output parameter mappings from subprocess outMap ACP.

        Structure: outMap/value/acps/acp[name='oneOutputMap']/value/acps/acp[name='sppn|sppv']

        Args:
            outmap_acp: The outMap ACP element
            ns: Namespace dictionary

        Returns:
            List of output mapping dictionaries with param_name and save_into
        """
        mappings = []

        value_elem = outmap_acp.find('a:value', ns)
        if value_elem is None:
            return mappings

        acps_elem = value_elem.find('a:acps', ns)
        if acps_elem is None:
            return mappings

        for one_output_acp in acps_elem.findall('a:acp', ns):
            if one_output_acp.get('name') != 'oneOutputMap':
                continue

            inner_value = one_output_acp.find('a:value', ns)
            if inner_value is None:
                continue

            inner_acps = inner_value.find('a:acps', ns)
            if inner_acps is None:
                continue

            param_name = None
            save_into = None

            for inner_acp in inner_acps.findall('a:acp', ns):
                inner_name = inner_acp.get('name')

                if inner_name == 'sppn':
                    # Subprocess parameter name
                    val = inner_acp.find('a:value', ns)
                    if val is not None and val.text:
                        param_name = val.text.strip()

                elif inner_name == 'sppv':
                    # Save into variable (expression)
                    expr = inner_acp.find('a:expr', ns)
                    if expr is not None and expr.text:
                        save_into = self._clean_sail_code(expr.text) or expr.text.strip()

            if param_name:
                mappings.append({
                    'param_name': param_name,
                    'save_into': save_into
                })

        return mappings

    def _extract_timer_config(
        self,
        ac_elem: ET.Element,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract timer configuration for Timer/Rule/Receive Message events (Phase 3).

        Timer configuration is stored in ACPs with the following parameters:
        - delayType: 0=Delay from activation, 1=Specific date/time, 2=Recurring
        - delayValue: Number of time units
        - delayUnits: 0=Minutes, 1=Hours, 2=Days, 3=Weeks, 4=Months
        - recurrenceInterval: Repeat interval
        - recurrenceCount: Number of repetitions (-1 = infinite)
        - ruleExpression: Expression that triggers the event
        - dateTimeExpression: Specific date/time expression

        Args:
            ac_elem: Activity class XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            Timer configuration dictionary or None if no timer config found
        """
        acps_elem = ac_elem.find('a:acps', ns)
        if acps_elem is None:
            return None

        config: Dict[str, Any] = {}

        # Map of ACP names to extract
        acp_mappings = {
            'delayType': 'delay_type',
            'delayValue': 'delay_value',
            'delayUnits': 'delay_units',
            'recurrenceInterval': 'recurrence_interval',
            'recurrenceCount': 'recurrence_count',
            'ruleExpression': 'rule_expression',
            'dateTimeExpression': 'datetime_expression',
            'timerExpression': 'timer_expression',
        }

        delay_type_names = {
            '0': 'Delay from activation',
            '1': 'Specific date/time',
            '2': 'Recurring'
        }

        delay_unit_names = {
            '0': 'Minutes',
            '1': 'Hours',
            '2': 'Days',
            '3': 'Weeks',
            '4': 'Months'
        }

        for acp in acps_elem.findall('a:acp', ns):
            acp_name = acp.get('name')
            if acp_name not in acp_mappings:
                continue

            # Try to get value from <expr> element first (for expressions)
            expr_elem = acp.find('a:expr', ns)
            value_elem = acp.find('a:value', ns)

            if expr_elem is not None and expr_elem.text:
                config[acp_mappings[acp_name]] = expr_elem.text.strip()
            elif value_elem is not None and value_elem.text:
                config[acp_mappings[acp_name]] = value_elem.text.strip()

        # Add human-readable names for delay type and units
        if 'delay_type' in config:
            config['delay_type_name'] = delay_type_names.get(
                str(config['delay_type']), 'Unknown'
            )

        if 'delay_units' in config:
            config['delay_units_name'] = delay_unit_names.get(
                str(config['delay_units']), 'Unknown'
            )

        return config if config else None

    def _extract_pre_triggers(
        self,
        node_elem: ET.Element,
        ns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract pre-trigger rules for Timer/Rule/Receive Message events.

        Pre-triggers define conditions that must be met before the event
        activates. They are stored in the pre-triggers element with
        rule-trigger children:
        pre-triggers/rule-trigger/name
        pre-triggers/rule-trigger/rules/rule/type (0=simple, 1=expression)
        pre-triggers/rule-trigger/rules/rule/expression

        Args:
            node_elem: Node XML element
            ns: Namespace dictionary for XML parsing

        Returns:
            List of trigger dictionaries with:
            - name: Trigger name
            - type_name: Human-readable type name
            - rules: List of rule definitions
        """
        triggers = []

        pre_triggers_elem = node_elem.find('a:pre-triggers', ns)
        if pre_triggers_elem is None:
            # Try without namespace
            pre_triggers_elem = node_elem.find('pre-triggers')

        if pre_triggers_elem is None:
            return triggers

        # Look for rule-trigger elements (the actual structure in Appian XML)
        for trigger_elem in pre_triggers_elem.findall('rule-trigger'):
            self._process_rule_trigger(trigger_elem, triggers)

        # Also try with namespace prefix
        for trigger_elem in pre_triggers_elem.findall('a:rule-trigger', ns):
            self._process_rule_trigger(trigger_elem, triggers)

        # Legacy: Also try pre-trigger elements
        for trigger_elem in pre_triggers_elem.findall('pre-trigger'):
            self._process_pre_trigger(trigger_elem, {
                '0': 'Message',
                '2': 'Timer',
                '4': 'Rule'
            }, triggers)

        for trigger_elem in pre_triggers_elem.findall('a:pre-trigger', ns):
            self._process_pre_trigger(trigger_elem, {
                '0': 'Message',
                '2': 'Timer',
                '4': 'Rule'
            }, triggers)

        return triggers

    def _process_rule_trigger(
        self,
        trigger_elem: ET.Element,
        triggers: List[Dict[str, Any]]
    ) -> None:
        """
        Process a rule-trigger element and add to triggers list.

        Args:
            trigger_elem: rule-trigger XML element
            triggers: List to append processed trigger to
        """
        ns = {'a': 'http://www.appian.com/ae/types/2009'}

        # Get trigger name - try with namespace first, then without
        name_elem = trigger_elem.find('a:name', ns)
        if name_elem is None:
            name_elem = trigger_elem.find('name')
        trigger_name = 'Unnamed Trigger'
        if name_elem is not None and name_elem.text:
            trigger_name = name_elem.text.strip()

        trigger_data: Dict[str, Any] = {
            'name': trigger_name,
            'type_name': 'Rule',
            'rules': []
        }

        # Find rules element - try with namespace first, then without
        rules_elem = trigger_elem.find('a:rules', ns)
        if rules_elem is None:
            rules_elem = trigger_elem.find('rules')

        if rules_elem is not None:
            # Find rule elements - try with namespace first, then without
            rule_elems = rules_elem.findall('a:rule', ns)
            if not rule_elems:
                rule_elems = rules_elem.findall('rule')

            for rule_elem in rule_elems:
                # Get rule type
                rule_type_elem = rule_elem.find('a:type', ns)
                if rule_type_elem is None:
                    rule_type_elem = rule_elem.find('type')
                rule_type = rule_type_elem.text if rule_type_elem is not None else '0'

                if rule_type == '0':  # Simple rule
                    trigger_data['rules'].append({
                        'type': 'simple',
                        'left_operand': self._get_elem_text_ns(rule_elem, 'leftOperand', ns),
                        'operator': self._get_elem_text_ns(rule_elem, 'operator', ns),
                        'right_operand': self._get_elem_text_ns(rule_elem, 'rightOperand', ns)
                    })
                else:  # Expression-based rule (type=1)
                    raw_expr = self._get_elem_text_ns(rule_elem, 'expression', ns)
                    trigger_data['rules'].append({
                        'type': 'complex',
                        'expression': self._clean_sail_code(raw_expr) or raw_expr
                    })

        # Only add if we have meaningful data
        if trigger_data['rules']:
            triggers.append(trigger_data)

    def _get_elem_text_ns(
        self,
        parent: ET.Element,
        tag: str,
        ns: Dict[str, str]
    ) -> Optional[str]:
        """
        Safely get text content from a child element, trying namespaced first.

        Args:
            parent: Parent XML element
            tag: Child element tag name (without namespace prefix)
            ns: Namespace dictionary

        Returns:
            Text content or None if not found
        """
        # Try with namespace first
        elem = parent.find(f'a:{tag}', ns)
        if elem is None:
            elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    def _process_pre_trigger(
        self,
        trigger_elem: ET.Element,
        trigger_type_names: Dict[str, str],
        triggers: List[Dict[str, Any]]
    ) -> None:
        """
        Process a single pre-trigger element and add to triggers list.

        Args:
            trigger_elem: Pre-trigger XML element
            trigger_type_names: Mapping of type codes to names
            triggers: List to append processed trigger to
        """
        type_elem = trigger_elem.find('type')
        trigger_type = type_elem.text if type_elem is not None else '0'

        trigger_data: Dict[str, Any] = {
            'type': trigger_type,
            'type_name': trigger_type_names.get(trigger_type, 'Unknown'),
            'rules': []
        }

        rules_elem = trigger_elem.find('rules')
        if rules_elem is not None:
            for rule_elem in rules_elem.findall('rule'):
                rule_type_elem = rule_elem.find('type')
                rule_type = rule_type_elem.text if rule_type_elem is not None else '0'

                if rule_type == '0':  # Simple rule
                    trigger_data['rules'].append({
                        'type': 'simple',
                        'left_operand': self._get_elem_text(rule_elem, 'left-operand'),
                        'operator': self._get_elem_text(rule_elem, 'operator'),
                        'right_operand': self._get_elem_text(rule_elem, 'right-operand')
                    })
                else:  # Complex rule (expression-based)
                    trigger_data['rules'].append({
                        'type': 'complex',
                        'expression': self._get_elem_text(rule_elem, 'expression')
                    })

        # Only add if we have meaningful data
        if trigger_data['rules'] or trigger_type != '0':
            triggers.append(trigger_data)

    def _get_elem_text(
        self,
        parent: ET.Element,
        tag: str
    ) -> Optional[str]:
        """
        Safely get text content from a child element.

        Args:
            parent: Parent XML element
            tag: Child element tag name

        Returns:
            Text content or None if not found
        """
        elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None
