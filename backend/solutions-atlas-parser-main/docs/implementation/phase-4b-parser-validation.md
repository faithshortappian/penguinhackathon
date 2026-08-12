# Phase 4B — Parser Validation with Real Data

**Goal**: Exhaustively validate the v3 parser output against real Appian packages before touching the MCP server. This phase catches data quality issues, missing information, schema violations, and format mismatches that unit tests cannot detect. Nothing proceeds to Phase 5 until every check passes.

**Prerequisite**: Phase 4 complete (full pipeline working — legacy, versioned baseline, versioned new release, delta parse).

**Test data**: `test_files/source_selection_v1/`
- `SourceSelectionv2.7.0 - FULL.zip` — 2,649 files, baseline
- `SourceSelectionv2.8.0 - FULL.zip` — 2,653 files, second release
- `SourceSelection-2.9.0-21 - Delta Package Compared with 2.8.0.zip` — 158 files, delta

---

## 4B.1 Test Harness

**New file**: `tests/validation/run_validation.py`

**Purpose**: Orchestrates the full validation suite. Parses all three packages in sequence, then runs every validation check. Produces a pass/fail report.

```python
"""
Full validation suite for v3 parser output.

Usage:
    python -m tests.validation.run_validation

Runs:
    1. Parse v2.7.0 as baseline (versioned mode)
    2. Parse v2.8.0 as new release (versioned full parse)
    3. Parse v2.9.0 as delta (versioned delta parse)
    4. Also parse v2.8.0 in legacy mode (flat output)
    5. Run all validation checks
    6. Print pass/fail report
"""

import sys
import os
import time

TEST_FILES = "test_files/source_selection_v1"
VERSIONED_DIR = "test_output/versioned/GSS"
LEGACY_DIR = "test_output/legacy"

def main():
    results = []

    # Step 1-4: Parse
    print("=== Parsing packages ===")
    t0 = time.time()
    _parse_baseline()
    _parse_new_release()
    _parse_delta()
    _parse_legacy()
    print(f"Parsing complete in {time.time() - t0:.1f}s\n")

    # Step 5: Validate
    print("=== Running validation checks ===\n")

    # Schema validation
    results += run_schema_checks()

    # Data completeness
    results += run_completeness_checks()

    # Data accuracy
    results += run_accuracy_checks()

    # Versioning checks
    results += run_versioning_checks()

    # Delta checks
    results += run_delta_checks()

    # Legacy mode checks
    results += run_legacy_checks()

    # Cross-file consistency
    results += run_consistency_checks()

    # Performance checks
    results += run_performance_checks()

    # Step 6: Report
    print("\n=== VALIDATION REPORT ===\n")
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}")
        if not r.passed:
            print(f"         {r.message}")

    print(f"\n{passed} passed, {failed} failed, {len(results)} total")
    sys.exit(0 if failed == 0 else 1)
```

---

## 4B.2 Schema Validation

**New file**: `tests/validation/check_schemas.py`

**Purpose**: Verify every output file conforms to the Spec 02 schemas. No missing required fields, no unexpected types.

### Check: `object_file_schema`
For every `objects/<uuid>.json`:
- Has required fields: `uuid`, `name`, `type`, `description`, `diff_hash`
- Has `bundles` (list of strings)
- Has `is_hub` (bool), `is_orphan` (bool)
- Has `inbound_count` (int), `outbound_count` (int)
- Has `calls` (list of `{uuid, name, type, dep_type}`)
- Has `called_by` (list of `{uuid, name, type, dep_type}`)
- Has `type_specific` (dict)
- `uuid` in filename matches `uuid` in content
- `diff_hash` is a non-empty hex string
- `description` is a string (can be empty)

### Check: `object_type_specific_fields`
For each object type, verify `type_specific` contains the expected fields:
- Expression Rule → has `inputs` (list), `output_type` (string)
- Interface → has `parameters` (list)
- Process Model → has `variables` (list), `total_nodes` (int), `complexity_score`
- Record Type → has `fields` (list), `relationships` (list)
- CDT → has `namespace` (string), `fields` (list)
- Integration → has `connected_system`, `http_method`, `url`
- Web API → has `http_method`, `url_alias`
- Site → has `pages` (list)
- Constant → has `value`, `value_type`
- Connected System → has `base_url`, `auth_type`
- Group → has `group_type`

### Check: `code_file_schema`
For every `code/<uuid>.json`:
- Has required fields: `uuid`, `name`, `type`, `sail_code`
- `sail_code` is a non-empty string
- `uuid` in filename matches `uuid` in content
- No code file exists for Constants, Groups, Translation Sets, CDTs

### Check: `bundle_file_schema`
For every `bundles/<Name>.json`:
- Has `_metadata` with: `bundle_id`, `bundle_type`, `root_name`, `object_count`
- `bundle_type` is one of: `action`, `process`, `page`, `site`, `dashboard`, `web_api`
- Has `entry_point` (dict, non-empty)
- Has `members` (list of `{uuid, name, type}`)
- Has `key_objects` (list of strings, max 5)
- `_metadata.object_count` matches `len(members)`
- Every member has all three fields (uuid, name, type)

### Check: `graph_schema`
For `graph.json`:
- Has `_metadata` with: `schema_version`, `node_count`, `edge_count`, `hub_threshold`
- Has `nodes` (list), `edges` (list)
- `_metadata.node_count` matches `len(nodes)`
- `_metadata.edge_count` matches `len(edges)`
- Every node has: `id`, `name`, `type`, `bundles`, `inbound_count`, `outbound_count`, `is_hub`, `is_orphan`
- Every edge has: `from`, `to`, `type`
- No node has `description` field (excluded by design)

### Check: `manifest_schema`
For `manifest.json`:
- Has `_metadata` with: `version`, `total_objects`, `generated_at`
- Has `objects` (dict)
- `_metadata.total_objects` matches `len(objects)`
- Every entry has: `name`, `type`, `diff_hash`, `last_changed_in`

### Check: `search_index_schema`
For `search_index.json`:
- Every entry has: `uuid`, `type`, `description`, `bundle_count`, `bundles`, `deps_out`, `deps_in`
- `bundle_count` matches `len(bundles)`

### Check: `orphan_index_schema`
For `orphans_index.json`:
- Has `_metadata.total_orphans` (int)
- Has `by_type` (dict of string → int)
- Has `orphans` (list of `{uuid, name, type}`)
- `_metadata.total_orphans` matches `len(orphans)`
- Sum of `by_type` values matches `total_orphans`

### Check: `release_index_schema`
For `release_index.json`:
- Has `_metadata` with: `application`, `total_releases`, `latest_release`
- Has `releases` (list)
- First release has `is_baseline: true`
- Non-baseline releases have `change_summary` with: `objects_added`, `objects_modified`, `objects_removed`, `objects_unchanged`
- Releases are ordered by `sort_key`

### Check: `changelog_schema`
For each `changelogs/<version>.json`:
- Has `_metadata` with: `from_release`, `to_release`, `generated_at`
- Has `summary` with all count fields
- Has `object_changes` (list) — each entry has: `uuid`, `name`, `type`, `status`, `old_hash`, `new_hash`, `affected_bundles`
- `status` is one of: `added`, `modified`, `removed`
- Has `bundle_changes` (list) — each entry has: `bundle_id`, `status`, `members_added`, `members_removed`

### Check: `version_history_schema`
For every `objects/<uuid>.json` in versioned mode:
- Has `version_history` (list)
- First entry has `status: "current"`
- First entry's `diff_hash` matches top-level `diff_hash`
- All entries have: `version`, `status`, `diff_hash`
- `status` is one of: `current`, `modified`, `added`
- Entries are ordered newest-first

### Check: `history_file_schema`
For every `history/<uuid>/<version>.json`:
- Has: `uuid`, `name`, `type`, `description`, `diff_hash`
- Has: `bundles`, `calls`, `called_by`
- Has: `sail_code` (string, can be null for non-code objects)
- Has: `type_specific` (dict)

---

## 4B.3 Data Completeness

**New file**: `tests/validation/check_completeness.py`

**Purpose**: Verify no data is lost in the v3 output compared to what the parser extracted.

### Check: `all_parsed_objects_have_files`
- Count of `objects/<uuid>.json` files matches total parsed objects in `app_overview.json`
- Every UUID in `manifest.json` has a corresponding `objects/<uuid>.json`

### Check: `all_code_objects_have_code_files`
- Every Expression Rule, Interface, Web API, and Process Model has a `code/<uuid>.json`
- No Constant, Group, Translation Set, or CDT has a code file

### Check: `all_objects_in_search_index`
- Every object name in `objects/` appears in `search_index.json`
- No extra entries in search index that don't have object files

### Check: `all_objects_in_graph`
- Every UUID in `manifest.json` appears as a node in `graph.json`
- No extra nodes in graph that aren't in manifest

### Check: `bundle_members_exist`
- For every bundle, every UUID in `members` has a corresponding `objects/<uuid>.json`
- No dangling UUID references

### Check: `orphan_completeness`
- Every object flagged `is_orphan: true` in its object file appears in `orphans_index.json`
- Every UUID in `orphans_index.json` has `is_orphan: true` in its object file
- No object is both in a bundle AND flagged as orphan

### Check: `description_populated`
- At least 80% of Expression Rules have non-empty `description`
- At least 80% of Interfaces have non-empty `description`
- At least 50% of Process Models have non-empty `description`
- Log objects with missing descriptions for review

### Check: `type_specific_populated`
- Every Expression Rule has `inputs` in `type_specific` (can be empty list)
- Every Interface has `parameters` in `type_specific`
- Every Record Type has `fields` in `type_specific` (non-empty)
- Every CDT has `fields` in `type_specific` (non-empty)
- Every Constant has `value` in `type_specific`

### Check: `sail_code_not_empty`
- Every `code/<uuid>.json` has non-empty `sail_code`
- No code file has `sail_code` that is just whitespace

### Check: `dependencies_populated`
- At least 70% of Expression Rules have non-empty `calls`
- At least 90% of Process Models have non-empty `calls`
- At least 50% of Interfaces have non-empty `calls`
- Total edge count in graph matches total dependencies in `app_overview.json`

---

## 4B.4 Data Accuracy

**New file**: `tests/validation/check_accuracy.py`

**Purpose**: Verify the data is correct, not just present.

### Check: `uuid_references_resolved`
- Sample 50 random `code/<uuid>.json` files
- Count occurrences of raw UUID patterns (`#"_a-..."`  or `_a-0000...`) in `sail_code`
- Expect < 2% unresolved UUIDs (same threshold as current parser: 99.97% resolution)
- Log any unresolved UUIDs for review

### Check: `record_type_urns_resolved`
- Sample 50 random code files
- Count occurrences of `urn:appian:record-field:v1:` in `sail_code`
- Expect < 5% unresolved (current: 98.1% resolution)

### Check: `dependency_symmetry`
- For every object A that lists B in `calls`, verify B lists A in `called_by`
- For every object A that lists B in `called_by`, verify B lists A in `calls`
- Report any asymmetries

### Check: `graph_edge_consistency`
- Every edge `{from, to}` in `graph.json` corresponds to a `calls` entry in `objects/<from>.json`
- Every `calls` entry in an object file corresponds to an edge in the graph
- Edge types match between graph and object files

### Check: `bundle_membership_consistency`
- For every object, `bundles` field in `objects/<uuid>.json` matches the set of bundles that list this UUID in their `members`
- No object claims bundle membership that the bundle doesn't confirm

### Check: `hub_classification_correct`
- Every object with `is_hub: true` has `inbound_count >= hub_threshold` (from graph metadata)
- No object with `is_hub: false` has `inbound_count >= hub_threshold`

### Check: `orphan_classification_correct`
- Every object with `is_orphan: true` has empty `bundles` list
- Every object with `is_orphan: false` has non-empty `bundles` list

### Check: `inbound_outbound_counts_match`
- For every object, `inbound_count` matches `len(called_by)`
- For every object, `outbound_count` matches `len(calls)`
- For every graph node, `inbound_count` matches count of edges pointing to it
- For every graph node, `outbound_count` matches count of edges from it

### Check: `diff_hash_consistency`
- For every object, `diff_hash` in `objects/<uuid>.json` matches `diff_hash` in `manifest.json`
- For every object, `diff_hash` in `version_history[0]` (current) matches top-level `diff_hash`

---

## 4B.5 Versioning Validation

**New file**: `tests/validation/check_versioning.py`

**Purpose**: Validate the multi-release pipeline using all three test packages.

### Check: `release_count`
After parsing all three packages:
- `release_index.json` has exactly 3 releases
- Releases are in correct order: v2.7.0 < v2.8.0 < v2.9.0
- First release is baseline (`is_baseline: true`)

### Check: `version_detection`
- v2.7.0 parse detects correct version from the version constant
- v2.8.0 parse detects a different (newer) version
- v2.9.0 delta detects a different (newest) version

### Check: `changelog_exists`
- `changelogs/` has exactly 2 files (one for v2.8.0, one for v2.9.0)
- No changelog for baseline (v2.7.0)

### Check: `changelog_content`
For the v2.8.0 changelog:
- `from_release` is v2.7.0, `to_release` is v2.8.0
- `objects_added` + `objects_modified` + `objects_unchanged` = total objects in v2.7.0 manifest (for non-removed)
- `object_changes` list is non-empty
- Every entry has valid `status` and `affected_bundles`
- Version constant is NOT in `object_changes`

### Check: `changelog_bundle_changes`
For each changelog:
- `bundle_changes` is present
- Modified bundles have `members_added` and `members_removed` arrays
- Added bundles have empty `members_removed`

### Check: `release_snapshots_exist`
- `release_snapshots/` has directories for v2.7.0 and v2.8.0 (not v2.9.0 — that's current)
- Each snapshot has `manifest.json` and `app_overview.json`
- Snapshot manifest object count matches the release's `total_objects`

### Check: `history_files_exist`
- `history/` directory is non-empty
- History files exist for objects that changed between v2.7.0 → v2.8.0
- History file content matches the Spec 04 schema (has sail_code, type_specific, deps)

### Check: `version_history_in_objects`
- Objects that changed in v2.8.0 have `version_history` with 2+ entries
- Objects that changed in v2.9.0 have `version_history` with 2+ or 3 entries
- Objects unchanged since v2.7.0 have `version_history` with 1 entry (status: "current")
- No object has duplicate version entries

### Check: `manifest_last_changed_in`
- Objects unchanged since v2.7.0 have `last_changed_in: "v2.7.0"` (or whatever the actual version string is)
- Objects changed in v2.8.0 have `last_changed_in` pointing to v2.8.0
- Objects changed in v2.9.0 have `last_changed_in` pointing to v2.9.0

### Check: `object_count_progression`
- v2.7.0 total objects ≤ v2.8.0 total objects ≤ v2.9.0 total objects (assuming no removals)
- The difference matches `objects_added` in the changelog

---

## 4B.6 Delta-Specific Validation

**New file**: `tests/validation/check_delta.py`

**Purpose**: Validate delta parse produces correct results.

### Check: `delta_merge_correctness`
- After delta parse of v2.9.0, total objects in manifest ≥ total objects in v2.8.0 manifest
- Objects NOT in the delta ZIP are unchanged (same `diff_hash` as v2.8.0)
- Objects IN the delta ZIP have updated `diff_hash`

### Check: `delta_smart_write_stats`
- Delta parse reports files_written << total objects (expect ~20-50 files written, not ~2500)
- files_skipped >> files_written

### Check: `delta_no_data_loss`
- After delta parse, every object from v2.8.0 that wasn't in the delta still exists in `current/`
- Their content is identical (byte-for-byte) to pre-delta state

### Check: `delta_resolution_correct`
- Sample 10 objects from the delta that reference existing objects
- Verify UUIDs in their `sail_code` are resolved to names (not raw UUIDs)
- Sample 10 existing objects that reference delta objects
- Verify those references are also resolved

### Check: `delta_bundles_updated`
- Bundles containing delta objects have updated `members` lists
- Bundles NOT containing any delta objects are unchanged (smart write skipped them)

---

## 4B.7 Legacy Mode Validation

**New file**: `tests/validation/check_legacy.py`

**Purpose**: Verify legacy mode output is correct and doesn't include versioning artifacts.

### Check: `legacy_no_versioning`
- No `manifest.json` in output
- No `parsed_state.json` in output
- No `release_index.json` in output
- No `history/`, `changelogs/`, `release_snapshots/` directories

### Check: `legacy_no_version_history`
- No `objects/<uuid>.json` file contains `version_history` field

### Check: `legacy_has_new_format`
- `graph.json` exists
- `orphans_index.json` exists (not `orphans/` directory with individual files)
- `bundles/<Name>.json` are single files (not directories with structure.json + code.json)
- `code/` directory exists with per-object code files
- `objects/<uuid>.json` files have `type_specific` field

### Check: `legacy_schema_matches_versioned`
- Object file schema (minus `version_history`) is identical between legacy and versioned output
- Code file schema is identical
- Bundle file schema is identical
- Graph schema is identical

---

## 4B.8 Cross-File Consistency

**New file**: `tests/validation/check_consistency.py`

**Purpose**: Verify all files reference each other correctly.

### Check: `manifest_to_objects`
- Every UUID in `manifest.json` has `objects/<uuid>.json`
- Every `objects/<uuid>.json` has its UUID in `manifest.json`
- Names match between manifest and object files

### Check: `search_index_to_objects`
- Every name in `search_index.json` has a corresponding object file (via UUID)
- `deps_in` and `deps_out` in search index match `inbound_count` and `outbound_count` in object file

### Check: `graph_to_objects`
- Every graph node UUID has an object file
- Every object file UUID has a graph node
- `is_hub` and `is_orphan` flags match between graph nodes and object files

### Check: `bundles_to_objects`
- Every UUID in every bundle's `members` has an object file
- Every object file's `bundles` list matches the bundles that contain it

### Check: `app_overview_accuracy`
- `total_parsed_objects` matches count of object files
- `object_counts` by type matches actual type distribution in object files
- `coverage.bundled` + `coverage.orphaned` = `total_parsed_objects`
- Bundle count in overview matches count of bundle files

---

## 4B.9 Performance Validation

**New file**: `tests/validation/check_performance.py`

**Purpose**: Verify the parser meets the Spec 01 success criteria.

### Check: `full_parse_under_3_seconds`
- Time the full parse of v2.8.0 (2,653 files)
- Must complete in under 3 seconds

### Check: `delta_parse_under_3_seconds`
- Time the delta parse of v2.9.0 (158 files)
- Must complete in under 3 seconds

### Check: `delta_git_footprint`
- Count files written during delta parse
- Must be < 100 files (spec says < 30 for 3 objects, but delta has 158 files)

### Check: `file_sizes_reasonable`
- No single `objects/<uuid>.json` exceeds 100KB
- No single `code/<uuid>.json` exceeds 500KB
- No single `bundles/<Name>.json` exceeds 200KB
- `graph.json` is under 10MB
- `search_index.json` is under 5MB
- `manifest.json` is under 2MB

---

## 4B.10 Regression Check Against Current Output

**New file**: `tests/validation/check_regression.py`

**Purpose**: Compare v3 output against the current KB output in `gam-knowledge-base/data/SourceSelection/` to ensure no information is lost.

### Check: `object_count_matches`
- v3 total objects ≈ current KB total objects (within 5% — minor differences from parser improvements are acceptable)

### Check: `bundle_count_matches`
- v3 bundle count ≈ current KB bundle count

### Check: `dependency_count_matches`
- v3 total edges in graph ≈ current KB total dependencies in app_overview

### Check: `sample_object_data_preserved`
- Pick 20 random objects from current KB `objects/<uuid>.json`
- For each, verify the v3 `objects/<uuid>.json` has:
  - Same `name`
  - Same `type`
  - Same or more `calls` entries
  - Same or more `called_by` entries
  - `description` present (may be new — current KB doesn't always have it)

### Check: `sample_code_preserved`
- Pick 20 random objects that have code in current KB bundles
- Verify their `code/<uuid>.json` in v3 has non-empty `sail_code`
- Verify the code contains resolved names (rule!, cons!, type!) not raw UUIDs

### Check: `bundle_membership_preserved`
- Pick 10 random bundles from current KB
- Verify the v3 bundle has the same or similar member count
- Verify key objects are still present

---

## Running the Validation

```bash
# Full validation suite
python -m tests.validation.run_validation

# Individual check modules
python -m tests.validation.check_schemas
python -m tests.validation.check_completeness
python -m tests.validation.check_accuracy
python -m tests.validation.check_versioning
python -m tests.validation.check_delta
python -m tests.validation.check_legacy
python -m tests.validation.check_consistency
python -m tests.validation.check_performance
python -m tests.validation.check_regression
```

---

## Phase 4B Deliverables

| Artifact | Type | Description |
|----------|------|-------------|
| `run_validation.py` | Test harness | Orchestrates full validation suite |
| `check_schemas.py` | Validation | 11 schema checks across all file types |
| `check_completeness.py` | Validation | 10 data completeness checks |
| `check_accuracy.py` | Validation | 10 data accuracy checks |
| `check_versioning.py` | Validation | 10 versioning pipeline checks |
| `check_delta.py` | Validation | 5 delta-specific checks |
| `check_legacy.py` | Validation | 4 legacy mode checks |
| `check_consistency.py` | Validation | 4 cross-file consistency checks |
| `check_performance.py` | Validation | 4 performance checks |
| `check_regression.py` | Validation | 5 regression checks against current KB |

**Total**: ~63 individual validation checks

## Phase 4B Exit Criteria

**ALL of the following must pass before proceeding to Phase 5:**

1. All 63 validation checks pass (0 failures)
2. Full parse of v2.8.0 completes in < 3 seconds
3. Delta parse of v2.9.0 produces < 100 changed files
4. UUID resolution rate ≥ 99.9%
5. Record Type URN resolution rate ≥ 95%
6. Zero schema violations across all output files
7. Zero cross-file reference inconsistencies
8. Legacy mode produces correct v3 format without versioning artifacts
9. Regression check confirms no data loss vs current KB output
10. Version history correctly tracks changes across all 3 releases
