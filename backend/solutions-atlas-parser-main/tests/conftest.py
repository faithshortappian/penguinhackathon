"""Shared test fixtures."""

import os
import json
import tempfile
import zipfile

import pytest

from appian_parser.output.json_dumper import ParsedObject


# ── Sample XML Content ───────────────────────────────────────────────────

CONSTANT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<constantHaul>
  <versionUuid>ver-001</versionUuid>
  <constant uuid="_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774" name="MY_CONSTANT">
    <uuid>_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774</uuid>
    <name>MY_CONSTANT</name>
    <description>A test constant</description>
    <typedValue>
      <type><name>int</name><namespace>http://www.w3.org/2001/XMLSchema</namespace></type>
      <value>42</value>
    </typedValue>
    <scope>APPLICATION</scope>
  </constant>
</constantHaul>
"""

INTERFACE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<interfaceHaul>
  <versionUuid>ver-002</versionUuid>
  <interface uuid="_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398" name="MyInterface">
    <uuid>_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398</uuid>
    <name>MyInterface</name>
    <description>A test interface</description>
    <definition>a!formLayout(label: "Test")</definition>
  </interface>
</interfaceHaul>
"""

EXPRESSION_RULE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<expressionRuleHaul>
  <versionUuid>ver-003</versionUuid>
  <rule uuid="_a-00001111-2222-3333-4444-555566667777_100" name="MyRule">
    <uuid>_a-00001111-2222-3333-4444-555566667777_100</uuid>
    <name>MyRule</name>
    <description>A test rule</description>
    <definition>1 + 1</definition>
  </rule>
</expressionRuleHaul>
"""

GROUP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<groupHaul>
  <versionUuid>ver-004</versionUuid>
  <group uuid="_a-0000aaaa-bbbb-cccc-dddd-eeeeffffaaaa_200" name="TestGroup">
    <uuid>_a-0000aaaa-bbbb-cccc-dddd-eeeeffffaaaa_200</uuid>
    <name>TestGroup</name>
    <description>A test group</description>
    <parentGroupUuid>_a-0000bbbb-cccc-dddd-eeee-ffffaaaabbbb_201</parentGroupUuid>
    <groupTypeUuid>gt-001</groupTypeUuid>
  </group>
  <members>
    <users>
      <userUuid>user-001</userUuid>
    </users>
    <groups>
      <groupUuid>group-001</groupUuid>
    </groups>
  </members>
</groupHaul>
"""

CONTENT_HAUL_CONSTANT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<contentHaul>
  <constant uuid="_a-0000cccc-dddd-eeee-ffff-aaaabbbbcccc_300" name="WrappedConstant">
    <uuid>_a-0000cccc-dddd-eeee-ffff-aaaabbbbcccc_300</uuid>
    <name>WrappedConstant</name>
    <typedValue>
      <type><name>string</name><namespace>http://www.w3.org/2001/XMLSchema</namespace></type>
      <value>hello</value>
    </typedValue>
  </constant>
</contentHaul>
"""


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_xml(tmp_path):
    """Write XML content to a temp file and return its path."""
    def _write(content: str, filename: str = "test.xml") -> str:
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return str(path)
    return _write


@pytest.fixture
def sample_parsed_objects():
    """A minimal set of parsed objects for resolution/dependency tests."""
    return [
        ParsedObject(
            uuid='_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398',
            name='GetCustomerAddress',
            object_type='Expression Rule',
            data={
                'uuid': '_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398',
                'name': 'GetCustomerAddress',
                'sail_code': 'rule!HelperRule(ri!input)',
            },
        ),
        ParsedObject(
            uuid='_a-00001111-2222-3333-4444-555566667777_100',
            name='HelperRule',
            object_type='Expression Rule',
            data={
                'uuid': '_a-00001111-2222-3333-4444-555566667777_100',
                'name': 'HelperRule',
                'sail_code': '1 + 1',
            },
        ),
        ParsedObject(
            uuid='_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774',
            name='MY_CONSTANT',
            object_type='Constant',
            data={
                'uuid': '_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774',
                'name': 'MY_CONSTANT',
                'value': '42',
            },
        ),
        ParsedObject(
            uuid='_a-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee_500',
            name='Addresses',
            object_type='Record Type',
            data={
                'uuid': '_a-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee_500',
                'name': 'Addresses',
                'fields': [
                    {'field_uuid': '48f38b25-c361-4ca7-885f-cebd80162c6a', 'field_name': 'addressId'},
                    {'field_uuid': '99f38b25-c361-4ca7-885f-cebd80162c6b', 'field_name': 'street'},
                ],
                'relationships': [
                    {
                        'relationship_uuid': 'aabbccdd-0001-0002-0003-000000000001',
                        'relationship_name': 'customer',
                        'target_record_type_uuid': '_a-bbbbbbbb-cccc-dddd-eeee-ffffffffffff_600',
                    },
                ],
                'actions': [],
                'views': [],
            },
        ),
        ParsedObject(
            uuid='_a-bbbbbbbb-cccc-dddd-eeee-ffffffffffff_600',
            name='Customers',
            object_type='Record Type',
            data={
                'uuid': '_a-bbbbbbbb-cccc-dddd-eeee-ffffffffffff_600',
                'name': 'Customers',
                'fields': [
                    {'field_uuid': 'cust-field-0001-0002-000000000001', 'field_name': 'customerId'},
                ],
                'relationships': [],
                'actions': [],
                'views': [],
            },
        ),
        ParsedObject(
            uuid='_a-cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa_700',
            name='WelcomeMessage',
            object_type='Translation String',
            data={
                'uuid': '_a-cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa_700',
                'name': 'WelcomeMessage',
                'translations': [
                    {'locale': 'en-US', 'value': 'Welcome'},
                    {'locale': 'es-ES', 'value': 'Bienvenido'},
                ],
            },
        ),
    ]


@pytest.fixture
def sample_uuid_lookup():
    """UUID lookup dict for resolver tests."""
    return {
        '_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398': {
            'name': 'GetCustomerAddress',
            'object_type': 'Expression Rule',
        },
        '_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774': {
            'name': 'MY_CONSTANT',
            'object_type': 'Constant',
        },
        '_a-00001111-2222-3333-4444-555566667777_100': {
            'name': 'MyCDT',
            'object_type': 'CDT',
        },
        '0006eed1-0f7f-8000-0020-7f0000014e7a': {
            'name': 'GetCustomerAddress',
            'object_type': 'Expression Rule',
        },
    }


@pytest.fixture
def sample_zip(tmp_path):
    """Create a minimal Appian package ZIP for integration tests."""
    zip_path = tmp_path / "test_package.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("constant/_a-0000e438_410774.xml", CONSTANT_XML)
        zf.writestr("interface/_a-0006eed1_43398.xml", INTERFACE_XML)
        zf.writestr("rule/_a-00001111_100.xml", EXPRESSION_RULE_XML)
        zf.writestr("group/_a-0000aaaa_200.xml", GROUP_XML)
    return str(zip_path)
