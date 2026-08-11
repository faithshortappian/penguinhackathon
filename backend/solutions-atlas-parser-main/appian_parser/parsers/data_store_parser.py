"""Parser for Appian Data Store objects."""

from typing import Dict, Any, List
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class DataStoreParser(BaseParser):
    """Extracts data store configuration including entities (CDT-to-table mappings)."""

    def parse(self, xml_path: str) -> Dict[str, Any]:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        ds_elem = root.find('.//dataStore')
        if ds_elem is None:
            raise ValueError(f"No dataStore element found in {xml_path}")

        data = {
            'uuid': self._get_text(ds_elem, 'uuid'),
            'name': self._get_text(ds_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(ds_elem, 'description'),
            'data_source_key': self._get_text(ds_elem, 'dataSourceKey'),
            'auto_update_schema': self._get_text(ds_elem, 'autoUpdateSchema') == 'true',
            'adapting_explicit_sql_names': self._get_text(ds_elem, 'adaptingExplicitSqlNames') == 'true',
            'entities': self._extract_entities(ds_elem),
            'security': self._extract_role_map(root),
        }
        return data

    def _extract_entities(self, ds_elem: ET.Element) -> List[Dict[str, Any]]:
        entities = []
        entities_elem = ds_elem.find('entities')
        if entities_elem is None:
            return entities
        for i, entity_elem in enumerate(entities_elem.findall('entity')):
            entities.append({
                'entity_uuid': self._get_text(entity_elem, 'uuid'),
                'entity_name': self._get_text(entity_elem, 'name'),
                'cdt_type': self._get_text(entity_elem, 'type'),
                'display_order': i,
            })
        return entities
