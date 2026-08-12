"""Diff hash service for object comparison."""
import hashlib
import json
from typing import Any, Dict


class DiffHashService:
    """Service for generating diff hashes."""
    
    EXCLUDED_FIELDS = {
        'version_uuid', 'versionUuid', 'history', 'created_at', 'updated_at',
        'id', 'object_id', 'package_id', 'parent_uuid', 'raw_xml'
    }
    
    @staticmethod
    def generate_hash(data: Dict[str, Any]) -> str:
        """Generate SHA-512 hash for data."""
        normalized = DiffHashService._normalize_data(data)
        json_str = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        return hashlib.sha512(json_str.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _normalize_data(data: Any) -> Any:
        """Normalize data by removing excluded fields."""
        if isinstance(data, dict):
            return {
                k: DiffHashService._normalize_data(v)
                for k, v in data.items()
                if k not in DiffHashService.EXCLUDED_FIELDS
            }
        elif isinstance(data, list):
            return [DiffHashService._normalize_data(item) for item in data]
        else:
            return data