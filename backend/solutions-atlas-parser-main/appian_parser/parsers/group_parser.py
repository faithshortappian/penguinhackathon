"""
Parser for Appian Group objects.

This module provides the GroupParser class for extracting data from
Group XML files.
"""

from typing import Dict, Any, List
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class GroupParser(BaseParser):
    """
    Parser for Appian Group objects.

    Extracts group members and parent group information from Group XML files.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Group XML file and extract all relevant data.

        Args:
            xml_path: Path to the Group XML file

        Returns:
            Dict containing:
            - uuid: Group UUID
            - name: Group name
            - version_uuid: Version UUID
            - description: Group description
            - members: List of group member UUIDs
            - parent_group_uuid: Parent group UUID (if any)
            - group_type: Type of group
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the group element
        group_elem = root.find('.//group')
        if group_elem is None:
            raise ValueError(f"No group element found in {xml_path}")

        # Extract basic info - UUID and name are child elements
        data = {
            'uuid': self._get_text(group_elem, 'uuid'),
            'name': self._get_text(group_elem, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(group_elem, 'description')
        }

        # Extract parent group
        data['parent_group_uuid'] = self._get_text(
            group_elem, 'parentGroupUuid'
        )

        # Extract group type
        data['group_type'] = self._get_text(group_elem, 'groupTypeUuid')

        # Extract members (from root, not group_elem)
        data['members'] = self._extract_members(root)

        return data

    def _extract_members(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract group members from root element.

        Args:
            root: Root XML element (groupHaul)

        Returns:
            List of member dictionaries with user/group UUIDs
        """
        members = []

        # Members is at root level, not inside group element
        members_elem = root.find('.//members')
        if members_elem is None:
            return members

        # Extract user members from <users> section
        users_elem = members_elem.find('users')
        if users_elem is not None:
            for user_elem in users_elem.findall('userUuid'):
                user_uuid = user_elem.text
                if user_uuid:
                    members.append({
                        'member_type': 'USER',
                        'member_uuid': user_uuid.strip(),
                        'display_order': len(members)
                    })

        # Extract group members from <groups> section
        groups_elem = members_elem.find('groups')
        if groups_elem is not None:
            for group_elem in groups_elem.findall('groupUuid'):
                group_uuid = group_elem.text
                if group_uuid:
                    members.append({
                        'member_type': 'GROUP',
                        'member_uuid': group_uuid.strip(),
                        'display_order': len(members)
                    })

        return members
