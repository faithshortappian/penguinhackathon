"""Extracts domain tags from parsed Appian objects."""

import re
from collections import defaultdict

from appian_parser.domain.models import ParsedObject
from appian_parser.domain.name_utils import collect_page_names, extract_domain_term

_DOMAIN_STOPWORDS = {
    'record', 'recordtype', 'type', 'syncedrecord', 'data', 'dynamic',
    'ref', 'cfg', 'config', 'configuration', 'map', 'mapping', 'mappings',
    'r', 'a', 't', 'the', 'and', 'or', 'for', 'of', 'in', 'to',
    'example', 'test', 'deprecated', 'internal', 'zinternaluse',
    'one', 'many', 'all', 'set', 'field', 'fields', 'entity',
    'backed', 'expression', 'synced', 'general', 'related', 'site', 'page',
    'key', 'txt', 'info', 'information', 'details', 'list', 'item', 'items',
    'dynamic record', 'entity type', 'expression backed one to one related record',
    'expression backed many to one related record',
}

_MAX_DOMAINS = 25


def extract_domains(
    bundle_entries: list[dict],
    parsed_objects: list[ParsedObject],
) -> list[str]:
    """Extract multi-word domain tags from record types, site pages, and actions."""
    raw_terms: list[str] = []

    for obj in parsed_objects:
        if obj.object_type == 'Record Type':
            term = extract_domain_term(obj.name)
            if term:
                raw_terms.append(term)

    for obj in parsed_objects:
        if obj.object_type == 'Site':
            for name in collect_page_names(obj.data.get('pages', [])):
                if not name.startswith('#"urn:'):
                    term = extract_domain_term(name)
                    if term:
                        raw_terms.append(term)

    for entry in bundle_entries:
        if entry.get('bundle_type') == 'action' and entry.get('parent_name'):
            term = extract_domain_term(entry['parent_name'])
            if term:
                raw_terms.append(term)

    # Collect known prefixes to filter
    known_prefixes: set[str] = set()
    for obj in parsed_objects:
        if obj.object_type == 'Application':
            prefix = (obj.data.get('prefix') or '').strip().lower()
            if prefix:
                known_prefixes.add(prefix)
                for seg in prefix.split('_'):
                    known_prefixes.add(seg.lower())
            for word in obj.name.split():
                if len(word) <= 5 and word.isupper():
                    known_prefixes.add(word.lower())

    seen: set[str] = set()
    domains: list[str] = []
    for term in raw_terms:
        cleaned = term
        for prefix in sorted(known_prefixes, key=len, reverse=True):
            if cleaned.startswith(prefix + ' '):
                cleaned = cleaned[len(prefix):].strip()
        if not cleaned or len(cleaned) <= 2:
            continue
        if (cleaned not in seen
                and cleaned not in _DOMAIN_STOPWORDS
                and not cleaned.endswith(' field')
                and not cleaned.endswith(' synced')
                and re.fullmatch(r'[a-z ]+', cleaned)):
            seen.add(cleaned)
            domains.append(cleaned)

    return domains[:_MAX_DOMAINS]
