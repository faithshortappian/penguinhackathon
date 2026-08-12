"""Routes for the Appian Solutions Parser.

Accepts Appian package ZIPs via file upload, runs the solutions-atlas-parser
in-memory, and returns structured JSON output (app overview, bundles,
dependencies, search index, etc.).
"""

import os
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/parser")


# ─── Response Models ─────────────────────────────────────────────

class ParseResponse(BaseModel):
    """Summary response from a parse operation."""
    total_files: int
    objects_parsed: int
    errors_count: int
    object_counts: dict[str, int] = {}
    bundle_count: int = 0


class ParseFullResponse(BaseModel):
    """Full parse result including all output data."""
    summary: ParseResponse
    app_overview: dict | None = None
    search_index: dict | None = None
    bundles: list[dict] = []
    graph: dict | None = None
    orphan_index: dict | None = None


# ─── Endpoints ───────────────────────────────────────────────────

@router.post("/parse", response_model=ParseFullResponse)
async def parse_package(
    file: UploadFile = File(..., description="Appian package ZIP file"),
    locale: str = Query("en-US", description="Locale for translation resolution"),
    include_dependencies: bool = Query(True, description="Include dependency analysis"),
):
    """
    Parse an Appian package ZIP and return structured JSON.

    Accepts the exported ZIP from Appian (which may contain nested ZIPs),
    runs the full parse pipeline (type detection -> parsing -> reference
    resolution -> dependency analysis -> bundle generation), and returns
    all outputs in a single response.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    temp_zip = None
    try:
        # Save upload to temp file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        content = await file.read()
        temp_zip.write(content)
        temp_zip.close()

        # Import parser components
        from appian_parser.package_reader import PackageReader
        from appian_parser.type_detector import TypeDetector
        from appian_parser.parser_registry import ParserRegistry
        from appian_parser.resolution.reference_resolver import ReferenceResolver
        from appian_parser.resolution.label_bundle_resolver import LabelBundleResolver

        reader = PackageReader()
        detector = TypeDetector()
        registry = ParserRegistry()

        contents = reader.read(temp_zip.name)

        try:
            # Phase 1: Parse all XML files
            parsed_objects, errors = _parse_all_objects(
                contents.xml_files, detector, registry
            )

            # Phase 2: Resolve references (UUID -> human-readable names)
            label_lookup = LabelBundleResolver.build_lookup(contents.properties_files)
            resolver = ReferenceResolver(parsed_objects, label_lookup=label_lookup)
            resolver.resolve_all(parsed_objects, locale=locale)

            # Phase 3: Dependency analysis + bundles (optional)
            dependencies = []
            bundle_dicts = []
            bundle_assignments: dict[str, list[str]] = {}
            hub_uuids: set[str] = set()
            graph = None

            if include_dependencies:
                from appian_parser.dependencies.analyzer import DependencyAnalyzer
                from appian_parser.output.bundle_coordinator import BundleCoordinator
                from appian_parser.output.graph_builder import GraphBuilder

                analyzer = DependencyAnalyzer()
                dependencies = analyzer.analyze(parsed_objects)

                coordinator = BundleCoordinator(pretty=False)
                bundle_assignments, hub_uuids, _, bundle_dicts = \
                    coordinator.build_all_v3(parsed_objects, dependencies)

                graph = GraphBuilder().build(
                    parsed_objects, dependencies, bundle_assignments, hub_uuids
                )

            # Build object counts
            by_type: dict[str, int] = {}
            for obj in parsed_objects:
                by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1

            # Build app overview
            app_overview = {
                "package_info": {
                    "filename": file.filename,
                    "total_files_in_zip": contents.total_files,
                    "total_xml_files": len(contents.xml_files),
                    "total_parsed_objects": len(parsed_objects),
                    "total_errors": len(errors),
                },
                "object_counts": dict(sorted(by_type.items())),
                "bundle_count": len(bundle_dicts),
            }

            # Build search index
            search_index = {}
            for obj in parsed_objects:
                search_index[obj.name] = {
                    "uuid": obj.uuid,
                    "type": obj.object_type,
                }

            # Build orphan index
            bundled_uuids = set(bundle_assignments.keys())
            orphan_index = {
                "total": len(parsed_objects) - len(bundled_uuids),
                "by_type": {},
            }
            for obj in parsed_objects:
                if obj.uuid not in bundled_uuids:
                    t = obj.object_type
                    orphan_index["by_type"][t] = orphan_index["by_type"].get(t, 0) + 1

            # Save parsed context to disk for the extension to query
            from app.context_store import save_parsed_context
            save_parsed_context(
                parsed_objects=parsed_objects,
                dependencies=dependencies,
                source_filename=file.filename or "unknown.zip",
                bundle_dicts=bundle_dicts,
            )

            summary = ParseResponse(
                total_files=len(contents.xml_files),
                objects_parsed=len(parsed_objects),
                errors_count=len(errors),
                object_counts=dict(sorted(by_type.items())),
                bundle_count=len(bundle_dicts),
            )

            return ParseFullResponse(
                summary=summary,
                app_overview=app_overview,
                search_index=search_index,
                bundles=bundle_dicts,
                graph=graph,
                orphan_index=orphan_index,
            )
        finally:
            reader.cleanup(contents.temp_dir)

    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Solutions parser not installed. Run: pip install -e ./solutions-atlas-parser-main. Error: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {str(e)[:500]}")
    finally:
        if temp_zip and os.path.exists(temp_zip.name):
            os.unlink(temp_zip.name)


@router.post("/parse/summary", response_model=ParseResponse)
async def parse_package_summary(
    file: UploadFile = File(..., description="Appian package ZIP file"),
    locale: str = Query("en-US", description="Locale for translation resolution"),
):
    """
    Quick parse -- returns only the summary (object counts, error count).
    Skips dependency analysis and bundle generation for speed.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    temp_zip = None
    try:
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        content = await file.read()
        temp_zip.write(content)
        temp_zip.close()

        from appian_parser.package_reader import PackageReader
        from appian_parser.type_detector import TypeDetector
        from appian_parser.parser_registry import ParserRegistry

        reader = PackageReader()
        detector = TypeDetector()
        registry = ParserRegistry()

        contents = reader.read(temp_zip.name)

        try:
            parsed_objects, errors = _parse_all_objects(
                contents.xml_files, detector, registry
            )

            by_type: dict[str, int] = {}
            for obj in parsed_objects:
                by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1

            return ParseResponse(
                total_files=len(contents.xml_files),
                objects_parsed=len(parsed_objects),
                errors_count=len(errors),
                object_counts=dict(sorted(by_type.items())),
                bundle_count=0,
            )
        finally:
            reader.cleanup(contents.temp_dir)

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Solutions parser not installed: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {str(e)[:500]}")
    finally:
        if temp_zip and os.path.exists(temp_zip.name):
            os.unlink(temp_zip.name)


@router.get("/types")
async def list_supported_types():
    """List all Appian object types the parser can handle."""
    try:
        from appian_parser.parser_registry import ParserRegistry
        registry = ParserRegistry()
        return {"types": sorted(registry.get_supported_types())}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Solutions parser not installed: {e}")


# ─── Helpers ─────────────────────────────────────────────────────

def _parse_all_objects(xml_files: list[str], detector, registry):
    """Parse all XML files into ParsedObjects."""
    from appian_parser.domain.models import ParsedObject, ParseError
    from appian_parser.diff_hash import DiffHashService

    parsed_objects: list[ParsedObject] = []
    errors: list[ParseError] = []

    for xml_file in xml_files:
        detection = None
        try:
            detection = detector.detect(xml_file)
            if detection.is_excluded or detection.is_unknown:
                continue
            parser = registry.get_parser(detection.mapped_type)
            parsed_data = parser.parse(xml_file)
            if not parsed_data or not parsed_data.get("uuid"):
                continue
            diff_hash = DiffHashService.generate_hash(parsed_data)
            parsed_objects.append(ParsedObject(
                uuid=parsed_data["uuid"],
                name=parsed_data.get("name", "Unknown"),
                object_type=detection.mapped_type,
                data=parsed_data,
                diff_hash=diff_hash,
                source_file=os.path.basename(xml_file),
            ))
        except Exception as e:
            errors.append(ParseError(
                file=os.path.basename(xml_file),
                error=str(e),
                object_type=detection.mapped_type if detection else "Unknown",
            ))

    return parsed_objects, errors
