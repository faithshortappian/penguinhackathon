"""Tests for TypeDetector."""

import pytest

from appian_parser.type_detector import TypeDetector


class TestTypeDetector:
    """Tests for XML type detection."""

    def setup_method(self):
        self.detector = TypeDetector()

    def test_detect_constant_haul(self, tmp_xml):
        from tests.conftest import CONSTANT_XML
        path = tmp_xml(CONSTANT_XML)
        result = self.detector.detect(path)
        assert result.mapped_type == 'Constant'
        assert not result.is_unknown
        assert not result.is_excluded

    def test_detect_interface_haul(self, tmp_xml):
        from tests.conftest import INTERFACE_XML
        path = tmp_xml(INTERFACE_XML)
        result = self.detector.detect(path)
        assert result.mapped_type == 'Interface'

    def test_detect_expression_rule_haul(self, tmp_xml):
        from tests.conftest import EXPRESSION_RULE_XML
        path = tmp_xml(EXPRESSION_RULE_XML)
        result = self.detector.detect(path)
        assert result.mapped_type == 'Expression Rule'

    def test_detect_group_haul(self, tmp_xml):
        from tests.conftest import GROUP_XML
        path = tmp_xml(GROUP_XML)
        result = self.detector.detect(path)
        assert result.mapped_type == 'Group'

    def test_detect_content_haul_constant(self, tmp_xml):
        from tests.conftest import CONTENT_HAUL_CONSTANT_XML
        path = tmp_xml(CONTENT_HAUL_CONSTANT_XML)
        result = self.detector.detect(path)
        assert result.mapped_type == 'Constant'

    def test_detect_xsd_as_cdt(self, tmp_path):
        path = tmp_path / "test.xsd"
        path.write_text("<xs:schema/>")
        result = self.detector.detect(str(path))
        assert result.mapped_type == 'CDT'

    def test_detect_unknown_tag(self, tmp_xml):
        path = tmp_xml('<?xml version="1.0"?><unknownTag/>')
        result = self.detector.detect(path)
        assert result.is_unknown

    def test_detect_excluded_type(self):
        detector = TypeDetector(excluded_types={'constantHaul'})
        # The excluded check is on the raw tag
        assert 'constantHaul' in detector.excluded_types

    def test_detect_invalid_xml(self, tmp_xml):
        path = tmp_xml("not xml at all")
        result = self.detector.detect(path)
        assert result.mapped_type == 'Unknown'
        assert result.is_unknown

    def test_all_haul_types_mapped(self):
        """Verify all expected haul types are in the tag map."""
        expected = [
            'interfaceHaul', 'expressionRuleHaul', 'processModelHaul',
            'recordTypeHaul', 'dataTypeHaul', 'integrationHaul',
            'webApiHaul', 'siteHaul', 'groupHaul', 'constantHaul',
            'connectedSystemHaul', 'controlPanelHaul',
            'translationSetHaul', 'translationStringHaul',
        ]
        for tag in expected:
            assert tag in TypeDetector.TAG_TYPE_MAP, f"Missing: {tag}"
