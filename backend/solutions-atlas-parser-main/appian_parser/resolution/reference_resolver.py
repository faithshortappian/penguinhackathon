"""Reference resolution coordinator.

Resolves UUID references, record type URNs, and translation string URNs
in parsed object data. Works entirely in-memory using data from the
parsed objects themselves.
"""

from typing import Any

from appian_parser.domain.constants import CANONICAL_RE, SAIL_CODE_FIELDS, UUID_FIELDS
from appian_parser.domain.field_walker import apply_to_field_paths
from appian_parser.resolution.label_bundle_resolver import LabelBundleResolver
from appian_parser.resolution.uuid_resolver import UUIDResolver
from appian_parser.resolution.record_type_resolver import RecordTypeURNResolver
from appian_parser.resolution.translation_resolver import TranslationResolver
from appian_parser.resolution.uuid_utils import UUIDUtils


class ReferenceResolver:
    """Resolves UUID references, record type URNs, and translation string URNs.

    Builds in-memory lookup caches from parsed objects, then walks configured
    field paths to resolve all opaque identifiers to human-readable names.

    Args:
        parsed_objects: List of ParsedObject instances to build caches from.
    """

    def __init__(self, parsed_objects: list, label_lookup: dict[str, str] | None = None) -> None:
        uuid_lookup = self._build_uuid_lookup(parsed_objects)
        rt_cache, field_cache, rel_cache = self._build_record_type_cache(parsed_objects)
        translation_cache = self._build_translation_cache(parsed_objects)

        self._uuid_resolver = UUIDResolver(uuid_lookup)
        self._rt_resolver = RecordTypeURNResolver(rt_cache, field_cache, rel_cache)
        self._translation_resolver = TranslationResolver(translation_cache)
        self._label_resolver = LabelBundleResolver(label_lookup or {})
        self._uuid_lookup = uuid_lookup

    def resolve_all(self, parsed_objects: list, locale: str = 'en-US') -> None:
        """Resolve all references in all parsed objects (mutates in place).

        Args:
            parsed_objects: Objects to resolve. Modified in place.
            locale: Locale for translation string resolution.
        """
        for obj in parsed_objects:
            self._resolve_object(obj, locale)

    def resolve_sail_code(self, code: str, locale: str = 'en-US') -> str:
        """Resolve all references in a SAIL code string.

        Args:
            code: Raw SAIL code with opaque identifiers.
            locale: Locale for translation resolution.

        Returns:
            SAIL code with identifiers resolved to human-readable names.
        """
        if not code:
            return code
        code = self._uuid_resolver.resolve_sail_code(code)
        code = self._rt_resolver.resolve_sail_code(code)
        code = self._translation_resolver.resolve_sail_code(code, locale)
        code = self._label_resolver.resolve_sail_code(code)
        return code

    def resolve_uuid(self, uuid_value: str) -> str:
        """Resolve a single UUID to its object name."""
        return UUIDUtils.resolve_uuid(uuid_value, self._uuid_lookup)

    # ── Cache Builders ───────────────────────────────────────────────────

    @staticmethod
    def _build_uuid_lookup(parsed_objects: list) -> dict[str, dict[str, Any]]:
        """Build UUID → {name, object_type} lookup with base and canonical indexing."""
        lookup: dict[str, dict[str, Any]] = {}
        for obj in parsed_objects:
            entry = {'name': obj.name, 'object_type': obj.object_type}
            lookup[obj.uuid] = entry

            base = UUIDUtils.extract_base_uuid(obj.uuid)
            if base and base != obj.uuid:
                lookup.setdefault(base, entry)

            m = CANONICAL_RE.match(obj.uuid)
            if m:
                lookup.setdefault(m.group(1), entry)
        return lookup

    @staticmethod
    def _build_record_type_cache(parsed_objects: list) -> tuple[
        dict[str, str],
        dict[tuple[str, str], str],
        dict[tuple[str, str], tuple[str, str | None]],
    ]:
        """Build record type, field, and relationship caches.

        Returns:
            Tuple of (record_types, fields, relationships) dicts.
            - record_types: rt_uuid → rt_name
            - fields: (rt_uuid, field_uuid) → field_name
            - relationships: (rt_uuid, rel_uuid) → (rel_name, target_rt_uuid)
        """
        record_types: dict[str, str] = {}
        fields: dict[tuple[str, str], str] = {}
        relationships: dict[tuple[str, str], tuple[str, str | None]] = {}

        for obj in parsed_objects:
            if obj.object_type != 'Record Type':
                continue

            data = obj.data
            base = UUIDUtils.extract_base_uuid(obj.uuid)
            rt_keys = [obj.uuid]
            if base and base != obj.uuid:
                rt_keys.append(base)

            for rk in rt_keys:
                record_types.setdefault(rk, obj.name)

            for field in data.get('fields', []):
                fid = field.get('field_uuid')
                fname = field.get('field_name', fid)
                if not fid:
                    continue
                fid_base = UUIDUtils.extract_base_uuid(fid)
                for rk in rt_keys:
                    fields.setdefault((rk, fid), fname)
                    if fid_base and fid_base != fid:
                        fields.setdefault((rk, fid_base), fname)

            for rel in data.get('relationships', []):
                rid = rel.get('relationship_uuid')
                if not rid:
                    continue
                val = (rel.get('relationship_name', rid), rel.get('target_record_type_uuid'))
                rid_base = UUIDUtils.extract_base_uuid(rid)
                for rk in rt_keys:
                    relationships.setdefault((rk, rid), val)
                    if rid_base and rid_base != rid:
                        relationships.setdefault((rk, rid_base), val)

        return record_types, fields, relationships

    @staticmethod
    def _build_translation_cache(parsed_objects: list) -> dict[str, dict[str, str]]:
        """Build translation UUID → {locale: text} cache."""
        cache: dict[str, dict[str, str]] = {}
        for obj in parsed_objects:
            if obj.object_type != 'Translation String':
                continue
            translations = {
                t['locale']: t['value']
                for t in obj.data.get('translations', [])
                if t.get('locale') and t.get('value')
            }
            if translations:
                cache[obj.uuid] = translations
                base = UUIDUtils.extract_base_uuid(obj.uuid)
                if base and base != obj.uuid:
                    cache.setdefault(base, translations)
        return cache

    # ── Object Field Walking ─────────────────────────────────────────────

    def _resolve_object(self, obj: Any, locale: str) -> None:
        """Resolve references in a single parsed object based on its type."""
        data = obj.data
        otype = obj.object_type

        for path in SAIL_CODE_FIELDS.get(otype, []):
            apply_to_field_paths(data, path, lambda v: self.resolve_sail_code(v, locale))

        for path in UUID_FIELDS.get(otype, []):
            apply_to_field_paths(data, path, self.resolve_uuid)
