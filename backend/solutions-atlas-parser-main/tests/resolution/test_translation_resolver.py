"""Tests for TranslationResolver."""

import pytest

from appian_parser.resolution.translation_resolver import TranslationResolver


@pytest.fixture
def translation_resolver():
    cache = {
        'cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa': {
            'en-US': 'Welcome',
            'es-ES': 'Bienvenido',
            'fr-FR': 'Bienvenue',
        },
        'dddddddd-eeee-ffff-aaaa-bbbbbbbbbbbb': {
            'en-US': 'A very long translation string that exceeds one hundred characters in length and should be truncated by the resolver to avoid overly long output',
        },
    }
    return TranslationResolver(cache)


class TestTranslationResolver:
    """Tests for translation string URN resolution."""

    def test_resolve_exact_locale(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = translation_resolver.resolve_sail_code(code, 'en-US')
        assert result == '"Welcome"'

    def test_resolve_spanish_locale(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = translation_resolver.resolve_sail_code(code, 'es-ES')
        assert result == '"Bienvenido"'

    def test_resolve_language_prefix_fallback(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = translation_resolver.resolve_sail_code(code, 'en-GB')
        assert result == '"Welcome"'

    def test_resolve_any_fallback(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa"'
        result = translation_resolver.resolve_sail_code(code, 'ja-JP')
        # Should return any available translation
        assert result.startswith('"')
        assert result.endswith('"')

    def test_truncates_long_translations(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:dddddddd-eeee-ffff-aaaa-bbbbbbbbbbbb"'
        result = translation_resolver.resolve_sail_code(code, 'en-US')
        assert '...' in result
        # Content between quotes should be <= 103 chars (100 + ...)
        inner = result[1:-1]
        assert len(inner) <= 103

    def test_unresolved_translation_unchanged(self, translation_resolver):
        code = '#"urn:appian:translation-string:v1:ffffffff-ffff-ffff-ffff-ffffffffffff"'
        result = translation_resolver.resolve_sail_code(code, 'en-US')
        assert result == code

    def test_escapes_quotes_in_translation(self):
        cache = {
            'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee': {'en-US': 'Say "hello"'},
        }
        resolver = TranslationResolver(cache)
        code = '#"urn:appian:translation-string:v1:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"'
        result = resolver.resolve_sail_code(code, 'en-US')
        assert result == '"Say \\"hello\\""'
