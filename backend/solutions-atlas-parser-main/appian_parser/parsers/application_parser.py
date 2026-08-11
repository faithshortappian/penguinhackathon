"""Parser for Appian Application objects."""

from typing import Dict, Any, List
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class ApplicationParser(BaseParser):
    """Extracts application metadata and associated object UUIDs."""

    def parse(self, xml_path: str) -> Dict[str, Any]:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        app_elem = root.find('.//application')
        if app_elem is None:
            raise ValueError(f"No application element found in {xml_path}")

        data = {
            'uuid': self._get_text(app_elem, 'uuid'),
            'name': self._get_text(app_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(app_elem, 'description'),
            'url_identifier': self._get_text(app_elem, 'urlIdentifier'),
            'prefix': self._get_text(app_elem, 'prefix'),
            'is_published': self._get_text(app_elem, 'published') == 'true',
            'is_public': self._get_text(app_elem, 'public') == 'true',
            'associated_object_uuids': self._extract_associated_objects(app_elem),
        }
        return data

    def _extract_associated_objects(self, app_elem: ET.Element) -> List[str]:
        uuids = []
        assoc = app_elem.find('associatedObjects')
        if assoc is None:
            return uuids
        global_id_map = assoc.find('globalIdMap')
        if global_id_map is None:
            return uuids
        for item in global_id_map.findall('item'):
            uuids_elem = item.find('uuids')
            if uuids_elem is not None:
                for uuid_elem in uuids_elem.findall('uuid'):
                    if uuid_elem.text:
                        uuids.append(uuid_elem.text.strip())
        return uuids
