"""Parser for Appian Folder objects.

Handles folder, rulesFolder, and communityKnowledgeCenter types.
These are organizational containers in the Appian object hierarchy.
"""

from typing import Dict, Any
import xml.etree.ElementTree as ET

from appian_parser.parsers.base_parser import BaseParser


class FolderParser(BaseParser):
    """Parser for Appian folder-type objects.

    Works for folder, rulesFolder, and communityKnowledgeCenter —
    all share the same XML structure (name, uuid, description, parentUuid).
    """

    # Tags that represent folder-like containers.
    _FOLDER_TAGS = ('folder', 'rulesFolder', 'communityKnowledgeCenter')

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """Parse folder XML and extract metadata.

        Args:
            xml_path: Path to the folder XML file

        Returns:
            Dict containing uuid, name, description, parent_uuid,
            folder_type, and version_uuid.
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the folder element (could be any of the folder tags).
        folder_elem = None
        folder_type = None
        for tag in self._FOLDER_TAGS:
            folder_elem = root.find(f'.//{tag}')
            if folder_elem is not None:
                folder_type = tag
                break

        if folder_elem is None:
            raise ValueError(f"No folder element found in {xml_path}")

        return {
            'uuid': self._get_text(folder_elem, 'uuid'),
            'name': self._get_text(folder_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(folder_elem, 'description'),
            'parent_uuid': self._get_text(folder_elem, 'parentUuid'),
            'folder_type': folder_type,
        }
