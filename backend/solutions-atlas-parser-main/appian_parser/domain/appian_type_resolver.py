"""Appian type name resolution."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TypeMapping:
    display: str
    category: str = "primitive"


class AppianTypeResolver:
    """Resolves Appian type names to user-friendly display names."""

    XSD_TYPE_MAP: dict[str, TypeMapping] = {
        'int': TypeMapping('Integer'),
        'integer': TypeMapping('Integer'),
        'long': TypeMapping('Long Integer'),
        'short': TypeMapping('Short Integer'),
        'byte': TypeMapping('Byte'),
        'string': TypeMapping('Text'),
        'boolean': TypeMapping('Boolean'),
        'decimal': TypeMapping('Decimal'),
        'double': TypeMapping('Double'),
        'float': TypeMapping('Float'),
        'date': TypeMapping('Date'),
        'datetime': TypeMapping('Date and Time'),
        'time': TypeMapping('Time'),
        'duration': TypeMapping('Duration'),
        'base64binary': TypeMapping('Binary'),
        'anyuri': TypeMapping('URI'),
        'positiveinteger': TypeMapping('Positive Integer'),
        'negativeinteger': TypeMapping('Negative Integer'),
        'nonnegativeinteger': TypeMapping('Non-Negative Integer'),
        'nonpositiveinteger': TypeMapping('Non-Positive Integer'),
        'unsignedint': TypeMapping('Unsigned Integer'),
        'unsignedlong': TypeMapping('Unsigned Long'),
    }

    APPIAN_TYPE_MAP: dict[str, TypeMapping] = {
        'Map': TypeMapping('Map', 'complex'),
        'Variant': TypeMapping('Any Type', 'complex'),
        'Text': TypeMapping('Text'),
        'Integer': TypeMapping('Integer'),
        'Boolean': TypeMapping('Boolean'),
        'Decimal': TypeMapping('Decimal'),
        'Date': TypeMapping('Date'),
        'DateTime': TypeMapping('Date and Time'),
        'Time': TypeMapping('Time'),
        'Document': TypeMapping('Document', 'complex'),
        'Folder': TypeMapping('Folder', 'complex'),
        'User': TypeMapping('User', 'complex'),
        'Group': TypeMapping('Group', 'complex'),
        'ProcessModel': TypeMapping('Process Model', 'complex'),
        'RecordType': TypeMapping('Record Type', 'complex'),
        'Expression': TypeMapping('Expression', 'complex'),
        'Dictionary': TypeMapping('Dictionary', 'complex'),
        'List': TypeMapping('List', 'complex'),
        'PagingInfo': TypeMapping('Paging Info', 'complex'),
        'DataSubset': TypeMapping('Data Subset', 'complex'),
        'Number (Integer)': TypeMapping('Integer'),
        'Number (Decimal)': TypeMapping('Decimal'),
    }

    APPIAN_NAMESPACE = 'http://www.appian.com/ae/types/2009'
    XML_SCHEMA_NAMESPACE = 'http://www.w3.org/2001/XMLSchema'

    _XSD_PREFIX_PATTERN = re.compile(r'^xsd:(\w+)(\?list)?$', re.IGNORECASE)
    _CURLY_BRACE_PATTERN = re.compile(r'^\{([^}]+)\}(\w+)(\?list)?$', re.IGNORECASE)
    _COLON_NAMESPACE_PATTERN = re.compile(r'^(.+):(\w+)(\?list)?$', re.IGNORECASE)
    _RECORD_TYPE_URN_PATTERN = re.compile(
        r'^urn:com:appian:recordtype:datatype:([a-f0-9\-]{36})(\?list)?$', re.IGNORECASE
    )

    @classmethod
    def resolve(cls, raw_type: Optional[str], record_type_cache: Optional[dict[str, str]] = None) -> str:
        if not raw_type or not raw_type.strip():
            return 'Unknown'
        raw_type = raw_type.strip()
        for resolver in [cls._try_xsd_prefix, cls._try_curly_brace_namespace,
                         cls._try_colon_namespace, cls._try_record_type_urn]:
            result = resolver(raw_type, record_type_cache)
            if result:
                return result
        return raw_type

    @classmethod
    def _try_xsd_prefix(cls, raw_type: str, _cache=None) -> Optional[str]:
        match = cls._XSD_PREFIX_PATTERN.match(raw_type)
        if match:
            mapping = cls.XSD_TYPE_MAP.get(match.group(1).lower())
            if mapping:
                is_list = match.group(2) is not None
                return f"{mapping.display} (List)" if is_list else mapping.display
        return None

    @classmethod
    def _try_curly_brace_namespace(cls, raw_type: str, _cache=None) -> Optional[str]:
        match = cls._CURLY_BRACE_PATTERN.match(raw_type)
        if match:
            resolved = cls._resolve_namespaced_type(match.group(1), match.group(2))
            is_list = match.group(3) is not None
            return f"{resolved} (List)" if is_list else resolved
        return None

    @classmethod
    def _try_colon_namespace(cls, raw_type: str, _cache=None) -> Optional[str]:
        match = cls._COLON_NAMESPACE_PATTERN.match(raw_type)
        if match:
            resolved = cls._resolve_namespaced_type(match.group(1), match.group(2))
            is_list = match.group(3) is not None
            return f"{resolved} (List)" if is_list else resolved
        return None

    @classmethod
    def _try_record_type_urn(cls, raw_type: str, cache=None) -> Optional[str]:
        match = cls._RECORD_TYPE_URN_PATTERN.match(raw_type)
        if match:
            uuid = match.group(1).lower()
            is_list = match.group(2) is not None
            if cache and uuid in cache:
                base = f"recordType!{cache[uuid]}"
            else:
                base = f"Record Type ({uuid[:8]}...)"
            return f"{base} (List)" if is_list else base
        return None

    @classmethod
    def _resolve_namespaced_type(cls, namespace: str, type_name: str) -> str:
        if cls.APPIAN_NAMESPACE in namespace:
            mapping = cls.APPIAN_TYPE_MAP.get(type_name)
            return mapping.display if mapping else type_name
        if cls.XML_SCHEMA_NAMESPACE in namespace:
            mapping = cls.XSD_TYPE_MAP.get(type_name.lower())
            return mapping.display if mapping else type_name
        if namespace and type_name:
            return f"type!{type_name}"
        return type_name

    @classmethod
    def is_primitive_type(cls, raw_type: Optional[str]) -> bool:
        if not raw_type:
            return False
        resolved = cls.resolve(raw_type)
        for m in cls.XSD_TYPE_MAP.values():
            if m.display == resolved and m.category == 'primitive':
                return True
        for m in cls.APPIAN_TYPE_MAP.values():
            if m.display == resolved and m.category == 'primitive':
                return True
        return False

    @classmethod
    def get_type_category(cls, raw_type: Optional[str]) -> str:
        if not raw_type:
            return 'unknown'
        resolved = cls.resolve(raw_type)
        for m in cls.XSD_TYPE_MAP.values():
            if m.display == resolved:
                return m.category
        for m in cls.APPIAN_TYPE_MAP.values():
            if m.display == resolved:
                return m.category
        if resolved.startswith('type!') or resolved.startswith('recordType!'):
            return 'custom'
        return 'unknown'
