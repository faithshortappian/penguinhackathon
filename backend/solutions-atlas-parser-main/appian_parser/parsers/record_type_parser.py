"""
Parser for Appian Record Type objects.

This module provides the RecordTypeParser class for extracting data from
Record Type XML files.

Enhanced to support Record Type Reference Resolution by extracting:
- plural_name: The plural display name of the record type (e.g., 'AS_GSM_Addresses')
- display_name: Human-readable display names for fields (e.g., 'Address Id')

These fields enable resolution of record type URNs in SAIL code:
    #"urn:appian:record-field:v1:{rt_uuid}/{field_uuid}"
    → recordType!{PluralName}.{fieldName}

Note: Field types are stored as raw values during parsing. Type resolution
to user-friendly display names is performed in post-extraction processing
when the record type cache is available.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class RecordTypeParser(BaseParser):
    """
    Parser for Appian Record Type objects.

    Extracts fields, relationships, views, and actions from Record Type XML files.

    Enhanced Extraction (for Record Type Reference Resolution):
        - plural_name: Extracted from <a:pluralName> element for display
        - display_name: Extracted from <displayName> element within each field

    Example:
        >>> parser = RecordTypeParser()
        >>> data = parser.parse('recordType.xml')
        >>> data['plural_name']
        'AS_GSM_Addresses'
        >>> data['fields'][0]['display_name']
        'Address Id'
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Record Type XML file and extract all relevant data.

        Args:
            xml_path: Path to the Record Type XML file

        Returns:
            Dict containing:
            - uuid: Record Type UUID
            - name: Record Type name
            - plural_name: Plural display name (e.g., 'AS_GSM_Addresses')
            - version_uuid: Version UUID
            - description: Record Type description
            - fields: List of field definitions (with display_name)
            - relationships: List of relationship definitions
            - views: List of view configurations
            - actions: List of record actions
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        ns = {'a': 'http://www.appian.com/ae/types/2009'}

        # Find the recordType element
        record_type_elem = root.find('.//recordType', ns)
        if record_type_elem is None:
            record_type_elem = root.find('.//a:recordType', ns)
        if record_type_elem is None:
            raise ValueError(f"No recordType element found in {xml_path}")

        # Extract basic info including plural_name for reference resolution
        data = {
            'uuid': record_type_elem.get('{http://www.appian.com/ae/types/2009}uuid') or record_type_elem.get('uuid'),
            'name': record_type_elem.get('name'),
            'plural_name': self._get_text(record_type_elem, 'a:pluralName', ns),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(record_type_elem, 'a:description', ns),
            # Source configuration
            'source': self._get_text(record_type_elem, 'a:source', ns),
            'security_type': self._get_text(record_type_elem, 'a:security', ns),
            # Display & identity
            'title_expr': self._get_text(record_type_elem, 'a:titleExpr', ns),
            'url_stub': self._get_text(record_type_elem, 'a:urlStub', ns),
            'icon_id': self._get_text(record_type_elem, 'a:iconId', ns),
            'layout_type': self._get_text(record_type_elem, 'a:layoutType', ns),
            # Filters & search
            'default_filters_expr': self._clean_sail_code(
                self._get_text(record_type_elem, 'a:defaultFiltersExpr', ns)
            ),
            'facets_list_expr': self._clean_sail_code(
                self._get_text(record_type_elem, 'a:facetsListExpr', ns)
            ),
            # List / data source expressions
            'list_view_src_expr': self._clean_sail_code(
                self._get_text(record_type_elem, 'a:listViewSrcExpr', ns)
            ),
            'data_src_expr': self._clean_sail_code(
                self._get_text(record_type_elem, 'a:dataSrcExpr', ns)
            ),
            # Flags
            'hide_news_view': self._get_text(record_type_elem, 'a:hideNewsView', ns) == 'true',
            'hide_latest_news': self._get_text(record_type_elem, 'a:hideLatestNews', ns) == 'true',
            'record_action_launch_type': self._get_text(record_type_elem, 'a:recordActionLaunchType', ns),
        }

        # Extract source configuration metadata
        source_config = record_type_elem.find('a:sourceConfiguration', ns)
        if source_config is not None:
            data['source_type'] = self._get_text(source_config, 'sourceType')
            data['source_uuid'] = self._get_text(source_config, 'sourceUuid')
            data['source_context_expr'] = self._clean_sail_code(
                self._get_text(source_config, 'sourceContextExpr')
            )
            data['source_filter_expr'] = self._clean_sail_code(
                self._get_text(source_config, 'sourceFilterExpr')
            )
        else:
            data['source_type'] = None
            data['source_uuid'] = None
            data['source_context_expr'] = None
            data['source_filter_expr'] = None

        # Extract fields from sourceConfiguration (with display_name)
        data['fields'] = self._extract_fields(record_type_elem, ns)

        # Extract relationships
        data['relationships'] = self._extract_relationships(record_type_elem, ns)

        # Extract views
        data['views'] = self._extract_views(record_type_elem, ns)

        # Extract actions (record actions)
        data['actions'] = self._extract_actions(record_type_elem, ns)

        return data

    def _get_text(self, element: ET.Element, path: str, ns: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Get text content from an XML element by path.

        Args:
            element: Parent XML element
            path: XPath to the target element
            ns: Namespace dict (optional)

        Returns:
            Text content of the element, or None if element not found
        """
        if ns:
            elem = element.find(path, ns)
        else:
            elem = element.find(path)
        return elem.text if elem is not None and elem.text else None

    def _extract_fields(self, record_type_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract field definitions from record type.

        Enhanced to include display_name for human-readable field resolution
        in SAIL code URNs and to resolve field types to user-friendly names.

        Args:
            record_type_elem: Record type XML element
            ns: Namespace dict

        Returns:
            List of field dictionaries with:
            - field_uuid: UUID of the field
            - field_name: Programmatic name (e.g., 'addressId')
            - display_name: Human-readable name (e.g., 'Address Id')
            - field_type: Resolved data type (user-friendly)
            - raw_field_type: Original data type from XML
            - source_field_name: Database column name
            - source_field_type: Database column type
            - is_record_id: Whether this is the primary key
            - is_unique: Whether the field has unique constraint
            - is_custom_field: Whether this is a custom field
            - display_order: Order for UI display
        """
        fields = []

        source_config = record_type_elem.find('a:sourceConfiguration', ns)
        if source_config is None:
            return fields

        for field_elem in source_config.findall('field'):
            field_uuid = self._get_text(field_elem, 'uuid')
            field_name = self._get_text(field_elem, 'fieldName')
            display_name = self._get_text(field_elem, 'displayName')
            raw_field_type = self._get_text(field_elem, 'type')

            # Store raw type - will be resolved in post-extraction
            # with record type cache
            field_type = raw_field_type

            source_field_name = self._get_text(field_elem, 'sourceFieldName')
            source_field_type = self._get_text(field_elem, 'sourceFieldType')

            is_record_id = self._get_text(field_elem, 'isRecordId') == 'true'
            is_unique = self._get_text(field_elem, 'isUnique') == 'true'
            is_custom = self._get_text(field_elem, 'isCustomField') == 'true'

            field = {
                'field_uuid': field_uuid,
                'field_name': field_name,
                'display_name': display_name,
                'field_type': field_type,
                'raw_field_type': raw_field_type,
                'source_field_name': source_field_name,
                'source_field_type': source_field_type,
                'is_record_id': is_record_id,
                'is_unique': is_unique,
                'is_custom_field': is_custom,
                'is_hidden': self._get_text(field_elem, 'isHidden') == 'true',
                'description': self._get_text(field_elem, 'description'),
                'field_format': self._get_text(field_elem, 'fieldFormat'),
                'custom_field_expr': self._clean_sail_code(
                    self._get_text(field_elem, 'customFieldExpr')
                ),
                'display_order': len(fields)
            }

            fields.append(field)

        return fields

    def _extract_relationships(self, record_type_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract relationship definitions from record type.

        Args:
            record_type_elem: Record type XML element
            ns: Namespace dict

        Returns:
            List of relationship dictionaries
        """
        relationships = []

        for rel_elem in record_type_elem.findall('a:recordRelationshipCfg', ns):
            rel_uuid = self._get_text(rel_elem, 'uuid')
            rel_name = self._get_text(rel_elem, 'relationshipName')
            target_record_type = self._get_text(rel_elem, 'targetRecordTypeUuid')
            rel_type = self._get_text(rel_elem, 'relationshipType')
            rel_data = self._get_text(rel_elem, 'relationshipData')

            relationship = {
                'relationship_uuid': rel_uuid,
                'relationship_name': rel_name,
                'target_record_type_uuid': target_record_type,
                'relationship_type': rel_type,
                'relationship_data': rel_data,
                'display_order': len(relationships)
            }

            relationships.append(relationship)

        return relationships

    def _extract_views(self, record_type_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract view configurations from record type.

        Args:
            record_type_elem: Record type XML element
            ns: Namespace dict

        Returns:
            List of view dictionaries
        """
        views = []

        # Extract all detail view configurations (tabs on the record summary page)
        for detail_view in record_type_elem.findall('a:detailViewCfg', ns):
            view_name = self._get_text(detail_view, 'a:nameExpr', ns)
            url_stub = self._get_text(detail_view, 'a:urlStub', ns)
            visibility = self._get_text(detail_view, 'a:visibilityExpr', ns)
            ui_expr = self._get_text(detail_view, 'a:uiExpr', ns)

            views.append({
                'view_type': 'DETAIL',
                'view_name': view_name,
                'url_stub': url_stub,
                'visibility_expr': self._clean_sail_code(visibility) or visibility,
                'ui_expr': self._clean_sail_code(ui_expr) or ui_expr,
                'display_order': len(views)
            })

        # Extract record header expression
        record_view_src = self._get_text(record_type_elem, 'a:recordViewSrcExpr', ns)
        if record_view_src:
            views.insert(0, {
                'view_type': 'HEADER',
                'view_name': 'Record Header',
                'url_stub': None,
                'visibility_expr': None,
                'ui_expr': self._clean_sail_code(record_view_src) or record_view_src,
                'display_order': 0,
            })
            # Re-number display_order
            for i, v in enumerate(views):
                v['display_order'] = i

        # Extract list view template
        list_view_expr = self._get_text(record_type_elem, 'a:listViewTemplateExpr', ns)
        if list_view_expr:
            views.append({
                'view_type': 'LIST',
                'view_name': 'List View',
                'url_stub': None,
                'visibility_expr': None,
                'ui_expr': self._clean_sail_code(list_view_expr) or list_view_expr,
                'display_order': len(views)
            })

        return views

    def _extract_actions(self, record_type_elem: ET.Element, ns: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extract all record action definitions from record type.

        Extracts both:
        - Record List Actions (<a:recordListActionCfg>): Actions available from the record list view
        - Record Actions (<a:relatedActionCfg>): Actions available from individual record views

        Args:
            record_type_elem: Record type XML element
            ns: Namespace dict

        Returns:
            List of action dictionaries with full metadata and expressions
        """
        actions = []

        # Extract Record List Actions (<a:recordListActionCfg>)
        for action_elem in record_type_elem.findall('a:recordListActionCfg', ns):
            action = self._parse_record_list_action(action_elem, ns, len(actions))
            if action:
                actions.append(action)

        # Extract Record Actions / Related Actions (<a:relatedActionCfg>)
        for action_elem in record_type_elem.findall('a:relatedActionCfg', ns):
            action = self._parse_record_action(action_elem, ns, len(actions))
            if action:
                actions.append(action)

        return actions

    def _parse_record_list_action(self, action_elem: ET.Element, ns: Dict[str, str], order: int) -> Dict[str, Any]:
        """
        Parse a Record List Action element (<a:recordListActionCfg>).

        Record List Actions are actions available from the record list view,
        such as "Create New" buttons.

        Args:
            action_elem: XML element for the action
            ns: Namespace dict
            order: Display order index

        Returns:
            Dictionary with action metadata and expressions
        """
        # Get action UUID from attribute
        action_uuid = action_elem.get('{http://www.appian.com/ae/types/2009}uuid')

        # Extract target process model
        target_elem = action_elem.find('a:target', ns)
        target_uuid = None
        if target_elem is not None:
            target_uuid = target_elem.get('{http://www.appian.com/ae/types/2009}uuid')

        return {
            'action_uuid': action_uuid,
            'action_type': 'RECORD_LIST_ACTION',
            'reference_key': self._get_text(action_elem, 'a:referenceKey', ns) or 'unknown',
            'target_uuid': target_uuid,
            'icon_id': self._get_text(action_elem, 'a:iconId', ns),
            'dialog_size': self._get_text(action_elem, 'a:dialogSize', ns),
            'dialog_width': self._get_text(action_elem, 'a:dialogWidth', ns),
            'dialog_height': self._get_text(action_elem, 'a:dialogHeight', ns),
            'show_in_record_list': self._get_text(action_elem, 'a:showInRecordList', ns) == 'true',
            'record_ui_security_type': self._get_text(action_elem, 'a:recordUiSecurityType', ns),
            'display_order': order,
            'expressions': {
                'TITLE': self._clean_sail_code(self._get_text(action_elem, 'a:titleExpr', ns)),
                'DESCRIPTION': self._get_text(action_elem, 'a:staticDescription', ns),
                'VISIBILITY': self._clean_sail_code(self._get_text(action_elem, 'a:visibilityExpr', ns)),
            }
        }

    def _parse_record_action(self, action_elem: ET.Element, ns: Dict[str, str], order: int) -> Dict[str, Any]:
        """
        Parse a Record Action element (<a:relatedActionCfg>).

        Record Actions are actions available from individual record views,
        such as "Edit", "Add Vendor", etc.

        Args:
            action_elem: XML element for the action
            ns: Namespace dict
            order: Display order index

        Returns:
            Dictionary with action metadata and expressions
        """
        # Get action UUID from attribute
        action_uuid = action_elem.get('{http://www.appian.com/ae/types/2009}uuid')

        # Extract target process model
        target_elem = action_elem.find('a:target', ns)
        target_uuid = None
        if target_elem is not None:
            target_uuid = target_elem.get('{http://www.appian.com/ae/types/2009}uuid')

        # Get description - try descriptionExpr first, then staticDescriptionString
        description = self._get_text(action_elem, 'a:descriptionExpr', ns)
        if not description:
            description = self._get_text(action_elem, 'a:staticDescriptionString', ns)

        return {
            'action_uuid': action_uuid,
            'action_type': 'RECORD_ACTION',
            'reference_key': self._get_text(action_elem, 'a:referenceKey', ns) or 'unknown',
            'target_uuid': target_uuid,
            'icon_id': self._get_text(action_elem, 'a:iconId', ns),
            'dialog_size': self._get_text(action_elem, 'a:dialogSize', ns),
            'dialog_width': self._get_text(action_elem, 'a:dialogWidth', ns),
            'dialog_height': self._get_text(action_elem, 'a:dialogHeight', ns),
            'show_in_record_list': self._get_text(action_elem, 'a:showInRecordList', ns) == 'true',
            'record_ui_security_type': self._get_text(action_elem, 'a:recordUiSecurityType', ns),
            'display_order': order,
            'expressions': {
                'TITLE': self._clean_sail_code(self._get_text(action_elem, 'a:titleExpr', ns)),
                'DESCRIPTION': self._clean_sail_code(description),
                'VISIBILITY': self._clean_sail_code(self._get_text(action_elem, 'a:visibilityExpr', ns)),
                'CONTEXT': self._clean_sail_code(self._get_text(action_elem, 'a:contextExpr', ns)),
            }
        }
