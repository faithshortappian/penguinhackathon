"""Resolves i18n label bundle calls to their actual display text.

Replaces patterns like:
  rule!AS_GSS_UT_displayDynamicLabel(bundleKey: "lbl_Sign")
with the resolved label value:
  "Sign"
"""
import re
from typing import List

# Matches label bundle calls without an arguments parameter.
# Pattern 1: rule!xxx(bundleKey: "key")
# Pattern 2: rule!xxx(\n  bundle: ...,\n  bundleKey: "key"\n)
# Excludes calls that have an `arguments:` parameter after the bundleKey.
_LABEL_CALL_RE = re.compile(
    r'rule!\w+\(\s*(?:bundle\s*:\s*[^,]+,\s*)?bundleKey\s*:\s*"([^"]+)"\s*\)',
    re.DOTALL,
)


class LabelBundleResolver:
    """Resolves i18n label bundle references in SAIL code."""

    def __init__(self, label_lookup: dict[str, str]) -> None:
        self._lookup = label_lookup

    @staticmethod
    def build_lookup(properties_files: List[str]) -> dict[str, str]:
        """Parse .properties files into a merged key→value dict."""
        lookup: dict[str, str] = {}
        for path in properties_files:
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            lookup.setdefault(k.strip(), v.strip())
            except OSError:
                continue
        return lookup

    def resolve_sail_code(self, code: str) -> str:
        """Replace label bundle calls with resolved text."""
        if not code or not self._lookup:
            return code

        def _replace(m: re.Match) -> str:
            key = m.group(1)
            value = self._lookup.get(key)
            return f'"{value}"' if value is not None else m.group(0)

        return _LABEL_CALL_RE.sub(_replace, code)
