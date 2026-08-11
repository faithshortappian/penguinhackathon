"""Derives a concise, LLM-navigational application description."""

from collections import defaultdict

from appian_parser.domain.models import ParsedObject
from appian_parser.domain.name_utils import (
    collect_page_names,
    humanize_object_name,
    join_natural,
)


def derive_description(
    bundle_entries: list[dict],
    parsed_objects: list[ParsedObject],
) -> str:
    """Build a compass-like app description targeting ~200-500 chars."""
    parts: list[str] = []

    prefix_part = _describe_app_prefixes(parsed_objects)
    if prefix_part:
        parts.append(prefix_part)
    else:
        app_descs = _get_application_descriptions(parsed_objects)
        if app_descs:
            parts.append(' '.join(app_descs))
        rt_part = _summarize_record_types(parsed_objects)
        if rt_part:
            parts.append(rt_part)

    site_part = _describe_sites(parsed_objects)
    if site_part:
        parts.append(site_part)

    ops_part = _describe_operations(bundle_entries)
    if ops_part:
        parts.append(ops_part)

    return ' '.join(parts)


def _get_application_descriptions(parsed_objects: list[ParsedObject]) -> list[str]:
    descs: list[str] = []
    for obj in parsed_objects:
        if obj.object_type == 'Application':
            desc = (obj.data.get('description') or '').strip()
            if desc:
                descs.append(desc.rstrip('.') + '.')
    return descs


def _summarize_record_types(parsed_objects: list[ParsedObject]) -> str:
    rts = sorted(obj.name for obj in parsed_objects if obj.object_type == 'Record Type')
    if not rts:
        return ''
    top = join_natural([humanize_object_name(n) for n in rts[:4]], limit=4)
    if len(rts) > 4:
        return f"{len(rts)} record types including {top}."
    return f"Manages {top} data."


def _describe_app_prefixes(parsed_objects: list[ParsedObject]) -> str:
    prefix_meta: dict[str, dict] = {}
    for obj in parsed_objects:
        if obj.object_type == 'Application':
            prefix = (obj.data.get('prefix') or '').strip()
            if prefix:
                name = obj.name
                for suffix in ('Full Application', 'Base Application', 'Base'):
                    if name.endswith(suffix):
                        name = name[:-len(suffix)].strip()
                desc = (obj.data.get('description') or '').strip()
                prefix_meta[prefix] = {'name': name, 'description': desc}

    prefix_objects: dict[str, list[ParsedObject]] = defaultdict(list)
    for obj in parsed_objects:
        if obj.object_type == 'Application':
            continue
        parts = obj.name.split('_')
        if len(parts) >= 3:
            prefix_objects['_'.join(parts[:2])].append(obj)

    if len(prefix_objects) <= 1:
        return ''

    significant: list[tuple[str, list[ParsedObject]]] = []
    minor_count = 0
    for prefix, objs in sorted(prefix_objects.items(), key=lambda x: -len(x[1])):
        if len(objs) >= 5:
            significant.append((prefix, objs))
        else:
            minor_count += len(objs)

    labeled: list[str] = []
    for prefix, objs in significant:
        meta = prefix_meta.get(prefix, {})
        app_name = meta.get('name', prefix)
        brief = _derive_prefix_brief(objs, meta.get('description', ''))
        if brief:
            labeled.append(f"{app_name} [{prefix}] ({len(objs)} objects — {brief})")
        else:
            labeled.append(f"{app_name} [{prefix}] ({len(objs)} objects)")

    result = f"Contains objects from: {join_natural(labeled, limit=5)}."
    if minor_count:
        result = result[:-1] + f", plus {minor_count} shared/minor objects."
    return result


def _derive_prefix_brief(objs: list[ParsedObject], app_description: str) -> str:
    generic_patterns = ('all objects for', 'full application', 'base application')
    if app_description and not any(p in app_description.lower() for p in generic_patterns):
        return app_description.rstrip('.')

    record_types = [o.name for o in objs if o.object_type == 'Record Type']
    if record_types:
        top = join_natural([humanize_object_name(n) for n in record_types[:3]], limit=3)
        if len(record_types) > 3:
            return f"{len(record_types)} record types including {top}"
        return f"manages {top} data"
    return ''


def _describe_sites(parsed_objects: list[ParsedObject]) -> str:
    site_descriptions: list[str] = []
    for obj in parsed_objects:
        if obj.object_type != 'Site':
            continue
        page_count = len(collect_page_names(obj.data.get('pages', [])))
        if page_count:
            site_descriptions.append(f"{obj.name} ({page_count} pages)")
        else:
            site_descriptions.append(obj.name)
    if not site_descriptions:
        return ''
    return f"Sites: {join_natural(site_descriptions)}."


def _describe_operations(bundle_entries: list[dict]) -> str:
    by_type: dict[str, list[str]] = defaultdict(list)
    for entry in bundle_entries:
        btype = entry.get('bundle_type', '')
        for name in entry.get('key_objects', []):
            by_type[btype].append(name)

    labels: list[str] = []
    for btype in ('action', 'page', 'dashboard', 'process', 'web_api'):
        for name in by_type.get(btype, []):
            h = humanize_object_name(name)
            if h and h not in labels:
                labels.append(h)

    if not labels:
        return ''
    return f"Key operations include: {join_natural(labels, limit=10)}."
