"""Translation string URN resolver for SAIL code.

Resolves translation URNs to their translated text values:
  urn:appian:translation-string:v1:{uuid} → "Translated text"
"""

import re


class TranslationResolver:
    """Resolves translation string URNs in SAIL code.

    Args:
        translation_cache: UUID → {locale: text} mapping.
    """

    _PATTERN = re.compile(
        r'#"urn:appian:translation-string:v1:([a-f0-9\-]{36})"',
        re.I,
    )

    def __init__(self, translation_cache: dict[str, dict[str, str]]) -> None:
        self._cache = translation_cache

    def resolve_sail_code(self, code: str, locale: str = 'en-US') -> str:
        """Resolve all translation URNs in SAIL code.

        Args:
            code: SAIL code containing translation URNs.
            locale: Preferred locale (falls back to language prefix, then any).

        Returns:
            Code with translation URNs replaced by quoted text.
        """
        return self._PATTERN.sub(lambda m: self._replace(m, locale), code)

    def _replace(self, match: re.Match, locale: str) -> str:
        """Replace a single translation URN match."""
        translations = self._cache.get(match.group(1))
        if not translations:
            return match.group(0)

        text = self._find_best_translation(translations, locale)
        text = text.replace('"', '\\"')
        if len(text) > 100:
            text = text[:100] + '...'
        return f'"{text}"'

    @staticmethod
    def _find_best_translation(translations: dict[str, str], locale: str) -> str:
        """Find the best translation for the given locale.

        Priority: exact locale → language prefix match → any available.
        """
        if locale in translations:
            return translations[locale]

        lang_prefix = locale.split('-')[0]
        for key, value in translations.items():
            if key.split('-')[0] == lang_prefix:
                return value

        return next(iter(translations.values()))
