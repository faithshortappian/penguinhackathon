"""Tests for ReferenceResolver (integration of all resolvers)."""

import pytest

from appian_parser.resolution.reference_resolver import ReferenceResolver


class TestReferenceResolver:
    """Tests for the coordinating reference resolver."""

    def test_resolve_all_mutates_in_place(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        # The first object has sail_code with rule!HelperRule
        obj = sample_parsed_objects[0]
        original_code = obj.data['sail_code']
        resolver.resolve_all(sample_parsed_objects)
        # sail_code should still contain rule!HelperRule (already resolved name)
        assert 'HelperRule' in obj.data['sail_code']

    def test_resolve_sail_code_uuids(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        code = '#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"()'
        result = resolver.resolve_sail_code(code)
        assert result == 'rule!GetCustomerAddress()'

    def test_resolve_sail_code_rt_urns(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        rt_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        field_uuid = '48f38b25-c361-4ca7-885f-cebd80162c6a'
        code = f'#"urn:appian:record-field:v1:{rt_uuid}/{field_uuid}"'
        result = resolver.resolve_sail_code(code)
        assert result == 'recordType!Addresses.addressId'

    def test_resolve_sail_code_translations(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = resolver.resolve_sail_code(code, 'en-US')
        assert result == '"Welcome"'

    def test_resolve_sail_code_spanish(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = resolver.resolve_sail_code(code, 'es-ES')
        assert result == '"Bienvenido"'

    def test_resolve_uuid_to_name(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        result = resolver.resolve_uuid('_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398')
        assert result == 'GetCustomerAddress'

    def test_resolve_uuid_unknown_returns_original(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        result = resolver.resolve_uuid('unknown-uuid')
        assert result == 'unknown-uuid'

    def test_resolve_empty_code_returns_empty(self, sample_parsed_objects):
        resolver = ReferenceResolver(sample_parsed_objects)
        assert resolver.resolve_sail_code('') == ''
        assert resolver.resolve_sail_code(None) is None

    def test_build_uuid_lookup_includes_base(self, sample_parsed_objects):
        lookup = ReferenceResolver._build_uuid_lookup(sample_parsed_objects)
        # Should have both full UUID and base UUID
        assert '_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398' in lookup
        assert '0006eed1-0f7f-8000-0020-7f0000014e7a' in lookup

    def test_build_record_type_cache(self, sample_parsed_objects):
        rt, fields, rels = ReferenceResolver._build_record_type_cache(sample_parsed_objects)
        assert 'Addresses' in rt.values()
        assert any('addressId' in v for v in fields.values())
        assert any('customer' in v[0] for v in rels.values())

    def test_build_translation_cache(self, sample_parsed_objects):
        cache = ReferenceResolver._build_translation_cache(sample_parsed_objects)
        # Should have the WelcomeMessage translation
        found = False
        for translations in cache.values():
            if 'Welcome' in translations.values():
                found = True
                break
        assert found
