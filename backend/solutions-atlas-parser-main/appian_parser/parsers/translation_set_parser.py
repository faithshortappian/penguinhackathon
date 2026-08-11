"""
Parser for Appian Translation Set objects.

This module provides the TranslationSetParser class for extracting data from
Translation Set XML files (translationSetHaul format).

Translation Sets are containers for internationalized UI strings in Appian,
enabling centralized management of user-facing text across applications.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class TranslationSetParser(BaseParser):
    """
    Parser for Appian Translation Set objects.

    Extracts metadata, enabled locales, default locale, and security settings
    from Translation Set XML files.

    XML Structure:
        <translationSetHaul>
            <versionUuid>...</versionUuid>
            <translationSet a:uuid="..." name="...">
                <a:description>...</a:description>
                <a:enabledLocales>
                    <a:localeLanguageTag>en-US</a:localeLanguageTag>
                </a:enabledLocales>
                <a:defaultLocale>
                    <a:localeLanguageTag>en-US</a:localeLanguageTag>
                </a:defaultLocale>
            </translationSet>
            <roleMap>
                <role name="...">
                    <users><userUuid>...</userUuid></users>
                    <groups><groupUuid>...</groupUuid></groups>
                </role>
            </roleMap>
        </translationSetHaul>
    """

    # XML namespaces used in Translation Set files
    NS = {'a': 'http://www.appian.com/ae/types/2009'}

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Translation Set XML file and extract all relevant data.

        Args:
            xml_path: Path to the Translation Set XML file

        Returns:
            Dict containing:
            - uuid: Translation Set UUID
            - name: Translation Set name
            - version_uuid: Version UUID
            - description: Translation Set description
            - default_locale: Default locale language tag
            - enabled_locales: List of enabled locale language tags
            - security_roles: List of security role assignments

        Raises:
            ValueError: If no translationSet element found in XML
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the translationSet element
        ts_elem = self._find_translation_set_element(root)
        if ts_elem is None:
            raise ValueError(f"No translationSet element found in {xml_path}")

        # Extract UUID - try namespaced attribute first, then non-namespaced
        uuid = self._extract_uuid(ts_elem)
        name = ts_elem.get('name')

        data = {
            'uuid': uuid,
            'name': name,
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._extract_description(ts_elem),
            'default_locale': self._extract_default_locale(ts_elem),
            'enabled_locales': self._extract_enabled_locales(ts_elem),
            'security': self._extract_role_map(root)
        }

        return data

    def _find_translation_set_element(self, root: ET.Element) -> Optional[ET.Element]:
        """
        Find the translationSet element in the XML tree.

        Handles both namespaced and non-namespaced element names.

        Args:
            root: Root XML element

        Returns:
            translationSet element or None if not found
        """
        # Try without namespace first (most common)
        ts_elem = root.find('.//translationSet')
        if ts_elem is not None:
            return ts_elem

        # Try with namespace
        ts_elem = root.find('.//a:translationSet', self.NS)
        return ts_elem

    def _extract_uuid(self, ts_elem: ET.Element) -> Optional[str]:
        """
        Extract UUID from Translation Set element.

        Handles both namespaced and non-namespaced UUID attributes.

        Args:
            ts_elem: Translation Set XML element

        Returns:
            UUID string or None
        """
        # Try with namespace first (a:uuid)
        uuid = ts_elem.get(f'{{{self.NS["a"]}}}uuid')
        if uuid:
            return uuid

        # Try without namespace
        return ts_elem.get('uuid')

    def _extract_description(self, ts_elem: ET.Element) -> Optional[str]:
        """
        Extract description from Translation Set element.

        Args:
            ts_elem: Translation Set XML element

        Returns:
            Description string or None
        """
        # Try with namespace first
        desc = self._get_text_ns(ts_elem, 'a:description')
        if desc:
            return desc

        # Try without namespace
        return self._get_text(ts_elem, 'description')

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

    def _extract_default_locale(self, ts_elem: ET.Element) -> Optional[str]:
        """
        Extract default locale from Translation Set element.

        Args:
            ts_elem: Translation Set XML element

        Returns:
            Default locale language tag (e.g., 'en-US') or None
        """
        # Try namespaced path first
        locale_tag = ts_elem.find('.//a:defaultLocale/a:localeLanguageTag', self.NS)
        if locale_tag is not None and locale_tag.text:
            return locale_tag.text

        # Try non-namespaced path
        locale_tag = ts_elem.find('.//defaultLocale/localeLanguageTag')
        if locale_tag is not None and locale_tag.text:
            return locale_tag.text

        return None

    def _extract_enabled_locales(self, ts_elem: ET.Element) -> List[str]:
        """
        Extract list of enabled locales from Translation Set element.

        Args:
            ts_elem: Translation Set XML element

        Returns:
            List of locale language tags (e.g., ['en-US', 'es-ES'])
        """
        locales = []

        # Try namespaced path first
        locale_tags = ts_elem.findall('.//a:enabledLocales/a:localeLanguageTag', self.NS)
        if locale_tags:
            for tag in locale_tags:
                if tag.text:
                    locales.append(tag.text)
            return locales

        # Try non-namespaced path
        locale_tags = ts_elem.findall('.//enabledLocales/localeLanguageTag')
        for tag in locale_tags:
            if tag.text:
                locales.append(tag.text)

        return locales
