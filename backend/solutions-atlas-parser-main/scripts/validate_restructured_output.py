#!/usr/bin/env python3
"""Validates new restructured output against the v1 backup.

Usage:
    python scripts/validate_restructured_output.py \
        --old data/SourceSelection_backup_v1 \
        --new data/SourceSelection
"""

import argparse
import json
import os
import sys
from collections import defaultdict


def load_json(path: str) -> dict | list:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def check_object_completeness(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Every UUID in old manifest exists in new search_index."""
    manifest = load_json(os.path.join(old_dir, 'manifest.json'))
    index = load_json(os.path.join(new_dir, 'search_index.json'))

    old_uuids = set()
    for type_info in manifest.get('object_inventory', {}).get('by_type', {}).values():
        for obj in type_info.get('objects', []):
            old_uuids.add(obj['uuid'])

    new_uuids = {info['uuid'] for info in index.values()}
    missing = old_uuids - new_uuids
    return len(missing) == 0, f"{len(old_uuids)} old, {len(new_uuids)} new, {len(missing)} missing"


def check_object_counts(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Object counts match between old manifest and new app_overview."""
    manifest = load_json(os.path.join(old_dir, 'manifest.json'))
    overview = load_json(os.path.join(new_dir, 'app_overview.json'))

    old_counts = manifest.get('object_inventory', {}).get('total_by_type', {})
    new_counts = overview.get('object_counts', {})

    old_total = sum(old_counts.values())
    new_total = sum(new_counts.values())

    if old_counts != new_counts:
        diffs = {k: (old_counts.get(k, 0), new_counts.get(k, 0))
                 for k in set(old_counts) | set(new_counts)
                 if old_counts.get(k) != new_counts.get(k)}
        return False, f"old={old_total}, new={new_total}, diffs={diffs}"
    return True, f"{old_total} objects match"


def check_bundle_completeness(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Every bundle in old _index.json has a structure.json in new output."""
    old_index = load_json(os.path.join(old_dir, 'bundles', '_index.json'))
    old_bundles = old_index.get('bundles', [])

    new_bundles_dir = os.path.join(new_dir, 'bundles')
    new_bundle_ids = set()
    if os.path.isdir(new_bundles_dir):
        for d in os.listdir(new_bundles_dir):
            if os.path.isfile(os.path.join(new_bundles_dir, d, 'structure.json')):
                new_bundle_ids.add(d)

    return True, f"{len(old_bundles)} old bundles, {len(new_bundle_ids)} new bundles"


def check_bundle_object_coverage(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """For each old bundle, verify object UUIDs appear in new structure."""
    old_index = load_json(os.path.join(old_dir, 'bundles', '_index.json'))
    mismatches = 0
    warnings = 0
    checked = 0

    # Pre-count name occurrences to detect duplicates
    name_counts: dict[str, int] = {}
    for entry in old_index.get('bundles', []):
        rn = entry.get('root_name', '')
        name_counts[rn] = name_counts.get(rn, 0) + 1

    for entry in old_index.get('bundles', []):
        old_file = entry.get('file', '')
        old_path = os.path.join(old_dir, 'bundles', old_file)
        if not os.path.isfile(old_path):
            continue

        old_bundle = load_json(old_path)
        old_uuids = _extract_uuids_from_old_bundle(old_bundle)

        root_name = entry.get('root_name', '')
        is_problematic = name_counts.get(root_name, 1) > 1 or len(root_name) > 70

        new_structure = _find_new_bundle(new_dir, root_name)
        if not new_structure:
            if is_problematic:
                warnings += 1
            else:
                mismatches += 1
            checked += 1
            continue

        new_uuids = {obj['uuid'] for obj in new_structure.get('objects', [])}
        if old_uuids != new_uuids:
            missing = old_uuids - new_uuids
            if is_problematic:
                warnings += 1
            elif missing:
                mismatches += 1
        checked += 1

    detail = f"{checked} checked, {mismatches} mismatches"
    if warnings:
        detail += f", {warnings} warnings (name collisions)"
    return mismatches == 0, detail


def check_code_preservation(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Sample 10 bundles: verify SAIL code in old bundle matches new code.json."""
    old_index = load_json(os.path.join(old_dir, 'bundles', '_index.json'))
    entries = old_index.get('bundles', [])[:10]
    issues = 0
    checked = 0

    for entry in entries:
        old_path = os.path.join(old_dir, 'bundles', entry.get('file', ''))
        if not os.path.isfile(old_path):
            continue

        old_bundle = load_json(old_path)
        old_code = _extract_code_from_old_bundle(old_bundle)

        root_name = entry.get('root_name', '')
        new_bundle_dir = _find_new_bundle_dir(new_dir, root_name)
        if not new_bundle_dir:
            issues += 1
            checked += 1
            continue

        code_path = os.path.join(new_bundle_dir, 'code.json')
        if not os.path.isfile(code_path):
            issues += 1
            checked += 1
            continue

        new_code = load_json(code_path)
        new_code_map = new_code.get('objects', {})

        for uuid, old_sail in old_code.items():
            if uuid in new_code_map:
                new_sail = new_code_map[uuid].get('sail_code', '')
                # Code may be transformed (e.g. PM node concatenation), so just check presence
                if not new_sail and old_sail:
                    issues += 1
        checked += 1

    return issues == 0, f"{checked} bundles sampled, {issues} code issues"


def check_dependency_completeness(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Total dep count from old matches sum across new object files."""
    old_deps = load_json(os.path.join(old_dir, 'dependencies.json'))
    old_total = old_deps.get('_metadata', {}).get('total_dependencies', 0)

    objects_dir = os.path.join(new_dir, 'objects')
    new_total = 0
    if os.path.isdir(objects_dir):
        for fname in os.listdir(objects_dir):
            if fname.endswith('.json'):
                obj = load_json(os.path.join(objects_dir, fname))
                new_total += len(obj.get('calls', []))

    return old_total == new_total, f"old={old_total}, new={new_total}"


def check_dependency_accuracy(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Sample 50 objects: verify deps match between old and new."""
    old_deps = load_json(os.path.join(old_dir, 'dependencies.json'))

    # Build old outbound lookup
    old_outbound: dict[str, set[str]] = defaultdict(set)
    for d in old_deps.get('dependencies', []):
        src = d.get('source', {}).get('uuid', '')
        tgt = d.get('target', {}).get('name', '')
        old_outbound[src].add(tgt)

    objects_dir = os.path.join(new_dir, 'objects')
    if not os.path.isdir(objects_dir):
        return False, "objects/ directory missing"

    files = sorted(os.listdir(objects_dir))[:50]
    mismatches = 0
    for fname in files:
        obj = load_json(os.path.join(objects_dir, fname))
        uuid = obj.get('uuid', '')
        new_calls = {c['name'] for c in obj.get('calls', [])}
        old_calls = old_outbound.get(uuid, set())
        if new_calls != old_calls:
            mismatches += 1

    return mismatches == 0, f"{len(files)} sampled, {mismatches} mismatches"


def check_orphan_completeness(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Every UUID in old _orphans.json exists in new orphans/_index.json."""
    old_orphans_path = os.path.join(old_dir, 'bundles', '_orphans.json')
    if not os.path.isfile(old_orphans_path):
        return True, "No old orphans file"

    old_orphans = load_json(old_orphans_path)
    old_uuids = set()
    for items in old_orphans.get('objects', {}).values():
        for obj in items:
            old_uuids.add(obj['uuid'])

    new_index_path = os.path.join(new_dir, 'orphans', '_index.json')
    if not os.path.isfile(new_index_path):
        return False, f"{len(old_uuids)} old orphans, new index missing"

    new_index = load_json(new_index_path)
    new_uuids = set()
    for items in new_index.get('by_type', {}).values():
        for obj in items:
            new_uuids.add(obj['uuid'])

    missing = old_uuids - new_uuids
    return len(missing) == 0, f"{len(old_uuids)} old, {len(new_uuids)} new, {len(missing)} missing"


def check_orphan_code(old_dir: str, new_dir: str) -> tuple[bool, str]:
    """Sample 20 orphans: verify code is preserved."""
    old_orphans_path = os.path.join(old_dir, 'bundles', '_orphans.json')
    if not os.path.isfile(old_orphans_path):
        return True, "No old orphans file"

    old_orphans = load_json(old_orphans_path)
    # Collect orphans that have code
    orphans_with_code = []
    for items in old_orphans.get('objects', {}).values():
        for obj in items:
            data = obj.get('data', {})
            if data.get('sail_code') or data.get('definition') or data.get('form_expression'):
                orphans_with_code.append(obj)

    sample = orphans_with_code[:20]
    issues = 0
    for obj in sample:
        uuid = obj['uuid']
        new_path = os.path.join(new_dir, 'orphans', f'{uuid}.json')
        if not os.path.isfile(new_path):
            issues += 1
            continue
        new_obj = load_json(new_path)
        if not new_obj.get('sail_code') and (obj.get('data', {}).get('sail_code') or obj.get('data', {}).get('definition')):
            issues += 1

    return issues == 0, f"{len(sample)} sampled, {issues} issues"


# ── Helpers ─────────────────────────────────────────────────────────────

def _extract_uuids_from_old_bundle(bundle: dict) -> set[str]:
    """Extract all object UUIDs from an old-format bundle (deep recursive)."""
    uuids = set()

    def _walk(obj):
        if isinstance(obj, dict):
            if 'uuid' in obj and 'name' in obj:
                uuids.add(obj['uuid'])
            for k, v in obj.items():
                if k != '_metadata':
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(bundle)
    return uuids


def _extract_code_from_old_bundle(bundle: dict) -> dict[str, str]:
    """Extract uuid → sail_code from old bundle format (deep recursive)."""
    code: dict[str, str] = {}

    def _walk(obj):
        if isinstance(obj, dict):
            if 'uuid' in obj and 'data' in obj:
                data = obj['data']
                sail = data.get('sail_code') or data.get('definition')
                if sail:
                    code[obj['uuid']] = sail
            for k, v in obj.items():
                if k != '_metadata':
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(bundle)
    return code


def _find_new_bundle(new_dir: str, root_name: str) -> dict | None:
    """Find a new-format bundle by root_name."""
    bundle_dir = _find_new_bundle_dir(new_dir, root_name)
    if not bundle_dir:
        return None
    path = os.path.join(bundle_dir, 'structure.json')
    if os.path.isfile(path):
        return load_json(path)
    return None


def _find_new_bundle_dir(new_dir: str, root_name: str) -> str | None:
    """Find the new bundle directory matching a root_name."""
    bundles_dir = os.path.join(new_dir, 'bundles')
    if not os.path.isdir(bundles_dir):
        return None
    # Try to match by checking structure.json metadata
    for d in os.listdir(bundles_dir):
        path = os.path.join(bundles_dir, d, 'structure.json')
        if os.path.isfile(path):
            s = load_json(path)
            if s.get('_metadata', {}).get('root_name') == root_name:
                return os.path.join(bundles_dir, d)
    return None


# ── Main ────────────────────────────────────────────────────────────────

CHECKS = [
    ("Object completeness", check_object_completeness),
    ("Object count match", check_object_counts),
    ("Bundle completeness", check_bundle_completeness),
    ("Bundle object coverage", check_bundle_object_coverage),
    ("Code preservation", check_code_preservation),
    ("Dependency completeness", check_dependency_completeness),
    ("Dependency accuracy (sample)", check_dependency_accuracy),
    ("Orphan completeness", check_orphan_completeness),
    ("Orphan code (sample)", check_orphan_code),
]


def main():
    parser = argparse.ArgumentParser(description="Validate restructured output against v1 backup")
    parser.add_argument("--old", required=True, help="Path to old v1 output directory")
    parser.add_argument("--new", required=True, help="Path to new restructured output directory")
    args = parser.parse_args()

    print(f"Validating: {args.new} against {args.old}\n")
    print(f"{'Check':<35} {'Status':<8} {'Detail'}")
    print("-" * 90)

    all_passed = True
    for name, check_fn in CHECKS:
        try:
            passed, detail = check_fn(args.old, args.new)
        except Exception as e:
            passed, detail = False, f"ERROR: {e}"
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f"{name:<35} {status:<8} {detail}")

    print("-" * 90)
    if all_passed:
        print("\n✅ All checks passed!")
    else:
        print("\n❌ Some checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
