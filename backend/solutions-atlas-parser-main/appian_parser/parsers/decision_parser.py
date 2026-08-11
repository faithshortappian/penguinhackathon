"""Parser for Appian Decision objects.

Extracts metadata and decision logic from decision table XML files.
"""

from typing import Dict, Any
import xml.etree.ElementTree as ET

from appian_parser.parsers.base_parser import BaseParser


class DecisionParser(BaseParser):
    """Parser for Appian Decision objects (decision tables).

    Extracts uuid, name, description, and the decision definition
    containing the business logic/rules.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """Parse Decision XML and extract metadata + definition.

        Args:
            xml_path: Path to the Decision XML file

        Returns:
            Dict containing uuid, name, description, version_uuid,
            parent_uuid, and definition (the SAIL decision logic).
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        decision_elem = root.find('.//decision')
        if decision_elem is None:
            raise ValueError(f"No decision element found in {xml_path}")

        return {
            'uuid': self._get_text(decision_elem, 'uuid'),
            'name': self._get_text(decision_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(decision_elem, 'description'),
            'parent_uuid': self._get_text(decision_elem, 'parentUuid'),
            'definition': self._clean_sail_code(
                self._get_text(decision_elem, 'definition')
            ),
        }
