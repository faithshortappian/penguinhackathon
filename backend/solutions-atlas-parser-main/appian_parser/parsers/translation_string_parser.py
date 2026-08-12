"""
Parser for Appian Translation String objects.

This module provides the TranslationStringParser class for extracting data from
Translation String XML files (translationStringHaul format).

Translation Strings are individual translatable text entries within a Translation Set,
containing locale-specific translations for UI labels and messages.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class TranslationStringParser(BaseParser):
    """
    Parser for Appian Translation String objects.

    Extracts string metadata, parent set reference, and locale-specific
    translations from Translation String XML files.

    XML Structure:
        <translationStringHaul>
            <versionUuid>...</versionUuid>
            <translationString a:uuid="...">
                <a:translationSetUuid>...</a:translationSetUuid>
                <a:description>...</a:description>
                <a:translatorNotes>...</a:translatorNotes>
                <translationTexts>
                    <translatedText>
                        <a:translationLocale>
                            <a:localeLanguageTag>en-US</a:localeLanguageTag>
                        </a:translationLocale>
                        <a:translatedText>Hello World</a:translatedText>
                    </translatedText>
                </translationTexts>
            </translationString>
        </translationStringHaul>
    """

    # XML namespaces used in Translation String files
    NS = {'a': 'http://www.appian.com/ae/types/2009'}

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Translation String XML file and extract all relevant data.

        Args:
            xml_path: Path to the Translation String XML file

        Returns:
            Dict containing:
            - uuid: Translation String UUID
            - version_uuid: Version UUID
            - translation_set_uuid: Parent Translation Set UUID
            - description: String description
            - translator_notes: Notes for translators
            - translations: List of locale-specific translations

        Raises:
            ValueError: If no translationString element found in XML
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the translationString element
        tstr_elem = self._find_translation_string_element(root)
        if tstr_elem is None:
            raise ValueError(f"No translationString element found in {xml_path}")

        # Extract UUID
        uuid = self._extract_uuid(tstr_elem)

        data = {
            'uuid': uuid,
            'version_uuid': self._get_text(root, './/versionUuid'),
            'translation_set_uuid': self._extract_translation_set_uuid(tstr_elem),
            'description': self._extract_description(tstr_elem),
            'translator_notes': self._extract_translator_notes(tstr_elem),
            'translations': self._extract_translations(tstr_elem)
        }

        # Derive a name since translation strings have no explicit name element
        data['name'] = self._derive_name(data)

        return data

    def _find_translation_string_element(self, root: ET.Element) -> Optional[ET.Element]:
        """
        Find the translationString element in the XML tree.

        Handles both namespaced and non-namespaced element names.

        Args:
            root: Root XML element

        Returns:
            translationString element or None if not found
        """
        # Try without namespace first (most common)
        tstr_elem = root.find('.//translationString')
        if tstr_elem is not None:
            return tstr_elem

        # Try with namespace
        tstr_elem = root.find('.//a:translationString', self.NS)
        return tstr_elem

    def _extract_uuid(self, tstr_elem: ET.Element) -> Optional[str]:
        """
        Extract UUID from Translation String element.

        Handles both namespaced and non-namespaced UUID attributes.

        Args:
            tstr_elem: Translation String XML element

        Returns:
            UUID string or None
        """
        # Try with namespace first (a:uuid)
        uuid = tstr_elem.get(f'{{{self.NS["a"]}}}uuid')
        if uuid:
            return uuid

        # Try without namespace
        return tstr_elem.get('uuid')

    def _extract_translation_set_uuid(self, tstr_elem: ET.Element) -> Optional[str]:
        """
        Extract parent Translation Set UUID from Translation String element.

        Args:
            tstr_elem: Translation String XML element

        Returns:
            Parent Translation Set UUID or None
        """
        # Try with namespace first
        uuid = self._get_text_ns(tstr_elem, 'a:translationSetUuid')
        if uuid:
            return uuid

        # Try without namespace
        return self._get_text(tstr_elem, 'translationSetUuid')

    def _extract_description(self, tstr_elem: ET.Element) -> Optional[str]:
        """
        Extract description from Translation String element.

        Args:
            tstr_elem: Translation String XML element

        Returns:
            Description string or None
        """
        # Try with namespace first
        desc = self._get_text_ns(tstr_elem, 'a:description')
        if desc:
            return desc

        # Try without namespace
        return self._get_text(tstr_elem, 'description')

    def _extract_translator_notes(self, tstr_elem: ET.Element) -> Optional[str]:
        """
        Extract translator notes from Translation String element.

        Args:
            tstr_elem: Translation String XML element

        Returns:
            Translator notes string or None
        """
        # Try with namespace first
        notes = self._get_text_ns(tstr_elem, 'a:translatorNotes')
        if notes:
            return notes

        # Try without namespace
        return self._get_text(tstr_elem, 'translatorNotes')

    def _get_text_ns(self, element: ET.Element, path: str) -> Optional[str]:
        """
        Get text from element using namespaced path.

        Args:
            element: Parent XML element
            path: XPath with namespace prefix (e.g., 'a:description')

        Returns:
            Text content or None
        """
        elem = element.find(path, self.NS)
        return elem.text if elem is not None and elem.text else None

    def _extract_translations(self, tstr_elem: ET.Element) -> List[Dict[str, Optional[str]]]:
        """
        Extract locale-specific translations from Translation String element.

        Args:
            tstr_elem: Translation String XML element

        Returns:
            List of translation dictionaries with:
            - locale: Locale language tag (e.g., 'en-US')
            - text: Translated text for this locale
        """
        translations = []

        # Find all translatedText elements
        # Try multiple paths to handle different XML structures
        translated_texts = tstr_elem.findall('.//translationTexts/translatedText')
        if not translated_texts:
            translated_texts = tstr_elem.findall('.//a:translationTexts/a:translatedText', self.NS)

        for tt in translated_texts:
            translation = self._parse_translated_text(tt)
            if translation:
                translations.append(translation)

        return translations

    def _parse_translated_text(self, tt_elem: ET.Element) -> Optional[Dict[str, Optional[str]]]:
        """
        Parse a single translatedText element.

        Args:
            tt_elem: translatedText XML element

        Returns:
            Dictionary with locale and text, or None if locale not found
        """
        locale = self._extract_locale_from_translated_text(tt_elem)
        if not locale:
            return None

        text = self._extract_text_from_translated_text(tt_elem)

        return {
            'locale': locale,
            'text': text
        }

    def _extract_locale_from_translated_text(self, tt_elem: ET.Element) -> Optional[str]:
        """
        Extract locale language tag from translatedText element.

        Args:
            tt_elem: translatedText XML element

        Returns:
            Locale language tag or None
        """
        # Try namespaced path first
        locale_elem = tt_elem.find('.//a:translationLocale/a:localeLanguageTag', self.NS)
        if locale_elem is not None and locale_elem.text:
            return locale_elem.text

        # Try non-namespaced path
        locale_elem = tt_elem.find('.//translationLocale/localeLanguageTag')
        if locale_elem is not None and locale_elem.text:
            return locale_elem.text

        return None

    def _extract_text_from_translated_text(self, tt_elem: ET.Element) -> Optional[str]:
        """
        Extract translated text from translatedText element.

        Args:
            tt_elem: translatedText XML element

        Returns:
            Translated text or None
        """
        # Try namespaced path first
        text_elem = tt_elem.find('.//a:translatedText', self.NS)
        if text_elem is not None:
            return text_elem.text

        # Try non-namespaced path
        text_elem = tt_elem.find('.//translatedText')
        if text_elem is not None:
            return text_elem.text

        return None

    def _derive_name(self, data: Dict[str, Any]) -> str:
        """Derive a display name from description or primary locale translation."""
        if data.get('description'):
            return data['description'][:80]
        for t in data.get('translations', []):
            if t.get('locale', '').startswith('en') and t.get('text'):
                return t['text'][:80]
        for t in data.get('translations', []):
            if t.get('text'):
                return t['text'][:80]
        return data.get('uuid') or 'Unknown'
