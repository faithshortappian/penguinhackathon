"""Document writer — extracts binary document files and writes an index.

Scans the extracted package temp directory for document binary files,
copies them to the output documents/ folder, and writes a _index.json
mapping UUIDs to metadata (name, extension, mime type, size, constants).
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
from typing import Any

from appian_parser.domain.models import ParsedObject


# File extensions we consider image/icon assets worth extracting.
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.bmp', '.webp'}


class DocumentWriter:
    """Extracts document binaries from the package and writes an index."""

    def __init__(self, pretty: bool = True):
        self._indent = 2 if pretty else None

    def write(
        self,
        temp_dir: str,
        output_dir: str,
        parsed_objects: list[ParsedObject],
    ) -> dict[str, Any]:
        """Extract document binaries and write documents/_index.json.

        Merges with existing _index.json if present (for delta parses).
        Never removes entries — documents are append-only.

        Args:
            temp_dir: Extracted package temp directory (contains content/ folder).
            output_dir: Root output directory (documents/ will be created inside).
            parsed_objects: All parsed objects — used to map constants to documents.

        Returns:
            The index dict that was written (for testing/inspection).
        """
        docs_dir = os.path.join(output_dir, 'documents')
        os.makedirs(docs_dir, exist_ok=True)

        # Load existing index if present (for merge during delta parses).
        existing_index = self._load_existing_index(docs_dir)

        # Build constant → document UUID mapping from parsed constants.
        constant_map = self._build_constant_map(parsed_objects)

        # Find and copy document binaries.
        new_index: dict[str, dict] = {}
        content_dir = self._find_content_dir(temp_dir)
        if not content_dir:
            # No content dir in this package — preserve existing index as-is.
            if existing_index:
                return self._write_index(docs_dir, existing_index)
            return self._write_index(docs_dir, new_index)

        for entry in os.listdir(content_dir):
            entry_path = os.path.join(content_dir, entry)
            if not os.path.isdir(entry_path):
                continue

            # Each document binary lives in content/{uuid}/file.{ext}
            for filename in os.listdir(entry_path):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue

                src_path = os.path.join(entry_path, filename)
                if not os.path.isfile(src_path):
                    continue

                # The folder name IS the document UUID.
                doc_uuid = entry
                dest_filename = f"{doc_uuid}{ext}"
                dest_path = os.path.join(docs_dir, dest_filename)
                shutil.copy2(src_path, dest_path)

                # Find metadata from parsed document objects.
                doc_meta = self._find_document_metadata(doc_uuid, parsed_objects)
                mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

                new_index[doc_uuid] = {
                    'name': doc_meta.get('name') if doc_meta else None,
                    'description': doc_meta.get('description') if doc_meta else None,
                    'version_uuid': doc_meta.get('version_uuid') if doc_meta else None,
                    'file': dest_filename,
                    'extension': ext.lstrip('.'),
                    'mime_type': mime_type,
                    'size_bytes': os.path.getsize(dest_path),
                    'constants': constant_map.get(doc_uuid, []),
                }

        # Merge: existing entries preserved, new entries added/updated.
        merged_index = {**existing_index, **new_index}
        return self._write_index(docs_dir, merged_index)

    def _load_existing_index(self, docs_dir: str) -> dict[str, dict]:
        """Load existing _index.json if present, for merge during delta parses."""
        index_path = os.path.join(docs_dir, '_index.json')
        if not os.path.isfile(index_path):
            return {}
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('documents', {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _find_content_dir(self, temp_dir: str) -> str | None:
        """Locate the content/ directory in the extracted package."""
        # Direct child.
        candidate = os.path.join(temp_dir, 'content')
        if os.path.isdir(candidate):
            return candidate
        # One level deeper (nested ZIP extraction).
        for entry in os.listdir(temp_dir):
            candidate = os.path.join(temp_dir, entry, 'content')
            if os.path.isdir(candidate):
                return candidate
        return None

    def _build_constant_map(self, parsed_objects: list[ParsedObject]) -> dict[str, list[str]]:
        """Map document UUIDs to the constant names that reference them.

        Constants of type CollaborationDocument have a value that is either
        the raw document UUID (pre-resolution) or the resolved document name
        (post-resolution). We match both cases.
        """
        # Build a name→uuid lookup for documents.
        doc_name_to_uuid: dict[str, str] = {}
        for obj in parsed_objects:
            if obj.object_type == 'Document':
                doc_name_to_uuid[obj.name] = obj.uuid

        mapping: dict[str, list[str]] = {}
        for obj in parsed_objects:
            if obj.object_type != 'Constant':
                continue
            data = obj.data
            raw_type = data.get('raw_value_type', '') or data.get('value_type', '') or ''
            if 'CollaborationDocument' not in raw_type and 'Document' not in raw_type:
                continue
            value = data.get('value')
            if not value or not isinstance(value, str):
                continue

            # Value could be a UUID (pre-resolution) or a document name (post-resolution).
            doc_uuid = None
            if value.startswith('_a-'):
                doc_uuid = value
            else:
                doc_uuid = doc_name_to_uuid.get(value)

            if doc_uuid:
                mapping.setdefault(doc_uuid, []).append(obj.name)
        return mapping

    def _find_document_metadata(
        self, doc_uuid: str, parsed_objects: list[ParsedObject]
    ) -> dict[str, Any] | None:
        """Find the parsed Document object matching this UUID."""
        for obj in parsed_objects:
            if obj.object_type == 'Document' and obj.uuid == doc_uuid:
                return obj.data
        return None

    def _write_index(self, docs_dir: str, index: dict) -> dict:
        """Write _index.json to the documents directory."""
        output = {
            'total': len(index),
            'documents': index,
        }
        index_path = os.path.join(docs_dir, '_index.json')
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=self._indent, ensure_ascii=False)
        return output
