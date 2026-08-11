"""Parser for Appian AI Skill objects.

Extracts metadata and configuration from aiSkillRemoteHaul XML files.
"""

import json
from typing import Dict, Any
import xml.etree.ElementTree as ET

from appian_parser.parsers.base_parser import BaseParser


class AISkillParser(BaseParser):
    """Parser for Appian AI Skill objects.

    Extracts uuid, name, description, and the JSON configuration
    containing model settings, prompts, and parameters.
    """

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """Parse AI Skill XML and extract metadata + config.

        Args:
            xml_path: Path to the AI Skill XML file

        Returns:
            Dict containing uuid, name, description, version_uuid,
            skill_type, models, and raw config.
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        design_obj = root.find('.//remoteDesignObject')
        if design_obj is None:
            raise ValueError(f"No remoteDesignObject element found in {xml_path}")

        data = {
            'uuid': self._get_text(design_obj, 'uuid'),
            'name': self._get_text(design_obj, 'name'),
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(design_obj, 'description'),
        }

        # Parse the JSON content (contains skill type, models, prompts).
        content_text = self._get_text(design_obj, 'content')
        if content_text:
            try:
                config = json.loads(content_text)
                data['skill_type'] = config.get('ai_skill_type')
                data['models'] = config.get('models', [])
            except (json.JSONDecodeError, TypeError):
                data['skill_type'] = None
                data['models'] = []
        else:
            data['skill_type'] = None
            data['models'] = []

        return data
