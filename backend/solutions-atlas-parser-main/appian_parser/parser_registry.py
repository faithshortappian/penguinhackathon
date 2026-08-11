"""Parser registry for Appian object types."""

from appian_parser.parsers.base_parser import BaseParser
from appian_parser.parsers.unknown_object_parser import UnknownObjectParser


class ParserRegistry:
    """Registry mapping object types to parser instances."""

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {}
        self._unknown_parser = UnknownObjectParser()
        self._register_default_parsers()

    def _register_default_parsers(self) -> None:
        from appian_parser.parsers.interface_parser import InterfaceParser
        from appian_parser.parsers.expression_rule_parser import ExpressionRuleParser
        from appian_parser.parsers.process_model_parser import ProcessModelParser
        from appian_parser.parsers.record_type_parser import RecordTypeParser
        from appian_parser.parsers.cdt_parser import CDTParser
        from appian_parser.parsers.integration_parser import IntegrationParser
        from appian_parser.parsers.web_api_parser import WebAPIParser
        from appian_parser.parsers.site_parser import SiteParser
        from appian_parser.parsers.group_parser import GroupParser
        from appian_parser.parsers.constant_parser import ConstantParser
        from appian_parser.parsers.connected_system_parser import ConnectedSystemParser
        from appian_parser.parsers.control_panel_parser import ControlPanelParser
        from appian_parser.parsers.translation_set_parser import TranslationSetParser
        from appian_parser.parsers.translation_string_parser import TranslationStringParser
        from appian_parser.parsers.data_store_parser import DataStoreParser
        from appian_parser.parsers.application_parser import ApplicationParser
        from appian_parser.parsers.document_parser import DocumentParser
        from appian_parser.parsers.folder_parser import FolderParser
        from appian_parser.parsers.ai_skill_parser import AISkillParser
        from appian_parser.parsers.decision_parser import DecisionParser

        self.register_parser('Interface', InterfaceParser())
        self.register_parser('Expression Rule', ExpressionRuleParser())
        self.register_parser('Process Model', ProcessModelParser())
        self.register_parser('Record Type', RecordTypeParser())
        self.register_parser('CDT', CDTParser())
        self.register_parser('Data Type', CDTParser())
        self.register_parser('Integration', IntegrationParser())
        self.register_parser('Web API', WebAPIParser())
        self.register_parser('Site', SiteParser())
        self.register_parser('Group', GroupParser())
        self.register_parser('Constant', ConstantParser())
        self.register_parser('Connected System', ConnectedSystemParser())
        self.register_parser('Control Panel', ControlPanelParser())
        self.register_parser('Translation Set', TranslationSetParser())
        self.register_parser('Translation String', TranslationStringParser())
        self.register_parser('Data Store', DataStoreParser())
        self.register_parser('Application', ApplicationParser())
        self.register_parser('Document', DocumentParser())
        self.register_parser('Folder', FolderParser())
        self.register_parser('AI Skill', AISkillParser())
        self.register_parser('Decision', DecisionParser())

    def get_parser(self, object_type: str) -> BaseParser:
        return self._parsers.get(object_type, self._unknown_parser)

    def register_parser(self, object_type: str, parser: BaseParser) -> None:
        self._parsers[object_type] = parser

    def get_supported_types(self) -> list[str]:
        return list(self._parsers.keys())
