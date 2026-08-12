"""
Parser for Appian Site objects.

This module provides the SiteParser class for extracting comprehensive data from
Site XML files, including:
- Site-level properties (branding, UI configuration, visibility)
- Hierarchical page structure (including nested page groups)
- Role mappings (site_administrator, site_viewer)

The parser extracts all fields defined in the enhanced Site model (Phase 1)
to support full site comparison and display in the merge workflow.
"""

from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET
from appian_parser.parsers.base_parser import BaseParser


class SiteParser(BaseParser):
    """
    Parser for Appian Site objects.

    Extracts comprehensive site data including:
    - Basic identification (uuid, name, version_uuid, description)
    - URL configuration (url_stub)
    - Display settings (display_name, show_name, is_static_display_name)
    - Branding expressions (colors, logo, favicon)
    - UI configuration (button shapes, navigation style, etc.)
    - Hierarchical page structure with all page properties
    - Role mappings with user and group members

    XML Structure:
    ```xml
    <siteHaul>
      <versionUuid>...</versionUuid>
      <site a:uuid="..." name="...">
        <description>...</description>
        <urlStub>...</urlStub>
        <page a:uuid="...">
          <!-- Page properties -->
          <page a:uuid="..."><!-- Nested pages for page groups --></page>
        </page>
        <!-- Site-level properties -->
      </site>
      <roleMap>
        <role name="site_administrator">...</role>
        <role name="site_viewer">...</role>
      </roleMap>
    </siteHaul>
    ```
    """

    # Namespace definitions for Appian XML
    NAMESPACES = {
        'a': 'http://www.appian.com/ae/types/2009',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }

    # Appian namespace prefix for UUID attributes
    APPIAN_UUID_ATTR = '{http://www.appian.com/ae/types/2009}uuid'
    XSI_TYPE_ATTR = '{http://www.w3.org/2001/XMLSchema-instance}type'

    def parse(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse Site XML file and extract all relevant data.

        Args:
            xml_path: Path to the Site XML file

        Returns:
            Dict containing:
            - uuid: Site UUID
            - name: Site name
            - version_uuid: Version UUID
            - description: Site description
            - url_stub: Site URL stub
            - display_name: Display name (can be expression)
            - is_static_display_name: Whether display name is static
            - show_name: Whether to show site name
            - header_background_color_expr: Header background color expression
            - selected_tab_background_color_expr: Selected tab color expression
            - accent_color_expr: Accent color expression
            - logo_expr: Logo expression
            - favicon_expr: Favicon expression
            - loading_bar_color_expr: Loading bar color expression
            - visibility: Site visibility setting
            - tempo_link_visibility: Tempo link visibility
            - tasks_in_sites_visibility: Tasks visibility in sites
            - show_record_news: Whether to show record news
            - button_shape: Button shape setting
            - button_label_case: Button label case setting
            - input_shape: Input shape setting
            - dialog_shape: Dialog shape setting
            - navigation_bar_style: Navigation bar style
            - primary_nav_layout_type: Primary navigation layout type
            - is_system: Whether this is a system site
            - pages: List of page definitions (hierarchical)
            - roles: List of role mappings with members

        Raises:
            ValueError: If no site element found in XML
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Find the site element
        site_elem = root.find('.//site', self.NAMESPACES)
        if site_elem is None:
            # Try without namespace
            site_elem = root.find('.//site')
        if site_elem is None:
            raise ValueError(f"No site element found in {xml_path}")

        # Extract basic info - UUID and name are attributes with namespace
        uuid = site_elem.get(self.APPIAN_UUID_ATTR) or site_elem.get('uuid')
        name = site_elem.get('name')

        data = {
            # Core identification
            'uuid': uuid,
            'name': name,
            'version_uuid': self._get_text(root, './/versionUuid'),
            'description': self._get_text(site_elem, 'description'),
            'url_stub': self._get_text(site_elem, 'urlStub'),

            # Display settings
            'display_name': self._clean_sail_code(self._get_text(site_elem, 'displayName')),
            'is_static_display_name': self._get_boolean(site_elem, 'isStaticDisplayName', False),
            'show_name': self._get_boolean(site_elem, 'showName', True),

            # Branding expressions
            'header_background_color_expr': self._clean_sail_code(self._get_text(site_elem, 'headerBackgroundColorExpr')),
            'selected_tab_background_color_expr': self._clean_sail_code(self._get_text(
                site_elem, 'selectedTabBackgroundColorExpr'
            )),
            'accent_color_expr': self._clean_sail_code(self._get_text(site_elem, 'accentColorExpr')),
            'logo_expr': self._clean_sail_code(self._get_text(site_elem, 'logoExpr')),
            'favicon_expr': self._clean_sail_code(self._get_text(site_elem, 'faviconExpr')),
            'loading_bar_color_expr': self._clean_sail_code(self._get_text(site_elem, 'loadingBarColorExpr')),

            # Also check for non-expression color values (static colors)
            'selected_tab_background_color': self._get_text(site_elem, 'selectedTabBackgroundColor'),

            # UI configuration
            'visibility': self._get_text(site_elem, 'visibility'),
            'tempo_link_visibility': self._get_text(site_elem, 'tempoLinkVisibility'),
            'tasks_in_sites_visibility': self._get_text(site_elem, 'tasksInSitesVisibility'),
            'show_record_news': self._get_boolean(site_elem, 'showRecordNews', True),
            'button_shape': self._get_text(site_elem, 'buttonShape'),
            'button_label_case': self._get_text(site_elem, 'buttonLabelCase'),
            'input_shape': self._get_text(site_elem, 'inputShape'),
            'dialog_shape': self._get_text(site_elem, 'dialogShape'),
            'navigation_bar_style': self._get_text(site_elem, 'navigationBarStyle'),
            'primary_nav_layout_type': self._get_text(site_elem, 'primaryNavLayoutType'),
            'is_system': self._get_boolean(site_elem, 'isSystem', False),

            # Nested data
            'pages': self._extract_pages(site_elem),
            'security': self._extract_role_map(root)
        }

        return data

    def _extract_pages(
        self,
        parent_elem: ET.Element,
        parent_uuid: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract pages recursively to handle page groups (nested pages).

        Page groups are pages that contain other pages. They typically don't have
        a uiObject but have child pages. This method recursively extracts the
        entire page hierarchy.

        Args:
            parent_elem: Parent XML element (site or page element)
            parent_uuid: UUID of the parent page (None for top-level pages)

        Returns:
            List of page dictionaries with hierarchy information.
            Each page dict contains:
            - page_uuid: Unique identifier for the page
            - parent_uuid: UUID of parent page (for nested pages)
            - static_name: Static page name (if not using expression)
            - name_expr: Name expression (if using dynamic name)
            - description: Page description
            - url_stub: URL stub for the page
            - icon_id: Icon identifier
            - page_width: Page width (STANDARD, WIDE, FULL)
            - ui_object_uuid: UUID of the interface/report
            - ui_object_type: Type of UI object (TempoReport, ContentFreeformRule, etc.)
            - visibility_expr: Visibility expression
            - are_url_params_encrypted: Whether URL params are encrypted
            - auto_context_update_enabled: Whether auto context update is enabled
            - site_branding_enabled: Whether site branding is enabled
            - dark_theme_enabled: Whether dark theme is enabled
            - display_order: Order of the page in the list
            - children: List of child pages (for page groups)
        """
        pages = []

        # Find all direct child page elements
        for idx, page_elem in enumerate(parent_elem.findall('page')):
            page_uuid = page_elem.get(self.APPIAN_UUID_ATTR) or page_elem.get('uuid')

            page = {
                'page_uuid': page_uuid,
                'parent_uuid': parent_uuid,

                # Name - can be static or expression
                'static_name': self._get_text(page_elem, 'staticName'),
                'name_expr': self._get_text(page_elem, 'nameExpr'),

                # Core properties
                'description': self._get_text(page_elem, 'description'),
                'url_stub': self._get_text(page_elem, 'urlStub') or '',
                'icon_id': self._get_text(page_elem, 'iconId'),
                'page_width': self._get_text(page_elem, 'pageWidth'),

                # Visibility expression
                'visibility_expr': self._clean_sail_code(self._get_text(page_elem, 'visibilityExpr')),

                # Settings
                'are_url_params_encrypted': self._get_boolean(
                    page_elem, 'areUrlParamsEncrypted', True
                ),
                'auto_context_update_enabled': self._get_boolean(
                    page_elem, 'autoContextUpdateEnabled', True
                ),
                'site_branding_enabled': self._get_boolean(
                    page_elem, 'siteBrandingEnabled', True
                ),
                'dark_theme_enabled': self._get_boolean(
                    page_elem, 'darkThemeEnabled', False
                ),

                # Ordering
                'display_order': idx,

                # Children (populated below)
                'children': []
            }

            # Extract UI object reference (interface/report)
            ui_obj_elem = page_elem.find('uiObject')
            if ui_obj_elem is not None:
                page['ui_object_uuid'] = (
                    ui_obj_elem.get(self.APPIAN_UUID_ATTR) or ui_obj_elem.get('uuid')
                )
                page['ui_object_type'] = ui_obj_elem.get(self.XSI_TYPE_ATTR)
                # Clean up the type (remove namespace prefix if present)
                if page['ui_object_type'] and ':' in page['ui_object_type']:
                    page['ui_object_type'] = page['ui_object_type'].split(':')[-1]
            else:
                page['ui_object_uuid'] = None
                page['ui_object_type'] = None

            # Recursively extract nested pages (page groups)
            page['children'] = self._extract_pages(page_elem, page_uuid)

            pages.append(page)

        return pages

    def _flatten_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Flatten hierarchical page structure for simple iteration.

        This is a utility method that can be used when a flat list of all pages
        is needed (e.g., for counting total pages).

        Args:
            pages: Hierarchical list of pages

        Returns:
            Flat list of all pages (including nested ones)
        """
        flat_pages = []
        for page in pages:
            flat_pages.append(page)
            if page.get('children'):
                flat_pages.extend(self._flatten_pages(page['children']))
        return flat_pages

    def get_total_page_count(self, pages: List[Dict[str, Any]]) -> int:
        """
        Get total count of all pages including nested ones.

        Args:
            pages: Hierarchical list of pages

        Returns:
            Total number of pages
        """
        return len(self._flatten_pages(pages))
