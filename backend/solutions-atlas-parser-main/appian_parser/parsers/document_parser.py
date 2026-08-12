"""Parser for Appian Document objects.

Extracts metadata from document XML files in the content/ directory.
Documents are binary assets (images, icons) uploaded to Appian and
referenced via constants in SAIL code.
"""

from typing import Dict, Any
import xml.etree.ElementTree as ET

from appian_parser.parsers.base_parser import BaseParser


class DocumentParser(BaseParser):
    """Parser for Appian Document objects.

    Extracts name, UUID, description, filename, and parent folder
    from document XML files.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """Parse document XML and extract metadata.

        Args:
            xml_path: Path to the document XML file

        Returns:
            Dict containing uuid, name, description, filename,
            parent_uuid, and version_uuid.
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        doc_elem = root.find('.//document')
        if doc_elem is None:
            raise ValueError(f"No document element found in {xml_path}")

        return {
            'uuid': self._get_text(doc_elem, 'uuid'),
            'name': self._get_text(doc_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(doc_elem, 'description'),
            'parent_uuid': self._get_text(doc_elem, 'parentUuid'),
            'filename': self._get_text(root, './/file'),
        }
