"""Type detection for Appian XML objects."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class TypeDetectionResult:
    mapped_type: str
    raw_tag: str
    is_excluded: bool
    is_unknown: bool


class TypeDetector:
    """Determines Appian object type from XML file structure."""

    TAG_TYPE_MAP = {
        'interfaceHaul': 'Interface',
        'expressionRuleHaul': 'Expression Rule',
        'processModelHaul': 'Process Model',
        'recordTypeHaul': 'Record Type',
        'dataTypeHaul': 'CDT',
        'integrationHaul': 'Integration',
        'webApiHaul': 'Web API',
        'siteHaul': 'Site',
        'groupHaul': 'Group',
        'constantHaul': 'Constant',
        'connectedSystemHaul': 'Connected System',
        'controlPanelHaul': 'Control Panel',
        'translationSetHaul': 'Translation Set',
        'translationStringHaul': 'Translation String',
        'aiSkillRemoteHaul': 'AI Skill',
        'dataStoreHaul': 'Data Store',
        'applicationHaul': 'Application',
        'interface': 'Interface',
        'expressionRule': 'Expression Rule',
        'processModel': 'Process Model',
        'recordType': 'Record Type',
        'dataType': 'CDT',
        'integration': 'Integration',
        'webApi': 'Web API',
        'site': 'Site',
        'group': 'Group',
        'constant': 'Constant',
        'connectedSystem': 'Connected System',
        'controlPanel': 'Control Panel',
        'translationSet': 'Translation Set',
        'translationString': 'Translation String',
    }

    CONTENT_HAUL_CHILD_MAP = {
        'interface': 'Interface',
        'expressionRule': 'Expression Rule',
        'rule': 'Expression Rule',
        'constant': 'Constant',
        'integration': 'Integration',
        'outboundIntegration': 'Integration',
        'webApi': 'Web API',
        'controlPanel': 'Control Panel',
        'translationSet': 'Translation Set',
        'translationString': 'Translation String',
        'rulesFolder': 'Folder',
        'dataStore': 'Data Store',
        'application': 'Application',
        'communityKnowledgeCenter': 'Folder',
        'document': 'Document',
        'folder': 'Folder',
        'decision': 'Decision',
    }

    DEFAULT_EXCLUDED = {
        'report', 'groupType', 'file',
    }

    def __init__(self, excluded_types: set[str] | None = None):
        self.excluded_types = excluded_types or self.DEFAULT_EXCLUDED

    def detect(self, xml_path: str) -> TypeDetectionResult:
        if xml_path.endswith('.xsd'):
            return TypeDetectionResult('CDT', 'xsd', False, False)

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            tag = root.tag
            if '}' in tag:
                tag = tag.split('}')[1]

            if tag == 'contentHaul':
                return self._detect_content_haul(root)

            mapped = self.TAG_TYPE_MAP.get(tag)
            if mapped:
                return TypeDetectionResult(mapped, tag, tag in self.excluded_types, False)

            return TypeDetectionResult('Unknown', tag, tag in self.excluded_types, True)

        except Exception:
            return TypeDetectionResult('Unknown', 'unknown', False, True)

    def _detect_content_haul(self, root: ET.Element) -> TypeDetectionResult:
        for child in root:
            child_tag = child.tag
            if '}' in child_tag:
                child_tag = child_tag.split('}')[1]
            if child_tag in self.CONTENT_HAUL_CHILD_MAP:
                mapped = self.CONTENT_HAUL_CHILD_MAP[child_tag]
                is_unknown = mapped == 'Unknown'
                return TypeDetectionResult(
                    mapped, child_tag, child_tag in self.excluded_types, is_unknown
                )
        return TypeDetectionResult('Unknown', 'contentHaul', False, True)
