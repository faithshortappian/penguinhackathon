"""Tests for parser modules."""

import pytest

from appian_parser.parsers.constant_parser import ConstantParser
from appian_parser.parsers.group_parser import GroupParser
from appian_parser.parsers.interface_parser import InterfaceParser
from appian_parser.parsers.expression_rule_parser import ExpressionRuleParser
from appian_parser.parser_registry import ParserRegistry
from tests.conftest import CONSTANT_XML, INTERFACE_XML, EXPRESSION_RULE_XML, GROUP_XML


class TestConstantParser:
    """Tests for ConstantParser."""

    def setup_method(self):
        self.parser = ConstantParser()

    def test_parse_extracts_uuid(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert data['uuid'] == '_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774'

    def test_parse_extracts_name(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert data['name'] == 'MY_CONSTANT'

    def test_parse_extracts_value(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert data['value'] == '42'

    def test_parse_extracts_description(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert data['description'] == 'A test constant'

    def test_parse_extracts_scope(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert data['scope'] == 'APPLICATION'

    def test_parse_extracts_value_type(self, tmp_xml):
        data = self.parser.parse(tmp_xml(CONSTANT_XML))
        assert 'int' in data['value_type']

    def test_parse_missing_constant_raises(self, tmp_xml):
        path = tmp_xml('<?xml version="1.0"?><constantHaul></constantHaul>')
        with pytest.raises(ValueError):
            self.parser.parse(path)


class TestGroupParser:
    """Tests for GroupParser."""

    def setup_method(self):
        self.parser = GroupParser()

    def test_parse_extracts_uuid(self, tmp_xml):
        data = self.parser.parse(tmp_xml(GROUP_XML))
        assert data['uuid'] == '_a-0000aaaa-bbbb-cccc-dddd-eeeeffffaaaa_200'

    def test_parse_extracts_members(self, tmp_xml):
        data = self.parser.parse(tmp_xml(GROUP_XML))
        assert len(data['members']) == 2
        types = {m['member_type'] for m in data['members']}
        assert types == {'USER', 'GROUP'}

    def test_parse_extracts_parent_group(self, tmp_xml):
        data = self.parser.parse(tmp_xml(GROUP_XML))
        assert data['parent_group_uuid'] == '_a-0000bbbb-cccc-dddd-eeee-ffffaaaabbbb_201'


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def test_get_parser_returns_correct_type(self):
        registry = ParserRegistry()
        parser = registry.get_parser('Constant')
        assert isinstance(parser, ConstantParser)

    def test_get_parser_unknown_returns_fallback(self):
        registry = ParserRegistry()
        parser = registry.get_parser('NonexistentType')
        assert parser is not None  # Returns UnknownObjectParser

    def test_get_supported_types_includes_all(self):
        registry = ParserRegistry()
        types = registry.get_supported_types()
        assert 'Interface' in types
        assert 'Expression Rule' in types
        assert 'Process Model' in types
        assert 'Record Type' in types
        assert 'Constant' in types

    def test_register_custom_parser(self):
        registry = ParserRegistry()
        custom = ConstantParser()
        registry.register_parser('Custom', custom)
        assert registry.get_parser('Custom') is custom
