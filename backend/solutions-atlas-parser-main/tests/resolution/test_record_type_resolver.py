"""Tests for RecordTypeURNResolver."""

import pytest

from appian_parser.resolution.record_type_resolver import RecordTypeURNResolver


@pytest.fixture
def rt_resolver():
    """Create a resolver with sample record type data."""
    record_types = {
        'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee': 'Addresses',
        'bbbbbbbb-cccc-dddd-eeee-ffffffffffff': 'Customers',
    }
    fields = {
        ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', '11111111-2222-3333-4444-555555555555'): 'addressId',
        ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', '22222222-3333-4444-5555-666666666666'): 'street',
        ('bbbbbbbb-cccc-dddd-eeee-ffffffffffff', '33333333-4444-5555-6666-777777777777'): 'customerId',
    }
    relationships = {
        ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'aabbccdd-0001-0002-0003-000000000001'): (
            'customer', 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff',
        ),
    }
    return RecordTypeURNResolver(record_types, fields, relationships)


class TestRecordTypeURNResolver:
    """Tests for record type URN resolution."""

    def test_resolve_record_type_urn(self, rt_resolver):
        code = '#"urn:appian:record-type:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses'

    def test_resolve_record_field_urn(self, rt_resolver):
        code = '#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/11111111-2222-3333-4444-555555555555"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.addressId'

    def test_resolve_record_relationship_urn(self, rt_resolver):
        code = '#"urn:appian:record-relationship:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/aabbccdd-0001-0002-0003-000000000001"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.customer'

    def test_resolve_two_segment_urn(self, rt_resolver):
        """Relationship + field: rt/rel/field → recordType!RT.rel.field"""
        code = '#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/aabbccdd-0001-0002-0003-000000000001/33333333-4444-5555-6666-777777777777"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.customer.customerId'

    def test_resolve_constructor_pattern(self, rt_resolver):
        code = '#"urn:appian:record-type:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"('
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses('

    def test_resolve_name_based_field(self, rt_resolver):
        code = '#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/myFieldName"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.myFieldName'

    def test_resolve_encoded_traversal(self, rt_resolver):
        code = '#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/customer%40customerId"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.customer.customerId'

    def test_unresolved_rt_unchanged(self, rt_resolver):
        code = '#"urn:appian:record-field:v1:ffffffff-ffff-ffff-ffff-ffffffffffff/11111111-2222-3333-4444-555555555555"'
        result = rt_resolver.resolve_sail_code(code)
        assert result == code

    def test_resolve_suffixed_rt_uuid(self):
        """Test that suffixed RT UUIDs (uuid-suffix) are resolved."""
        record_types = {
            'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee': 'MyRecord',
        }
        fields = {
            ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', '11111111-2222-3333-4444-555555555555'): 'myField',
        }
        resolver = RecordTypeURNResolver(record_types, fields, {})
        code = '#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee-as_rm_pro/11111111-2222-3333-4444-555555555555"'
        result = resolver.resolve_sail_code(code)
        assert result == 'recordType!MyRecord.myField'

    def test_resolve_multiple_urns_in_code(self, rt_resolver):
        code = (
            'a!queryRecordType(\n'
            '  recordType: #"urn:appian:record-type:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",\n'
            '  fields: {#"urn:appian:record-field:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/11111111-2222-3333-4444-555555555555"}\n'
            ')'
        )
        result = rt_resolver.resolve_sail_code(code)
        assert 'recordType!Addresses' in result
        assert 'recordType!Addresses.addressId' in result
