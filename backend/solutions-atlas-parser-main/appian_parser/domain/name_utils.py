"""Shared Appian naming utilities for humanizing object names."""

import re


def humanize_object_name(name: str) -> str:
    """Turn 'AS_GSS_BL_ValidateSubmission' into 'validate submission'."""
    name = re.sub(r'^(?:[A-Z][A-Z0-9]{1,5}_){2,4}', '', name)
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    return name.replace('_', ' ').strip().lower()


def humanize_record_name(name: str) -> str:
    """Clean up a record type name for display."""
    name = re.sub(r'^(?:[A-Z][A-Z0-9]{1,5}_){1,4}', '', name)
    for suffix in ('_RecordType', '_SYNCEDRECORD', '_RECORD', '_Record'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    return name.replace('_', ' ').strip()


def clean_action_name(name: str) -> str:
    """Extract a readable action label from a raw action name.

    Handles SAIL expressions like:
      rule!AS_GSS_UT_displayDynamicLabel(bundleKey: "btn_ClaimTask")
      → "Claim Task"
    """
    if not name:
        return ''
    m = re.search(r'bundleKey[:\s]*"([^"]+)"', name)
    if m:
        key = m.group(1)
        key = re.sub(r'^(?:btn|lbl|txt)_', '', key)
        key = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', key)
        return key.replace('_', ' ').strip()
    if 'rule!' in name or 'a!local' in name or 'rv!record' in name:
        return ''
    return name.strip()


def extract_domain_term(name: str) -> str:
    """Extract a multi-word domain term from an Appian object name."""
    name = re.sub(r'^(?:[A-Z][A-Z0-9]{1,5}_){1,4}', '', name)
    for suffix in ('_RecordType', '_SYNCEDRECORD', '_RECORD', '_Record'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    name = re.sub(r'[_\s]+', ' ', name).strip().lower()
    name = re.sub(r'^(?:[a-z] )+', '', name).strip()
    return name


def collect_page_names(pages: list[dict]) -> list[str]:
    """Recursively collect page names from hierarchical site page structure."""
    names: list[str] = []
    for page in pages:
        name = page.get('static_name') or page.get('name_expr') or ''
        if name:
            names.append(name)
        names.extend(collect_page_names(page.get('children', [])))
    return names


def join_natural(items: list[str], limit: int = 8) -> str:
    """Join items naturally, truncating with '+ N more' if over limit."""
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) <= limit:
        return ', '.join(items[:-1]) + ' and ' + items[-1]
    return ', '.join(items[:limit]) + f' + {len(items) - limit} more'
