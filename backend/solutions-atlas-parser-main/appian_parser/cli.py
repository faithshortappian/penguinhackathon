"""CLI for appian-parser."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from appian_parser.package_reader import PackageReader
from appian_parser.type_detector import TypeDetector
from appian_parser.parser_registry import ParserRegistry
from appian_parser.diff_hash import DiffHashService
from appian_parser.domain.models import (
    BuildArtifacts, ParsedObject, ParseError, DumpOptions, DumpResult,
)
from appian_parser.resolution.reference_resolver import ReferenceResolver
from appian_parser.resolution.label_bundle_resolver import LabelBundleResolver
from appian_parser.dependencies.analyzer import DependencyAnalyzer
from appian_parser.output.bundle_coordinator import BundleCoordinator
from appian_parser.output.search_index_builder import SearchIndexBuilder
from appian_parser.output.app_overview_builder import AppOverviewBuilder
from appian_parser.output.object_file_builder import ObjectFileBuilder
from appian_parser.output.code_file_builder import CodeFileBuilder
from appian_parser.output.graph_builder import GraphBuilder
from appian_parser.output.orphan_index_builder import OrphanIndexBuilder
from appian_parser.output.legacy_writer import LegacyWriter
from appian_parser.output.versioned_writer import VersionedWriter
from appian_parser.output.document_writer import DocumentWriter
from appian_parser.output.v3_manifest_builder import V3ManifestBuilder
from appian_parser.versioning.config import AppConfig, VersionDetector, ReleaseIndexBuilder
from appian_parser.versioning.parsed_state import ParsedStateStore
from appian_parser.versioning.delta import DeltaMerger, ModeDetector, ParseMode
from appian_parser.versioning.history import HistoryArchiver, SnapshotWriter, ChangelogBuilder, RetentionPruner
from appian_parser.enrichment import Enricher
from appian_parser.output.enrichment_writer import EnrichmentWriter


def _build_dependency_summary(dependencies: list) -> dict:
    """Build dependency summary stats from raw dependency list."""
    by_type: dict[str, int] = {}
    inbound: dict[str, int] = {}
    outbound: dict[str, int] = {}
    target_info: dict[str, dict] = {}
    source_info: dict[str, dict] = {}

    for d in dependencies:
        by_type[d.dependency_type] = by_type.get(d.dependency_type, 0) + 1
        inbound[d.target_uuid] = inbound.get(d.target_uuid, 0) + 1
        outbound[d.source_uuid] = outbound.get(d.source_uuid, 0) + 1
        target_info[d.target_uuid] = {'name': d.target_name, 'type': d.target_type}
        source_info[d.source_uuid] = {'name': d.source_name, 'type': d.source_type}

    most_depended = sorted(inbound.items(), key=lambda x: -x[1])[:20]
    most_deps = sorted(outbound.items(), key=lambda x: -x[1])[:20]

    return {
        'total': len(dependencies),
        'by_type': dict(sorted(by_type.items())),
        'most_depended_on': [
            {**target_info[uuid], 'inbound_count': count} for uuid, count in most_depended
        ],
        'most_dependencies': [
            {**source_info[uuid], 'outbound_count': count} for uuid, count in most_deps
        ],
    }


def dump_package(zip_path: str, output_dir: str, options: DumpOptions) -> DumpResult:
    """Main orchestration: ZIP -> parsed objects -> JSON output."""
    start_time = time.time()

    reader = PackageReader()
    detector = TypeDetector(excluded_types=options.excluded_types or None)
    registry = ParserRegistry()

    contents = reader.read(zip_path)

    try:
        # === PHASE 1: ACQUIRE ===
        parsed_objects, errors = _parse_all(contents, detector, registry)

        # === PHASE 2: TRANSFORM ===
        label_lookup = LabelBundleResolver.build_lookup(contents.properties_files)
        resolver = ReferenceResolver(parsed_objects, label_lookup=label_lookup)
        resolver.resolve_all(parsed_objects, locale=options.locale)

        dependencies = []
        if options.include_dependencies:
            analyzer = DependencyAnalyzer()
            dependencies = analyzer.analyze(parsed_objects)

        duration = time.time() - start_time

        # Package info
        by_type: dict[str, int] = {}
        for obj in parsed_objects:
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
        package_info = {
            'filename': contents.zip_filename,
            'total_files_in_zip': contents.total_files,
            'total_xml_files': len(contents.xml_files),
            'total_parsed_objects': len(parsed_objects),
            'total_errors': len(errors),
            'parse_duration_seconds': round(duration, 2),
        }
        object_counts = dict(sorted(by_type.items()))

        # Version detection (versioned mode only)
        version_info = None
        now_iso = datetime.now(timezone.utc).isoformat()
        if options.data_dir:
            app_config = AppConfig.load(os.path.join(options.data_dir, 'app_config.json'))
            if options.release_override:
                version_info = VersionDetector.parse_version(options.release_override)
            else:
                version_info = VersionDetector().detect(parsed_objects, app_config.version_constant)

        # === PHASE 3: BUILD ===
        artifacts = _build_artifacts(
            parsed_objects, dependencies, package_info, object_counts, options,
            version=version_info.raw if version_info else None,
        )

        # === PHASE 4: WRITE ===
        if options.data_dir and version_info:
            manifest_path = os.path.join(options.data_dir, 'current', 'manifest.json')
            old_manifest = None
            if os.path.isfile(manifest_path):
                with open(manifest_path) as f:
                    old_manifest = json.load(f)

            manifest = V3ManifestBuilder.build(parsed_objects, version_info.raw, now_iso,
                                               previous_manifest=old_manifest)
            parsed_state = ParsedStateStore.build(parsed_objects, version_info.raw, now_iso)
            writer = VersionedWriter(options.data_dir, pretty=options.pretty)

            if old_manifest is None:
                # First parse — baseline
                release_index = ReleaseIndexBuilder.build_baseline(
                    app_name=app_config.application_name,
                    version_info=version_info,
                    parsed_at=now_iso,
                    source_package=contents.zip_filename,
                    total_objects=len(parsed_objects),
                    total_bundles=len(artifacts.bundle_dicts),
                )
                writer.write_baseline(artifacts, manifest, parsed_state, release_index)
            else:
                # Subsequent full parse — new release flow
                old_version = old_manifest['_metadata']['version']

                old_objects = []
                state_path = os.path.join(options.data_dir, 'current', 'parsed_state.json')
                if os.path.isfile(state_path):
                    old_objects, _ = ParsedStateStore.load(state_path)

                SnapshotWriter().snapshot(options.data_dir, old_version)

                changed_uuids = {
                    uuid for uuid, entry in old_manifest.get('objects', {}).items()
                    if uuid in manifest.get('objects', {}) and
                    entry['diff_hash'] != manifest['objects'][uuid]['diff_hash']
                }
                removed_uuids = set(old_manifest.get('objects', {})) - set(manifest.get('objects', {}))
                if old_objects:
                    old_deps = DependencyAnalyzer().analyze(old_objects)
                    HistoryArchiver().archive(
                        options.data_dir, changed_uuids | removed_uuids, old_version,
                        old_objects, old_deps, artifacts.bundle_assignments, pretty=options.pretty,
                    )

                old_bundle_dicts = _load_bundle_dicts(os.path.join(options.data_dir, 'current', 'bundles'))

                changelog = ChangelogBuilder().build(
                    old_manifest, manifest, old_version, version_info.raw, now_iso,
                    artifacts.bundle_assignments, old_bundle_dicts, artifacts.bundle_dicts,
                    app_config.version_constant, is_full_parse=True,
                )

                release_index_path = os.path.join(options.data_dir, 'release_index.json')
                with open(release_index_path) as f:
                    release_index = json.load(f)

                if version_info.raw == old_version:
                    # Same version re-parse — update existing entry in place
                    for entry in release_index['releases']:
                        if entry['version'] == version_info.raw:
                            entry['parsed_at'] = now_iso
                            entry['source_package'] = contents.zip_filename
                            entry['total_objects'] = len(parsed_objects)
                            entry['total_bundles'] = len(artifacts.bundle_dicts)
                            break
                else:
                    # New release — append
                    ReleaseIndexBuilder.append_release(
                        release_index, version_info, now_iso, contents.zip_filename,
                        len(parsed_objects), len(artifacts.bundle_dicts),
                        changelog['summary'], old_version,
                    )

                writer.write_new_release(
                    artifacts, manifest, parsed_state, changelog, release_index,
                    version_info.raw, removed_uuids=removed_uuids,
                )

                RetentionPruner().prune_if_needed(
                    options.data_dir, release_index, app_config.max_retained_releases,
                )
                writer._writer.write_json(
                    os.path.join(options.data_dir, 'release_index.json'), release_index,
                )

            effective_output = options.data_dir
        else:
            writer = LegacyWriter()
            writer.write_all(output_dir, artifacts, errors, pretty=options.pretty)
            effective_output = output_dir

        # Enrichment (orthogonal to v3 refactor)
        if options.include_enrichment and dependencies:
            enricher = Enricher()
            enriched_data = enricher.enrich_all(parsed_objects, dependencies)
            if enriched_data:
                enrich_dir = effective_output if not options.data_dir else f"{options.data_dir}/current"
                EnrichmentWriter(enrich_dir, pretty=options.pretty).write_all(enriched_data)

        # Document extraction (binary images/icons)
        docs_output = effective_output if not options.data_dir else f"{options.data_dir}/current"
        DocumentWriter(pretty=options.pretty).write(
            contents.temp_dir, docs_output, parsed_objects,
        )

        # Schema extraction (DDL replay from scripts/ folder)
        from appian_parser.schema import SchemaBuilder
        from appian_parser.schema.record_type_mapper import (
            build_record_type_map, build_field_map, build_reference_data_metadata,
        )
        schema_builder = SchemaBuilder()
        schema_result = schema_builder.build(Path(contents.temp_dir))
        if schema_result:
            schema_output = os.path.join(
                docs_output if not options.data_dir else f"{options.data_dir}/current",
                "schema",
            )
            os.makedirs(schema_output, exist_ok=True)

            # Build record type map and field map by cross-referencing with parsed objects
            rt_map = build_record_type_map(parsed_objects, schema_result)
            f_map = build_field_map(parsed_objects, schema_result)
            ref_metadata = build_reference_data_metadata(schema_result, rt_map)

            schema_files = {
                "tables.json": schema_result.tables_as_dict(),
                "relationships.json": schema_result.relationships,
                "reference_data.json": ref_metadata,
                "insertion_order.json": schema_result.insertion_order,
                "table_classification.json": schema_result.table_classification,
                "summary.json": schema_result.summary,
                "record_type_map.json": rt_map,
                "field_map.json": f_map,
            }
            for filename, data in schema_files.items():
                with open(os.path.join(schema_output, filename), "w") as f:
                    json.dump(data, f, indent=2 if options.pretty else None)

        return DumpResult(
            total_files=len(contents.xml_files),
            objects_parsed=len(parsed_objects),
            errors_count=len(errors),
            output_dir=effective_output,
        )
    finally:
        reader.cleanup(contents.temp_dir)


def _parse_all(contents, detector, registry):
    """Parse all XML files into ParsedObjects."""
    parsed_objects: list[ParsedObject] = []
    errors: list[ParseError] = []

    for xml_file in contents.xml_files:
        detection = None
        try:
            detection = detector.detect(xml_file)
            if detection.is_excluded or detection.is_unknown:
                continue
            parser = registry.get_parser(detection.mapped_type)
            parsed_data = parser.parse(xml_file)
            if not parsed_data or not parsed_data.get('uuid'):
                continue
            diff_hash = DiffHashService.generate_hash(parsed_data)
            parsed_objects.append(ParsedObject(
                uuid=parsed_data['uuid'],
                name=parsed_data.get('name', 'Unknown'),
                object_type=detection.mapped_type,
                data=parsed_data,
                diff_hash=diff_hash,
                source_file=os.path.basename(xml_file),
            ))
        except Exception as e:
            errors.append(ParseError(
                file=os.path.basename(xml_file),
                error=str(e),
                object_type=detection.mapped_type if detection else 'Unknown',
            ))

    return parsed_objects, errors


def _build_artifacts(
    parsed_objects: list[ParsedObject],
    dependencies: list,
    package_info: dict,
    object_counts: dict,
    options: DumpOptions,
    *,
    version: str | None = None,
    previous_object_files: dict[str, dict] | None = None,
) -> BuildArtifacts:
    """Build all v3 output artifacts in memory."""
    # 1. Bundles
    bundle_assignments: dict[str, list[str]] = {}
    hub_uuids: set[str] = set()
    bundle_entries: list = []
    bundle_dicts: list[dict] = []

    if options.include_dependencies and dependencies:
        coordinator = BundleCoordinator(pretty=options.pretty)
        bundle_assignments, hub_uuids, bundle_entries, bundle_dicts = \
            coordinator.build_all_v3(parsed_objects, dependencies)

    bundled_uuids = set(bundle_assignments.keys())
    orphan_uuids = {obj.uuid for obj in parsed_objects if obj.uuid not in bundled_uuids}

    # 2. Object files
    object_files = ObjectFileBuilder().build_all(
        parsed_objects, dependencies, bundle_assignments, hub_uuids, orphan_uuids,
        version=version, previous_object_files=previous_object_files,
    )

    # 3. Code files
    code_files = CodeFileBuilder().build_all(parsed_objects)

    # 4. Graph
    graph = GraphBuilder().build(parsed_objects, dependencies, bundle_assignments, hub_uuids) \
        if dependencies else {'_metadata': {'node_count': 0, 'edge_count': 0}, 'nodes': [], 'edges': []}

    # 5. Search index
    search_index = SearchIndexBuilder().build(parsed_objects, dependencies, bundle_assignments)

    # 6. App overview
    dep_summary = _build_dependency_summary(dependencies) if dependencies else {
        'total': 0, 'by_type': {}, 'most_depended_on': [], 'most_dependencies': [],
    }
    coverage = {
        'total_objects': len(parsed_objects),
        'bundled': len(bundled_uuids),
        'orphaned': len(orphan_uuids),
    }
    app_overview = AppOverviewBuilder().build(
        package_info, object_counts, bundle_entries, dep_summary, coverage,
        parsed_objects=parsed_objects,
        dependencies=dependencies,
    )

    # 7. Orphan index
    orphan_index = OrphanIndexBuilder().build(parsed_objects, bundle_assignments)

    return BuildArtifacts(
        object_files=object_files,
        code_files=code_files,
        bundle_dicts=bundle_dicts,
        bundle_assignments=bundle_assignments,
        hub_uuids=hub_uuids,
        graph=graph,
        search_index=search_index,
        app_overview=app_overview,
        orphan_index=orphan_index,
    )


def delta_package(zip_path: str, options: DumpOptions) -> DumpResult:
    """Delta parse: merge delta ZIP into existing versioned state."""
    start_time = time.time()
    data_dir = options.data_dir
    now_iso = datetime.now(timezone.utc).isoformat()

    app_config = AppConfig.load(os.path.join(data_dir, 'app_config.json'))

    # Load existing state
    state_path = f"{data_dir}/current/parsed_state.json"
    if not os.path.exists(state_path):
        print("Warning: parsed_state.json not found. Falling back to full parse.")
        return dump_package(zip_path, '', options)

    existing_objects, existing_version = ParsedStateStore.load(state_path)

    # Load old manifest + old bundle dicts for changelog
    with open(f"{data_dir}/current/manifest.json") as f:
        old_manifest = json.load(f)

    old_bundle_dicts = _load_bundle_dicts(f"{data_dir}/current/bundles")

    # Parse delta ZIP
    reader = PackageReader()
    detector = TypeDetector(excluded_types=options.excluded_types or None)
    registry = ParserRegistry()
    contents = reader.read(zip_path)

    try:
        delta_objects, errors = _parse_all(contents, detector, registry)

        # Merge
        merge_result = DeltaMerger().merge(existing_objects, delta_objects)

        # Transform (full set)
        label_lookup = LabelBundleResolver.build_lookup(contents.properties_files)
        resolver = ReferenceResolver(merge_result.merged_objects, label_lookup=label_lookup)
        resolver.resolve_all(merge_result.merged_objects, locale=options.locale)
        dependencies = DependencyAnalyzer().analyze(merge_result.merged_objects)

        # Detect version
        if options.release_override:
            version_info = VersionDetector.parse_version(options.release_override)
        else:
            version_info = VersionDetector().detect(merge_result.merged_objects, app_config.version_constant)

        detected_version = version_info.raw if version_info else None
        mode = ModeDetector().detect(existing_version, detected_version)

        if not version_info:
            version_info = VersionDetector.parse_version(existing_version)

        duration = time.time() - start_time
        by_type: dict[str, int] = {}
        for obj in merge_result.merged_objects:
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
        package_info = {
            'filename': contents.zip_filename,
            'total_files_in_zip': contents.total_files,
            'total_xml_files': len(contents.xml_files),
            'total_parsed_objects': len(merge_result.merged_objects),
            'total_errors': len(errors),
            'parse_duration_seconds': round(duration, 2),
        }

        # Load previous object files for version_history
        prev_obj_files = _load_object_files(f"{data_dir}/current/objects")

        # Build
        artifacts = _build_artifacts(
            merge_result.merged_objects, dependencies, package_info,
            dict(sorted(by_type.items())), options,
            version=version_info.raw, previous_object_files=prev_obj_files,
        )

        # Write
        manifest = V3ManifestBuilder.build(
            merge_result.merged_objects, version_info.raw, now_iso, previous_manifest=old_manifest,
        )
        parsed_state = ParsedStateStore.build(merge_result.merged_objects, version_info.raw, now_iso)
        writer = VersionedWriter(data_dir, pretty=options.pretty)

        if mode == ParseMode.DAILY_UPDATE:
            writer.write_daily_update(artifacts, manifest, parsed_state)
        else:
            # New release: snapshot → archive → write → changelog → prune
            SnapshotWriter().snapshot(data_dir, existing_version)

            changed_uuids = merge_result.modified_uuids | merge_result.added_uuids
            # Re-analyze old deps for history archival
            old_deps = DependencyAnalyzer().analyze(existing_objects)
            old_ba = artifacts.bundle_assignments  # approximate
            HistoryArchiver().archive(
                data_dir, merge_result.modified_uuids, existing_version,
                existing_objects, old_deps, old_ba, pretty=options.pretty,
            )

            changelog = ChangelogBuilder().build(
                old_manifest, manifest, existing_version, version_info.raw, now_iso,
                artifacts.bundle_assignments, old_bundle_dicts, artifacts.bundle_dicts,
                app_config.version_constant, is_full_parse=False,
            )

            release_index_path = f"{data_dir}/release_index.json"
            with open(release_index_path) as f:
                release_index = json.load(f)
            ReleaseIndexBuilder.append_release(
                release_index, version_info, now_iso, contents.zip_filename,
                len(merge_result.merged_objects), len(artifacts.bundle_dicts),
                changelog['summary'], existing_version,
            )

            writer.write_new_release(
                artifacts, manifest, parsed_state, changelog, release_index, version_info.raw,
            )

            RetentionPruner().prune_if_needed(data_dir, release_index, app_config.max_retained_releases)
            # Re-save release index after pruning
            writer._writer.write_json(f"{data_dir}/release_index.json", release_index)

        # Document extraction (binary images/icons)
        DocumentWriter(pretty=options.pretty).write(
            contents.temp_dir, f"{data_dir}/current", merge_result.merged_objects,
        )

        # Schema extraction (DDL replay from scripts/ folder)
        from appian_parser.schema import SchemaBuilder
        from appian_parser.schema.record_type_mapper import (
            build_record_type_map, build_field_map, build_reference_data_metadata,
        )
        schema_builder = SchemaBuilder()
        schema_result = schema_builder.build(Path(contents.temp_dir))
        if schema_result:
            schema_output = os.path.join(f"{data_dir}/current", "schema")
            os.makedirs(schema_output, exist_ok=True)

            rt_map = build_record_type_map(merge_result.merged_objects, schema_result)
            f_map = build_field_map(merge_result.merged_objects, schema_result)
            ref_metadata = build_reference_data_metadata(schema_result, rt_map)

            schema_files = {
                "tables.json": schema_result.tables_as_dict(),
                "relationships.json": schema_result.relationships,
                "reference_data.json": ref_metadata,
                "insertion_order.json": schema_result.insertion_order,
                "table_classification.json": schema_result.table_classification,
                "summary.json": schema_result.summary,
                "record_type_map.json": rt_map,
                "field_map.json": f_map,
            }
            for filename, data in schema_files.items():
                with open(os.path.join(schema_output, filename), "w") as f:
                    json.dump(data, f, indent=2 if options.pretty else None)

        return DumpResult(
            total_files=len(contents.xml_files),
            objects_parsed=len(merge_result.merged_objects),
            errors_count=len(errors),
            output_dir=data_dir,
        )
    finally:
        reader.cleanup(contents.temp_dir)


def _load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_bundle_dicts(bundles_dir: str) -> list[dict]:
    if not os.path.isdir(bundles_dir):
        return []
    result = []
    for fname in os.listdir(bundles_dir):
        if fname.endswith('.json'):
            result.append(_load_json(os.path.join(bundles_dir, fname)))
    return result


def _load_object_files(objects_dir: str) -> dict[str, dict]:
    if not os.path.isdir(objects_dir):
        return {}
    result = {}
    for fname in os.listdir(objects_dir):
        if fname.endswith('.json'):
            uuid = fname[:-5]
            result[uuid] = _load_json(os.path.join(objects_dir, fname))
    return result


def main():
    parser = argparse.ArgumentParser(prog='appian-parser', description='Appian package parser')
    subparsers = parser.add_subparsers(dest='command')

    # dump command
    dump_parser = subparsers.add_parser('dump', help='Parse package and dump JSON')
    dump_parser.add_argument('package', help='Path to Appian package ZIP file')
    dump_parser.add_argument('output', nargs='?', default=None, help='Output directory (legacy mode)')
    dump_parser.add_argument('--data-dir', help='Versioned data store directory')
    dump_parser.add_argument('--release', help='Override version string')
    dump_parser.add_argument('--exclude-types', help='Comma-separated types to exclude')
    dump_parser.add_argument('--no-pretty', action='store_true', help='Disable pretty printing')
    dump_parser.add_argument('--locale', default='en-US', help='Locale for translation resolution (default: en-US)')
    dump_parser.add_argument('--no-deps', action='store_true', help='Skip dependency analysis')
    dump_parser.add_argument('--no-enrich', action='store_true', help='Skip data enrichment')

    # delta command
    delta_parser = subparsers.add_parser('delta', help='Delta parse into versioned data store')
    delta_parser.add_argument('package', help='Delta ZIP file')
    delta_parser.add_argument('--data-dir', required=True, help='Versioned data store directory')
    delta_parser.add_argument('--release', help='Override version string')
    delta_parser.add_argument('--locale', default='en-US')
    delta_parser.add_argument('--no-pretty', action='store_true')

    # types command
    subparsers.add_parser('types', help='List supported object types')

    args = parser.parse_args()

    if args.command == 'dump':
        if not os.path.isfile(args.package):
            print(f"Error: {args.package} not found", file=sys.stderr)
            sys.exit(1)

        if not args.output and not args.data_dir:
            print("Error: provide either output directory or --data-dir", file=sys.stderr)
            sys.exit(1)

        options = DumpOptions(
            pretty=not args.no_pretty,
            locale=args.locale,
            include_dependencies=not args.no_deps,
            include_enrichment=not args.no_enrich,
            data_dir=args.data_dir,
            release_override=args.release,
        )
        if args.exclude_types:
            options.excluded_types = set(args.exclude_types.split(','))

        print(f"Parsing {args.package}...")
        result = dump_package(args.package, args.output or '', options)
        print(f"Done! Parsed {result.objects_parsed} objects ({result.errors_count} errors)")
        print(f"Output: {result.output_dir}")

    elif args.command == 'delta':
        if not os.path.isfile(args.package):
            print(f"Error: {args.package} not found", file=sys.stderr)
            sys.exit(1)
        options = DumpOptions(
            pretty=not args.no_pretty, locale=args.locale,
            data_dir=args.data_dir, release_override=getattr(args, 'release', None),
        )
        print(f"Delta parsing {args.package}...")
        result = delta_package(args.package, options)
        print(f"Done! Parsed {result.objects_parsed} objects ({result.errors_count} errors)")
        print(f"Output: {result.output_dir}")

    elif args.command == 'types':
        registry = ParserRegistry()
        for t in sorted(registry.get_supported_types()):
            print(f"  {t}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
