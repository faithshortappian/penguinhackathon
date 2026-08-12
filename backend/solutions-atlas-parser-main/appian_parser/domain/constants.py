"""Shared constants, regex patterns, and field path configurations.

Centralizes all patterns and configuration that are shared across
resolution, dependency analysis, and output modules.
"""

import re

# ── UUID Patterns ────────────────────────────────────────────────────────

# Canonical prefix: _a-{base_uuid}_{numericId} — strips application suffix
CANONICAL_RE = re.compile(
    r'(_[ae]-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_\d+)',
    re.I,
)

# Full prefixed UUID: _a-{uuid}_{suffix} or _e-{uuid}_{suffix}
UUID_FULL_RE = re.compile(
    r'(_[ae]-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_[\w-]+)',
    re.I,
)

# Standard 36-char UUID with word boundaries
UUID_STANDARD_RE = re.compile(
    r'(?<![0-9a-f-])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?![0-9a-f-])',
    re.I,
)

# Extract base UUID from prefixed format
UUID_PREFIXED_RE = re.compile(
    r'_[ae]-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_[\w-]+',
    re.I,
)

# Extended UUID for record type URNs: standard or suffixed (uuid-suffix)
RT_UUID_PATTERN = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?:-[\w-]+)?'

# ── SAIL Reference Patterns ─────────────────────────────────────────────

RULE_REF_RE = re.compile(r'rule!([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
CONS_REF_RE = re.compile(r'cons!([a-zA-Z_][a-zA-Z0-9_]*)')
TYPE_REF_RE = re.compile(r'type!([a-zA-Z_][a-zA-Z0-9_]*)')
RECORD_TYPE_REF_RE = re.compile(r'recordType!([a-zA-Z_][a-zA-Z0-9_]*)')
RT_URN_RE = re.compile(r'urn:appian:record-(?:type|field|relationship):v1:([0-9a-f-]{36})', re.I)

# ── Object Type → Folder Mapping ────────────────────────────────────────

TYPE_TO_FOLDER: dict[str, str] = {
    'Interface': 'interfaces',
    'Expression Rule': 'expression_rules',
    'Process Model': 'process_models',
    'Record Type': 'record_types',
    'CDT': 'cdts',
    'Data Type': 'cdts',
    'Integration': 'integrations',
    'Web API': 'web_apis',
    'Site': 'sites',
    'Group': 'groups',
    'Constant': 'constants',
    'Connected System': 'connected_systems',
    'Control Panel': 'control_panels',
    'Translation Set': 'translation_sets',
    'Translation String': 'translation_strings',
    'Data Store': 'data_stores',
    'Application': 'applications',
    'Unknown': 'unknown',
}

# ── Field Path Configurations ────────────────────────────────────────────
#
# These declarative field paths define which fields contain SAIL code
# (needing full UUID/URN/translation resolution) and which contain raw
# UUIDs (needing name resolution only).
#
# Notation: `field[]` means iterate over list items, `field.subfield`
# means nested dict access.

SAIL_CODE_FIELDS: dict[str, list[str]] = {
    'Interface': ['sail_code', 'test_inputs[].input_value'],
    'Expression Rule': [
        'sail_code', 'definition',
        'test_cases[].test_inputs[].input_value',
        'test_cases[].assertions[].assertion_value',
    ],
    'Process Model': [
        'nodes[].form_expression',
        'nodes[].gateway_conditions[].condition',
        'nodes[].inputs[].input_expression',
        'nodes[].outputs[].output_expression',
        'nodes[].pre_triggers[].rules[].expression',
        'nodes[].subprocess_config.input_mappings[].expression',
        'nodes[].subprocess_config.output_mappings[].save_into',
        'start_form_expression',
        'variables[].initial_expression',
    ],
    'Record Type': [
        'actions[].expressions.TITLE',
        'actions[].expressions.DESCRIPTION',
        'actions[].expressions.VISIBILITY',
        'actions[].expressions.CONTEXT',
        'views[].visibility_expr',
        'views[].ui_expr',
        'views[].view_name',
        'default_filters_expr',
        'facets_list_expr',
        'list_view_src_expr',
        'data_src_expr',
        'title_expr',
        'source_context_expr',
        'source_filter_expr',
        'fields[].custom_field_expr',
    ],
    'Web API': ['sail_code'],
    'Site': [
        'pages[].visibility_expr',
        'display_name',
        'header_background_color_expr',
        'selected_tab_background_color_expr',
        'accent_color_expr',
        'logo_expr',
        'favicon_expr',
        'loading_bar_color_expr',
    ],
    'Control Panel': ['settings_json_raw'],
    'Integration': ['url', 'request_body', 'test_inputs[].input_value'],
}

UUID_FIELDS: dict[str, list[str]] = {
    'Process Model': [
        'nodes[].interface_uuid',
        'nodes[].subprocess_uuid',
        'start_form_interface_uuid',
    ],
    'Integration': ['connected_system_uuid'],
    'Group': [
        'parent_group_uuid',
        'members[].member_uuid',
    ],
    'Constant': ['value'],
    'Site': ['pages[].ui_object_uuid'],
    'Control Panel': [
        'primary_record_type_uuid',
        'interfaces[].interface_uuid',
        'custom_pages[].interface_uuid',
    ],
    'Record Type': [
        'relationships[].target_record_type_uuid',
        'actions[].target_uuid',
        'source_uuid',
    ],
}

# Structural UUID fields for dependency analysis (field_path, dependency_type)
STRUCTURAL_FIELDS: dict[str, list[tuple[str, str]]] = {
    'Process Model': [
        ('nodes[].interface_uuid', 'CALLS'),
        ('nodes[].subprocess_uuid', 'CALLS'),
        ('start_form_interface_uuid', 'CALLS'),
    ],
    'Integration': [
        ('connected_system_uuid', 'USES_CONNECTED_SYSTEM'),
    ],
    'Record Type': [
        ('relationships[].target_record_type_uuid', 'USES_RECORD_TYPE'),
        ('actions[].target_uuid', 'CALLS'),
        ('source_uuid', 'USES_DATA_STORE'),
    ],
    'Site': [
        ('pages[].ui_object_uuid', 'CALLS'),
    ],
    'Group': [
        ('parent_group_uuid', 'USES_GROUP'),
    ],
    'Control Panel': [
        ('primary_record_type_uuid', 'USES_RECORD_TYPE'),
        ('interfaces[].interface_uuid', 'CALLS'),
        ('custom_pages[].interface_uuid', 'CALLS'),
    ],
}

# ── Dependency Type Inference ────────────────────────────────────────────

_DEP_TYPE_MAP: dict[str, str] = {
    'Expression Rule': 'CALLS',
    'Interface': 'CALLS',
    'Constant': 'USES_CONSTANT',
    'CDT': 'USES_CDT',
    'Data Type': 'USES_CDT',
    'Record Type': 'USES_RECORD_TYPE',
    'Integration': 'USES_INTEGRATION',
    'Connected System': 'USES_CONNECTED_SYSTEM',
    'Group': 'USES_GROUP',
    'Site': 'USES_SITE',
    'Data Store': 'USES_DATA_STORE',
}


def infer_dependency_type(target_object_type: str) -> str:
    """Infer the dependency type from the target object's type."""
    return _DEP_TYPE_MAP.get(target_object_type, 'CALLS')
