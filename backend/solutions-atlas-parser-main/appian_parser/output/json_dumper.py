"""JSON output generation.

Writes errors to a structured JSON directory.
"""

import json
import os
from typing import Any

from appian_parser.domain.models import ParsedObject, ParseError, DumpOptions, DumpResult  # noqa: F401


class JSONDumper:
    """Writes parse errors to JSON output.

    Args:
        output_dir: Root directory for output files.
        pretty: Whether to pretty-print JSON (default True).
    """

    def __init__(self, output_dir: str, pretty: bool = True) -> None:
        self._output_dir = output_dir
        self._indent = 2 if pretty else None

    def write_errors(self, errors: list[ParseError]) -> None:
        """Write parsing errors (only if any exist)."""
        if not errors:
            return
        os.makedirs(self._output_dir, exist_ok=True)
        data = [{'file': e.file, 'error': e.error, 'object_type': e.object_type} for e in errors]
        self._write_json(os.path.join(self._output_dir, 'errors.json'), data)

    def _write_json(self, path: str, data: Any) -> None:
        """Write data as JSON to a file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=self._indent, ensure_ascii=False, default=str)
