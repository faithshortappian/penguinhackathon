"""
Parser for Appian Control Panel objects.

This module provides the ControlPanelParser class for extracting data from
Control Panel XML files with complex JSON configuration.
"""

import json
import re
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class ControlPanelParser(BaseParser):
    """
    Parser for Appian Control Panel objects.
    
    Control Panels are unique in that their primary configuration is stored
    in a JSON structure within the <settingsJson> tag, rather than SAIL code.
    """

    # XML namespaces used in Control Panel files
    NAMESPACES = {
        'a': 'http://www.appian.com/ae/types/2009',
    }

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Control Panel XML file and extract all relevant data.
        
        Args:
            xml_path: Path to the Control Panel XML file
            
        Returns:
            Dict containing:
            - uuid: Control Panel UUID
            - name: Control Panel name
            - version_uuid: Version UUID
            - description: Control Panel description
            - url_stub: URL stub
            - settings_json_raw: Raw JSON configuration
            - settings_json_parsed: Parsed JSON configuration
            - display_name_type: Display name type (LITERAL, TRANSLATION)
            - display_name_value: Display name value
            - primary_record_type_uuid: Primary record type UUID
            - primary_record_display_name: Primary record display name
            - primary_record_display_name_plural: Primary record display name plural
            - primary_record_url_stub: Primary record URL stub
            - primary_record_data_key_name: Primary record data key name
            - application_uuid: Application UUID
            - rule_folder_uuid: Rule folder UUID
            - branding_icon: Branding icon
            - branding_color: Branding color
            - hierarchy_*: Hierarchy configuration fields
            - interface_types: List of interface type configurations
            - interfaces: List of interface mappings
            - custom_pages: List of custom page configurations
            - referenceable_record_types: List of referenceable record types
            - security_roles: List of security role mappings
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Find the control panel element
        cp_elem = root.find('.//controlPanel')
        if cp_elem is None:
            raise ValueError(f"No controlPanel element found in {xml_path}")
        
        # Extract basic info from attributes and child elements
        data = {
            'uuid': self._get_uuid(cp_elem),
            'name': cp_elem.get('name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_description(cp_elem),
            'url_stub': self._get_url_stub(cp_elem)
        }
        
        # Extract and parse settings JSON
        settings_json_elem = cp_elem.find('settingsJson')
        if settings_json_elem is not None and settings_json_elem.text:
            data['settings_json_raw'] = settings_json_elem.text.strip()
            try:
                settings_json = json.loads(data['settings_json_raw'])
                data['settings_json_parsed'] = settings_json
                
                # Extract structured data from JSON
                data.update(self._extract_json_configuration(settings_json))
                
            except json.JSONDecodeError as e:
                # Log warning but continue processing
                data['settings_json_parsed'] = {}
                # Initialize empty configuration to prevent errors downstream
                data.update(self._get_empty_configuration())
        else:
            data['settings_json_raw'] = None
            data['settings_json_parsed'] = {}
            data.update(self._get_empty_configuration())
        
        # Extract security roles from roleMap
        data['security'] = self._extract_role_map(root)
        
        return data

    def _get_uuid(self, cp_elem: ET.Element) -> Optional[str]:
        """
        Extract UUID from Control Panel element, handling namespaces.
        
        Args:
            cp_elem: Control Panel XML element
            
        Returns:
            UUID string or None
        """
        # Try with namespace first
        uuid = cp_elem.get('{http://www.appian.com/ae/types/2009}uuid')
        if uuid:
            return uuid
        
        # Try without namespace
        return cp_elem.get('uuid')

    def _get_description(self, cp_elem: ET.Element) -> Optional[str]:
        """
        Extract description from Control Panel element, handling namespaces.
        
        Args:
            cp_elem: Control Panel XML element
            
        Returns:
            Description string or None
        """
        # Try with namespace first
        desc = self._get_text(cp_elem, '{http://www.appian.com/ae/types/2009}description')
        if desc:
            return desc
        
        # Try without namespace
        return self._get_text(cp_elem, 'description')

    def _get_url_stub(self, cp_elem: ET.Element) -> Optional[str]:
        """
        Extract URL stub from Control Panel element, handling namespaces.
        
        Args:
            cp_elem: Control Panel XML element
            
        Returns:
            URL stub string or None
        """
        # Try with namespace first
        url_stub = self._get_text(cp_elem, '{http://www.appian.com/ae/types/2009}urlStub')
        if url_stub:
            return url_stub
        
        # Try without namespace
        return self._get_text(cp_elem, 'urlStub')

    def _get_empty_configuration(self) -> Dict[str, Any]:
        """
        Get empty configuration structure to prevent downstream errors.
        
        Returns:
            Dict with all configuration fields set to None or empty lists
        """
        return {
            'display_name_type': None,
            'display_name_value': None,
            'primary_record_type_uuid': None,
            'primary_record_display_name': None,
            'primary_record_display_name_plural': None,
            'primary_record_url_stub': None,
            'primary_record_data_key_name': None,
            'application_uuid': None,
            'rule_folder_uuid': None,
            'branding_icon': None,
            'branding_color': None,
            'hierarchy_unique_join_field': None,
            'hierarchy_selection_designator_field': None,
            'hierarchy_collection_display_name': None,
            'hierarchy_collection_display_name_plural': None,
            'hierarchy_non_collection_display_name': None,
            'hierarchy_non_collection_display_name_plural': None,
            'hierarchy_max_collection_depth': None,
            'hierarchy_cpti_record_type_uuid': None,
            'interface_types': [],
            'interfaces': [],
            'custom_pages': [],
            'referenceable_record_types': []
        }

    def _extract_json_configuration(self, settings_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured configuration from the settings JSON.
        
        Args:
            settings_json: Parsed JSON configuration
            
        Returns:
            Dict with extracted configuration sections
        """
        config = {}
        
        # Extract display name configuration
        display_name = settings_json.get('displayName', {})
        config['display_name_type'] = display_name.get('type')
        config['display_name_value'] = self._extract_display_name_value(display_name)
        
        # Extract primary record configuration
        primary_record = settings_json.get('primaryRecordCfg', {})
        config['primary_record_type_uuid'] = primary_record.get('recordType', {}).get('uuid')
        config['primary_record_display_name'] = primary_record.get('displayName', {}).get('value')
        config['primary_record_display_name_plural'] = primary_record.get('displayNamePlural', {}).get('value')
        config['primary_record_url_stub'] = primary_record.get('urlStub')
        config['primary_record_data_key_name'] = primary_record.get('dataKeyName')
        
        # Extract object storage configuration
        object_storage = settings_json.get('objectStorageCfg', {})
        config['application_uuid'] = object_storage.get('application', {}).get('uuid')
        config['rule_folder_uuid'] = object_storage.get('ruleFolder', {}).get('uuid')
        
        # Extract branding configuration
        branding = settings_json.get('brandingCfg', {})
        config['branding_icon'] = branding.get('icon')
        config['branding_color'] = branding.get('color')
        
        # Extract hierarchy configuration
        hierarchy = settings_json.get('hierarchyCfg', {})
        config['hierarchy_unique_join_field'] = hierarchy.get('uniqueJoinField')
        config['hierarchy_selection_designator_field'] = hierarchy.get('selectionDesignatorField')
        config['hierarchy_collection_display_name'] = hierarchy.get('collectionDisplayName', {}).get('value')
        config['hierarchy_collection_display_name_plural'] = hierarchy.get('collectionDisplayNamePlural', {}).get('value')
        config['hierarchy_non_collection_display_name'] = hierarchy.get('nonCollectionDisplayName', {}).get('value')
        config['hierarchy_non_collection_display_name_plural'] = hierarchy.get('nonCollectionDisplayNamePlural', {}).get('value')
        config['hierarchy_max_collection_depth'] = hierarchy.get('maxCollectionDepth')
        config['hierarchy_cpti_record_type_uuid'] = hierarchy.get('cptiRecordType', {}).get('uuid')
        
        # Extract interface types
        interface_cfg = settings_json.get('interfaceCfg', {})
        config['interface_types'] = []
        for idx, interface_type in enumerate(interface_cfg.get('interfaceTypes', [])):
            config['interface_types'].append({
                'uuid': interface_type.get('uuid'),
                'name_type': interface_type.get('name', {}).get('type'),
                'name_value': interface_type.get('name', {}).get('value'),
                'description_type': interface_type.get('description', {}).get('type'),
                'description_value': interface_type.get('description', {}).get('value'),
                'intent': interface_type.get('intent'),
                'url_stub': interface_type.get('urlStub'),
                'display_order': idx
            })
        
        # Extract interface mappings
        config['interfaces'] = []
        for idx, interface in enumerate(interface_cfg.get('interfaces', [])):
            config['interfaces'].append({
                'interface_uuid': interface.get('interfaceUuid'),
                'interface_type_uuid': interface.get('interfaceTypeUuid'),
                'display_order': idx
            })
        
        # Extract custom pages
        config['custom_pages'] = []
        for idx, custom_page in enumerate(settings_json.get('customPages', [])):
            config['custom_pages'].append({
                'display_name_type': custom_page.get('displayName', {}).get('type'),
                'display_name_value': self._extract_display_name_value(custom_page.get('displayName', {})),
                'description_type': custom_page.get('description', {}).get('type'),
                'description_value': custom_page.get('description', {}).get('value'),
                'interface_uuid': custom_page.get('interfaceUuid'),
                'scope': custom_page.get('scope'),
                'context_rule_input': custom_page.get('contextRuleInput'),
                'url_stub': custom_page.get('urlStub'),
                'icon': custom_page.get('icon'),
                'display_order': idx
            })
        
        # Extract referenceable record types
        config['referenceable_record_types'] = []
        for idx, record_type in enumerate(settings_json.get('referenceableRecordTypes', [])):
            if isinstance(record_type, dict) and 'uuid' in record_type:
                config['referenceable_record_types'].append({
                    'record_type_uuid': record_type['uuid'],
                    'display_order': idx
                })
        
        return config
    
    def _extract_display_name_value(self, display_name_obj: Dict[str, Any]) -> Optional[str]:
        """
        Extract display name value, handling both LITERAL and TRANSLATION types.
        
        Args:
            display_name_obj: Display name object from JSON
            
        Returns:
            Display name value or None
        """
        if display_name_obj.get('type') == 'LITERAL':
            return display_name_obj.get('value')
        elif display_name_obj.get('type') == 'TRANSLATION':
            # For translation type, we store the UUID for now
            # This could be resolved to actual translation text later
            translation_info = display_name_obj.get('value', {})
            if isinstance(translation_info, dict) and 'uuid' in translation_info:
                return f"TRANSLATION:{translation_info['uuid']}"
            return translation_info
        return display_name_obj.get('value')

    def clean_sail_code_from_json(self, json_str: str) -> str:
        """
        Clean SAIL code that might be embedded in JSON values.
        
        This method identifies and cleans SAIL expressions that appear in JSON values,
        particularly in field references and expressions.
        
        Args:
            json_str: JSON string that may contain SAIL code
            
        Returns:
            JSON string with cleaned SAIL code
        """
        if not json_str:
            return json_str
        
        # Pattern to match SAIL field references like #"urn:appian:record-field:..." or #\"urn:appian:record-field:...\"
        sail_field_pattern = r'#\\"urn:appian:record-field:[^\\"]*\\"'
        
        # Replace SAIL field references with cleaned versions
        cleaned_json = re.sub(sail_field_pattern, lambda m: self._clean_field_reference(m.group(0)), json_str)
        
        return cleaned_json
    
    def _clean_field_reference(self, field_ref: str) -> str:
        """
        Clean a SAIL field reference to make it more readable.
        
        Args:
            field_ref: SAIL field reference like #"urn:appian:record-field:v1:uuid/field-uuid" or #\"urn:appian:record-field:v1:uuid/field-uuid\"
            
        Returns:
            Cleaned field reference
        """
        # Extract the field UUID (last part after the final /)
        # Handle both escaped and unescaped quotes
        field_ref_clean = field_ref.replace('\\"', '"')  # Remove escape characters
        parts = field_ref_clean.split('/')
        if len(parts) >= 2:
            field_uuid = parts[-1].rstrip('"')
            return f'#FIELD[{field_uuid}]'
        return field_ref