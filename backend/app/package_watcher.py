"""Watches a local folder for Appian ZIP packages and auto-parses them.

Drop a ZIP into backend/packages/ and the next server start (or manual
trigger) will parse it automatically. No upload endpoint needed — just
drag and drop into the folder.

Also exposes a route to trigger a re-scan manually without restarting.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PACKAGES_DIR = Path(__file__).parent.parent / "packages"


def check_for_new_packages():
    """Scan packages/ folder and parse any ZIP files found.

    Compares against what's already loaded in context_store. If the newest
    ZIP is different from what was last parsed, it re-parses.
    """
    if not PACKAGES_DIR.exists():
        PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created packages/ folder at {PACKAGES_DIR} — drop ZIPs here for auto-parse.")
        return

    zips = sorted(PACKAGES_DIR.glob("*.zip"), key=os.path.getmtime, reverse=True)
    if not zips:
        logger.info("No ZIP files in packages/ folder.")
        return

    newest_zip = zips[0]

    # Check if we already parsed this file
    from app.context_store import get_meta
    meta = get_meta()
    if meta and meta.get("source_filename") == newest_zip.name:
        logger.info(f"Context already loaded from {newest_zip.name} — skipping re-parse.")
        return

    logger.info(f"Found new package: {newest_zip.name} — parsing...")
    _parse_zip(str(newest_zip))


def _parse_zip(zip_path: str):
    """Run the full parse pipeline on a ZIP file and save context."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "solutions-atlas-parser-main"))

        from appian_parser.package_reader import PackageReader
        from appian_parser.type_detector import TypeDetector
        from appian_parser.parser_registry import ParserRegistry
        from appian_parser.domain.models import ParsedObject
        from appian_parser.diff_hash import DiffHashService
        from appian_parser.resolution.reference_resolver import ReferenceResolver
        from appian_parser.resolution.label_bundle_resolver import LabelBundleResolver
        from appian_parser.dependencies.analyzer import DependencyAnalyzer
        from app.context_store import save_parsed_context

        reader = PackageReader()
        detector = TypeDetector()
        registry = ParserRegistry()
        contents = reader.read(zip_path)

        try:
            # Parse
            parsed_objects = []
            for xml_file in contents.xml_files:
                try:
                    detection = detector.detect(xml_file)
                    if detection.is_excluded or detection.is_unknown:
                        continue
                    parser = registry.get_parser(detection.mapped_type)
                    data = parser.parse(xml_file)
                    if not data or not data.get("uuid"):
                        continue
                    parsed_objects.append(ParsedObject(
                        uuid=data["uuid"],
                        name=data.get("name", "Unknown"),
                        object_type=detection.mapped_type,
                        data=data,
                        diff_hash=DiffHashService.generate_hash(data),
                        source_file=os.path.basename(xml_file),
                    ))
                except Exception:
                    pass  # Skip individual file errors

            # Resolve references
            label_lookup = LabelBundleResolver.build_lookup(contents.properties_files)
            resolver = ReferenceResolver(parsed_objects, label_lookup=label_lookup)
            resolver.resolve_all(parsed_objects, locale="en-US")

            # Dependencies
            analyzer = DependencyAnalyzer()
            dependencies = analyzer.analyze(parsed_objects)

            # Save
            save_parsed_context(
                parsed_objects=parsed_objects,
                dependencies=dependencies,
                source_filename=os.path.basename(zip_path),
            )

            logger.info(f"Auto-parsed {os.path.basename(zip_path)}: {len(parsed_objects)} objects, {len(dependencies)} deps")

        finally:
            reader.cleanup(contents.temp_dir)

    except Exception as e:
        logger.error(f"Auto-parse failed for {zip_path}: {e}")


# ─── FastAPI route ────────────────────────────────────────────

try:
    from fastapi import APIRouter
    router = APIRouter(prefix="/api/v1/parser")

    @router.post("/reload")
    async def reload_from_folder():
        """Manually trigger a re-scan of the packages/ folder."""
        check_for_new_packages()
        from app.context_store import get_meta
        meta = get_meta()
        if meta:
            return {"success": True, "message": f"Context loaded: {meta['total_objects']} objects from {meta['source_filename']}"}
        return {"success": False, "message": "No ZIP found in packages/ folder"}

except ImportError:
    router = None  # fastapi not available (e.g. in test scripts)
