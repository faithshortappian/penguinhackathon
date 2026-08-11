"""Generates one business-level summary file per bundle type from existing bundle output."""

from __future__ import annotations

import json
import os
from typing import Any

_BUNDLE_TYPES = ('actions', 'processes', 'pages', 'sites', 'dashboards', 'web_apis')


class BundleSummarizer:
    """Reads bundles dir and writes one markdown summary per bundle type."""

    def summarize(self, output_dir: str) -> str:
        """Generate summaries. Returns path to summaries directory."""
        bundles_dir = os.path.join(output_dir, 'bundles')
        summaries_dir = os.path.join(output_dir, 'summaries')
        os.makedirs(summaries_dir, exist_ok=True)

        # Load index for app overview
        index_path = os.path.join(bundles_dir, '_index.json')
        index = self._load_json(index_path) if os.path.isfile(index_path) else {}

        written = []
        for bundle_type in _BUNDLE_TYPES:
            type_dir = os.path.join(bundles_dir, bundle_type)
            if not os.path.isdir(type_dir):
                continue

            bundles = self._load_bundles(type_dir)
            if not bundles:
                continue

            md = self._render(bundle_type, bundles, index)
            out_path = os.path.join(summaries_dir, f'{bundle_type}.md')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(md)
            written.append(out_path)

        # Write orphans summary if present
        orphans_path = os.path.join(bundles_dir, '_orphans.json')
        if os.path.isfile(orphans_path):
            orphans = self._load_json(orphans_path)
            md = self._render_orphans(orphans)
            out_path = os.path.join(summaries_dir, 'orphans.md')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(md)
            written.append(out_path)

        return summaries_dir

    # ── Rendering ───────────────────────────────────────────────────────

    def _render(self, bundle_type: str, bundles: list[dict], index: dict) -> str:
        title = bundle_type.replace('_', ' ').title()
        lines = [f'# {title} Summary', '', f'Total: {len(bundles)} bundle(s)', '']

        for b in sorted(bundles, key=lambda x: x.get('_metadata', {}).get('root_object', {}).get('name', '')):
            meta = b.get('_metadata', {})
            ep = b.get('entry_point', {})
            root = meta.get('root_object', {})

            lines.append(f'## {root.get("name", "Unknown")}')
            lines.append('')

            # Entry point details
            desc = self._get_description(b)
            if desc:
                lines.append(f'**Description:** {desc}')

            if ep.get('record_type'):
                lines.append(f'**Record Type:** {ep["record_type"]}')
            if ep.get('action_type'):
                lines.append(f'**Action Type:** {ep["action_type"]}')
            if ep.get('process_model'):
                lines.append(f'**Process Model:** {ep["process_model"]}')
            if ep.get('http_method'):
                lines.append(f'**HTTP Method:** {ep["http_method"]}')
            if ep.get('url_alias'):
                lines.append(f'**URL:** {ep["url_alias"]}')
            if ep.get('url_stub'):
                lines.append(f'**URL Stub:** {ep["url_stub"]}')
            if ep.get('complexity_score') is not None:
                lines.append(f'**Complexity:** {ep["complexity_score"]}')
            if ep.get('total_nodes') is not None:
                lines.append(f'**Nodes:** {ep["total_nodes"]}')

            lines.append(f'**Objects in bundle:** {meta.get("total_objects", "?")}')
            lines.append('')

            # Object type breakdown
            objects = b.get('objects', {})
            if objects:
                lines.append('**Contains:**')
                for obj_type, items in sorted(objects.items()):
                    names = sorted(o.get('name', '?') for o in items)
                    lines.append(f'- {obj_type} ({len(items)}): {", ".join(names)}')
                lines.append('')

            # Views for page bundles
            if ep.get('views'):
                lines.append('**Views:**')
                for v in ep['views']:
                    lines.append(f'- {v.get("view_type", "?")} — {v.get("view_name") or v.get("url_stub", "?")}')
                lines.append('')

            # Site pages
            if ep.get('pages'):
                lines.append('**Pages:**')
                self._render_pages(ep['pages'], lines, indent=0)
                lines.append('')

            lines.append('---')
            lines.append('')

        return '\n'.join(lines)

    def _render_orphans(self, orphans: dict) -> str:
        meta = orphans.get('_metadata', {})
        lines = [
            '# Orphaned Objects',
            '',
            f'Total: {meta.get("total_objects", "?")} objects not reachable from any entry point.',
            '',
        ]
        for obj_type, items in sorted(orphans.get('objects', {}).items()):
            lines.append(f'## {obj_type} ({len(items)})')
            lines.append('')
            for o in sorted(items, key=lambda x: x.get('name', '')):
                desc = o.get('description') or ''
                suffix = f' — {desc}' if desc else ''
                lines.append(f'- {o.get("name", "?")}{suffix}')
            lines.append('')

        return '\n'.join(lines)

    def _render_pages(self, pages: list[dict], lines: list[str], indent: int) -> None:
        prefix = '  ' * indent + '- '
        for p in pages:
            lines.append(f'{prefix}{p.get("name", "?")}')
            for child in p.get('children', []):
                self._render_pages([child], lines, indent + 1)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _get_description(self, bundle: dict) -> str | None:
        """Try to find a description from the root object in the bundle."""
        ep = bundle.get('entry_point', {})
        if ep.get('description'):
            return ep['description']
        # Look in objects for the root
        root_name = bundle.get('_metadata', {}).get('root_object', {}).get('name')
        for items in bundle.get('objects', {}).values():
            for obj in items:
                if obj.get('name') == root_name and obj.get('description'):
                    return obj['description']
        return None

    def _load_bundles(self, type_dir: str) -> list[dict]:
        bundles = []
        for fname in sorted(os.listdir(type_dir)):
            if not fname.endswith('.json'):
                continue
            data = self._load_json(os.path.join(type_dir, fname))
            if data:
                bundles.append(data)
        return bundles

    @staticmethod
    def _load_json(path: str) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
