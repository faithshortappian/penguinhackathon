"""Tests for UUID resolution modules."""

import pytest

from appian_parser.resolution.uuid_resolver import UUIDResolver
from appian_parser.resolution.uuid_utils import UUIDUtils


class TestUUIDUtils:
    """Tests for UUIDUtils static methods."""

    def test_is_appian_uuid_prefixed(self):
        assert UUIDUtils.is_appian_uuid('_a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398')

    def test_is_appian_uuid_prefixed_e(self):
        assert UUIDUtils.is_appian_uuid('_e-0000e4ea-0367-8000-9af4-01075c01075c_322')

    def test_is_appian_uuid_standard(self):
        assert UUIDUtils.is_appian_uuid('0006eed1-0f7f-8000-0020-7f0000014e7a')

    def test_is_appian_uuid_suffixed(self):
        assert UUIDUtils.is_appian_uuid('82127412-76f3-43c7-9b98-c2201b1e158b-as_rm_pro')

    def test_is_appian_uuid_rejects_invalid(self):
        assert not UUIDUtils.is_appian_uuid('not-a-uuid')
        assert not UUIDUtils.is_appian_uuid(None)
        assert not UUIDUtils.is_appian_uuid('')

    def test_extract_base_uuid_prefixed(self):
        result = UUIDUtils.extract_base_uuid('_a-0000e6a4-3c85-8000-9ba5-011c48011c48_43398')
        assert result == '0000e6a4-3c85-8000-9ba5-011c48011c48'

    def test_extract_base_uuid_standard(self):
        result = UUIDUtils.extract_base_uuid('0006eed1-0f7f-8000-0020-7f0000014e7a')
        assert result == '0006eed1-0f7f-8000-0020-7f0000014e7a'

    def test_extract_base_uuid_suffixed(self):
        result = UUIDUtils.extract_base_uuid('82127412-76f3-43c7-9b98-c2201b1e158b-as_rm_pro')
        assert result == '82127412-76f3-43c7-9b98-c2201b1e158b'

    def test_extract_base_uuid_none(self):
        assert UUIDUtils.extract_base_uuid(None) is None
        assert UUIDUtils.extract_base_uuid('') is None

    def test_resolve_uuid_found(self):
        lookup = {'uuid-1': {'name': 'MyObj', 'object_type': 'Interface'}}
        assert UUIDUtils.resolve_uuid('uuid-1', lookup) == 'MyObj'

    def test_resolve_uuid_not_found(self):
        assert UUIDUtils.resolve_uuid('unknown', {}) == 'unknown'

    def test_resolve_uuid_none(self):
        assert UUIDUtils.resolve_uuid(None, {}) == ''

    def test_resolve_uuid_with_type(self):
        lookup = {'uuid-1': {'name': 'MyObj', 'object_type': 'Interface'}}
        name, otype = UUIDUtils.resolve_uuid_with_type('uuid-1', lookup)
        assert name == 'MyObj'
        assert otype == 'Interface'

    def test_format_uuid_with_name(self):
        assert UUIDUtils.format_uuid_with_name('uuid-1', 'MyObj') == 'MyObj (uuid-1)'
        assert UUIDUtils.format_uuid_with_name('uuid-1', 'MyObj', include_uuid=False) == 'MyObj'


class TestUUIDResolver:
    """Tests for UUIDResolver SAIL code resolution."""

    def test_resolve_prefixed_uuid_to_rule(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"(ri!input)'
        result = resolver.resolve_sail_code(code)
        assert result == 'rule!GetCustomerAddress(ri!input)'

    def test_resolve_prefixed_uuid_to_cons(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774"'
        result = resolver.resolve_sail_code(code)
        assert result == 'cons!MY_CONSTANT'

    def test_resolve_prefixed_uuid_to_type(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"_a-00001111-2222-3333-4444-555566667777_100"'
        result = resolver.resolve_sail_code(code)
        assert result == 'type!MyCDT'

    def test_resolve_bare_uuid(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"0006eed1-0f7f-8000-0020-7f0000014e7a"'
        result = resolver.resolve_sail_code(code)
        assert result == 'rule!GetCustomerAddress'

    def test_unresolved_uuid_unchanged(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"_a-ffffffff-ffff-ffff-ffff-ffffffffffff_999"'
        result = resolver.resolve_sail_code(code)
        assert result == code

    def test_resolve_multiple_uuids(self, sample_uuid_lookup):
        resolver = UUIDResolver(sample_uuid_lookup)
        code = '#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"(cons!#"_a-0000e438-fd8a-8000-9bbe-011c48011c48_410774")'
        result = resolver.resolve_sail_code(code)
        assert 'rule!GetCustomerAddress' in result
        assert 'cons!MY_CONSTANT' in result

    def test_canonical_prefix_resolution(self):
        """Test cross-app-suffix resolution via canonical prefix."""
        lookup = {
            '_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398-tmg-am-am': {
                'name': 'MyRule', 'object_type': 'Expression Rule',
            },
        }
        resolver = UUIDResolver(lookup)
        # Reference uses different app suffix
        code = '#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398-tmg-rm"'
        result = resolver.resolve_sail_code(code)
        assert result == 'rule!MyRule'
