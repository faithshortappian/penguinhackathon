# Appian Parser — Steering Document

## What This Project Is

A standalone Python library (v1.0.0) that parses Appian low-code application packages (ZIP files containing XML/XSD) into structured, LLM-ready JSON. It is the core parsing engine behind the GAM Appian Knowledge Base system. Not directly user-facing — it produces structured data consumed by a downstream MCP server and knowledge base.

## Problem Statement

Appian exports applications as ZIPs with thousands of XML files full of opaque UUIDs (`_a-0006eed1-...`), Record Type URNs (`urn:appian:record-field:v1:...`), and Translation URNs. These are unreadable by humans or AI. This parser converts them into human-readable JSON with all references resolved to names like `rule!GetCustomerAddress`, `recordType!Vendor.vendorName`, and actual translated text.

## Tech Stack

- Python 3.10+ (stdlib only — zero runtime dependencies)
- `xml.etree.ElementTree` for XML parsing
- `re` for pattern matching, `json` for serialization, `hashlib` for SHA-512 hashing
- Dev: `pytest`, `pytest-cov`
- Optional: `mcp[cli]` for the MCP server component
- Optional: `flask` for the web upload UI

## Project Structure

```
appian_parser/              # Core library
├── cli.py                  # CLI orchestration — main entry point (dump_package)
├── package_reader.py       # ZIP extraction → PackageContents
├── type_detector.py        # XML root tag → object type classification
├── parser_registry.py      # Factory routing type → parser instance
├── diff_hash.py            # SHA-512 content hashing
├── parsers/                # 15 type-specific XML parsers + 1 fallback
│   ├── base_parser.py      # ABC with shared XML utilities
│   ├── process_model_parser.py  # Largest parser (1486 LOC, 80+ node types)
│   ├── record_type_parser.py    # Fields, relationships, views, actions
│   ├── interface_parser.py      # SAIL UI definitions
│   ├── expression_rule_parser.py
│   ├── integration_parser.py
│   ├── web_api_parser.py
│   ├── site_parser.py
│   ├── cdt_parser.py
│   ├── constant_parser.py
│   ├── connected_system_parser.py
│   ├── control_panel_parser.py
│   ├── group_parser.py
│   ├── translation_set_parser.py
│   ├── translation_string_parser.py
│   ├── application_parser.py
│   ├── data_store_parser.py
│   └── unknown_object_parser.py
├── resolution/             # In-memory reference resolution
│   ├── reference_resolver.py    # Coordinator: builds caches, walks field paths, delegates
│   ├── uuid_resolver.py         # UUID → rule!/cons!/type!
│   ├── record_type_resolver.py  # RT URN → recordType!Name.field
│   ├── translation_resolver.py  # Translation URN → translated text
│   ├── label_bundle_resolver.py # .properties file resolution
│   └── uuid_utils.py            # UUID format detection/extraction
├── dependencies/
│   └── analyzer.py         # Pattern-based dependency graph builder
├── domain/                 # Shared config, models, constants
│   ├── constants.py        # Regex patterns, field paths (SAIL_CODE_FIELDS, UUID_FIELDS, STRUCTURAL_FIELDS)
│   ├── models.py           # ParsedObject, ParseError, DumpOptions, DumpResult
│   ├── enriched_models.py  # EnrichedBundle, ObjectEnrichment, TypedEdge, etc.
│   ├── enums.py            # DependencyTypeEnum
│   ├── field_walker.py     # Dotted field path walker (e.g. "nodes[].config.expression")
│   ├── appian_type_resolver.py  # XSD/Appian type name resolution
│   └── node_types/         # Process model node type registry (500+ LOC)
├── enrichment/             # Post-processing enrichment layer
│   ├── enricher.py         # Orchestrator for all enrichment
│   ├── tag_classifier.py   # Semantic tag assignment (approval, CRUD, etc.)
│   ├── graph_enricher.py   # Edge type classification for process flows
│   ├── depth_calculator.py # BFS dependency depth from entry points
│   ├── path_analyzer.py    # Critical path analysis (longest, most-nodes)
│   ├── statistics_collector.py  # Bundle/object statistics
│   └── edge_types.py       # EdgeType enum and EdgeMetadata
└── output/                 # JSON output generation
    ├── bundle_coordinator.py     # Bundle generation orchestrator (BFS traversal)
    ├── bundle_structure_builder.py  # structure.json per bundle
    ├── bundle_code_builder.py       # code.json per bundle
    ├── bundle_builder.py            # Legacy monolithic bundle builder
    ├── bundle_summarizer.py         # Human-readable bundle summaries
    ├── search_index_builder.py      # search_index.json
    ├── app_overview_builder.py      # app_overview.json
    ├── object_dependency_writer.py  # objects/<uuid>.json
    ├── orphan_writer.py             # orphans/ directory
    ├── enrichment_writer.py         # enrichment/ output
    ├── json_dumper.py               # Error file writer
    └── manifest_builder.py          # Legacy manifest

mcp_server/                 # MCP server exposing parsed data as AI tools
├── server.py               # 20+ MCP tools (search, query, batch_get, etc.)
├── datasource.py           # LocalDataSource / GitHubDataSource abstraction

web/                        # Flask upload UI
├── app.py                  # Upload ZIP, browse output

scripts/
└── validate_restructured_output.py  # Output correctness validation

tests/                      # pytest test suite
├── conftest.py             # Shared fixtures, sample XML generators
├── test_cli.py             # End-to-end integration
├── parsers/                # Parser unit tests
├── resolution/             # Resolver unit tests
├── dependencies/           # Analyzer tests
└── enrichment/             # Enrichment tests
```

## Data Pipeline

The pipeline runs sequentially in `cli.py:dump_package()`:

1. **Extract** — `PackageReader.read()` unzips to temp dir, discovers XML/XSD files
2. **Classify** — `TypeDetector.detect()` reads XML root tag, maps to one of 17 object types
3. **Parse** — `ParserRegistry.get_parser()` routes to type-specific parser, returns structured dict
4. **Hash** — `DiffHashService.generate_hash()` produces SHA-512 for change detection
5. **Resolve** — `ReferenceResolver.resolve_all()` replaces UUIDs/URNs with human-readable names (mutates in place)
6. **Analyze** — `DependencyAnalyzer.analyze()` extracts inter-object dependencies via regex on SAIL code + structural UUID fields
7. **Enrich** — `Enricher.enrich_all()` adds tags, statistics, critical paths, dependency depths
8. **Output** — Multiple writers produce the final directory structure:
   - `app_overview.json` — package metadata + bundle index + dependency summary
   - `search_index.json` — name → {uuid, type, bundles, deps} lookup
   - `bundles/<Name>/structure.json` — flow, relationships, metadata (5-50KB)
   - `bundles/<Name>/code.json` — SAIL code keyed by UUID (50KB-2MB)
   - `objects/<uuid>.json` — per-object calls/called_by/bundles
   - `orphans/` — objects not reachable from any entry point
   - `enrichment/` — tags, statistics, critical paths

## Bundle System

6 bundle types, each a self-contained functional flow discovered via entry point detection + BFS graph traversal:

| Type | Entry Point | What It Captures |
|------|-------------|------------------|
| action | Record Type Action | Action → process model → form → all deps |
| process | Standalone Process Model | PM not triggered by any action/subprocess |
| page | Record Type Views | Summary/detail views → interfaces → deps |
| site | Site | Navigation → all page targets → interfaces |
| dashboard | Control Panel | Dashboard → interfaces → record types |
| web_api | Web API | API endpoint → all called rules/integrations |

Bundles are split into `structure.json` (metadata, always loaded) and `code.json` (SAIL code, loaded on demand) to prevent LLM context overflow.

## Reference Resolution

Three resolver types, all operating in-memory from parsed object data:

- **UUIDResolver**: `#"_a-0006eed1-..._43398"` → `rule!AS_GSS_BL_validateVendors` (uses canonical prefix matching to handle cross-app suffixes)
- **RecordTypeURNResolver**: `urn:appian:record-field:v1:{rt_uuid}/{field_uuid}` → `recordType!Vendor.vendorName`
- **TranslationResolver**: `urn:appian:translation-string:v1:{uuid}` → `"Bonding Required To Bid"` (locale-aware with fallback)

Field paths for resolution are declaratively configured in `domain/constants.py` (`SAIL_CODE_FIELDS`, `UUID_FIELDS`). The `field_walker.py` utility walks these dotted paths (e.g. `nodes[].inputs[].input_expression`) through nested dicts/lists.

## Dependency Analysis

`DependencyAnalyzer` extracts dependencies from two sources:
1. **SAIL code patterns** — regex for `rule!Name(`, `cons!Name`, `recordType!Name`, `type!Name` in resolved code
2. **Structural UUID fields** — configured in `STRUCTURAL_FIELDS` (e.g. process model's `nodes[].interface_uuid`)

Each dependency is a frozen dataclass: `Dependency(source_uuid, source_name, source_type, target_uuid, target_name, target_type, dependency_type)`.

Dependency types: `CALLS`, `USES_CONSTANT`, `USES_CDT`, `USES_RECORD_TYPE`, `USES_INTEGRATION`, `USES_CONNECTED_SYSTEM`, `USES_GROUP`, `USES_DATA_STORE`.

## Key Data Models

```python
ParsedObject(uuid, name, object_type, data: dict, diff_hash, source_file)
Dependency(source_uuid, source_name, source_type, target_uuid, target_name, target_type, dependency_type)  # frozen
DumpOptions(excluded_types, include_raw_xml, include_dependencies, include_enrichment, locale, pretty)
DumpResult(total_files, objects_parsed, errors_count, output_dir)
```

## Design Principles (Must Follow)

1. **Zero runtime dependencies** — stdlib only. No external packages for parsing.
2. **Single Responsibility** — each class does one thing. Parsers parse, resolvers resolve, writers write.
3. **Open/Closed** — new object types = new parser class + registry entry + tag mapping. No changes to existing code.
4. **Declarative field paths** — resolution and dependency extraction paths are data in `constants.py`, not code.
5. **In-memory resolution** — no DB, no API calls, no file I/O during resolution. All lookups from parsed objects.
6. **In-place mutation** — `ReferenceResolver` mutates `ParsedObject.data` directly for performance.
7. **Fail fast, continue parsing** — invalid files produce `ParseError` entries but don't halt the pipeline.
8. **Immutable value objects** — `Dependency`, `TypeDetectionResult` are frozen dataclasses.
9. **Content hashing** — every object gets SHA-512 for change detection/dedup.

## Coding Conventions

- Python 3.10+ with type hints on all function signatures
- PEP 8 style
- Docstrings on public APIs
- All parsers extend `BaseParser` ABC and implement `parse(xml_file: str) -> dict`
- Field path notation: `field` for direct access, `field[]` for list iteration, `field.subfield` for nesting
- Regex patterns compiled once as module-level constants in `domain/constants.py`
- Test files mirror source structure under `tests/`

## CLI Usage

```bash
python -m appian_parser dump <package.zip> <output_dir> [--locale LOCALE] [--exclude-types TYPES] [--no-deps] [--no-enrich] [--no-pretty]
python -m appian_parser types
```

## Testing

```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=appian_parser --cov-report=term-missing
```

## Performance Baseline

On MacBook Pro M1, 16GB RAM:
- ~2,500 objects: ~1.9s parse time, ~450MB peak memory
- ~3,500 objects: ~2.7s parse time, ~620MB peak memory
- Bottlenecks: reference resolution (~40%), bundle generation (~30%), JSON serialization (~20%), XML parsing (~10%)

## Related Repository: solutions-atlas-mcp-server

The parsed JSON output from this repo is consumed by the **Appian Atlas MCP Server** (`/Users/ramaswamy.u/repo-gitlab/solutions-atlas-mcp-server`), which exposes it to LLM agents (Amazon Q, Kiro) via the Model Context Protocol.

### How They Connect

```
appian-parser                          solutions-knowledge-base (GitLab)       solutions-atlas-mcp-server
─────────────                          ─────────────────────────────────       ──────────────────────────
ZIP → parse → JSON output  ──commit──▶  data/<AppName>/                  ◀──API──  GitLabDataSource
                                         ├── app_overview.json                      │
                                         ├── search_index.json                      ▼
                                         ├── bundles/<Name>/              MCP Tools (9 tools)
                                         │   ├── structure.json           exposed to LLM agents
                                         │   └── code.json
                                         ├── objects/<uuid>.json
                                         └── orphans/
```

1. **appian-parser** produces the structured JSON directory
2. That output is committed to a **solutions-knowledge-base** GitLab repo (project ID 13478) under `data/<AppName>/`
3. **solutions-atlas-mcp-server** reads that data via GitLab API and exposes it as MCP tools

### Atlas MCP Server Architecture

- **Package**: `atlas_mcp` (v1.0.0), Python 3.11, dependencies: `requests`, `mcp`
- **Entry point**: `main.py` → `AtlasMCPServer` → stdio MCP transport
- **Data source**: `GitLabDataSource` — reads JSON files from GitLab repo via API, with LRU cache (500 entries) + pinned anchor files (`app_overview.json`, `search_index.json`, `orphans/_index.json`)
- **Auth**: GitLab personal access token (read-only enforced — server refuses tokens with write scopes via `AtlasTokenValidator`)
- **Deployment**: Docker container, distributed via GitLab Container Registry, CI/CD via `.gitlab-ci.yml`

### MCP Tools Exposed (9 tools)

These are the tools LLM agents use to query our parsed data:

| Tool | What It Does | Files It Reads |
|------|-------------|----------------|
| `list_applications` | List all apps with object counts + bundle coverage | `app_overview.json` for each app |
| `get_app_overview` | Full app overview (metadata, bundles, deps, coverage) | `app_overview.json` |
| `search_bundles` | Search bundles by name, filter by type | `app_overview.json` (bundle index) |
| `get_bundle` | Get bundle at detail level: summary/structure/full | `bundles/<id>/structure.json` + optionally `code.json` |
| `search_objects` | Search objects by name, filter by type | `search_index.json` |
| `get_dependencies` | Get calls/called_by for an object | `search_index.json` → `objects/<uuid>.json` |
| `get_object_detail` | Full object detail by UUID | `objects/<uuid>.json` |
| `list_orphans` | List unreachable objects grouped by type | `orphans/_index.json` |
| `get_orphan` | Full orphan detail including code | `orphans/<uuid>.json` |

### Why This Matters for appian-parser Development

Any changes to the **output format** of this parser directly affect the MCP server's ability to read the data. Specifically:

- **File paths** — the MCP server hardcodes paths like `bundles/{id}/structure.json`, `objects/{uuid}.json`, `orphans/_index.json`
- **JSON schema** — the MCP server reads specific keys: `_metadata`, `entry_point`, `flow`, `objects`, `package_info`, `coverage`, `bundles` from `app_overview.json`; `uuid`, `type`, `bundles`, `inbound_count`, `outbound_count` from `search_index.json`; `sail_code` from `code.json`
- **Bundle ID resolution** — the MCP server resolves bundle IDs by matching `root_name` from the bundle index in `app_overview.json`
- **Truncation** — `get_bundle` with `detail_level=full` truncates at 80K chars, so bundle size matters

### Atlas Server Config

| Env Var | Purpose | Default |
|---------|---------|---------|
| `GITLAB_TOKEN` | GitLab PAT (read-only) | required |
| `ATLAS_DATA_PROJECT_ID` | Knowledge base repo project ID | required (currently `13478`) |
| `ATLAS_DATA_BRANCH` | Branch to read from | `main` |
| `ATLAS_DATA_PREFIX` | Directory prefix for app data | `data` |

## Important Notes for Development

- `ProcessModelParser` is the most complex parser (1,486 LOC) — handle 80+ node types. Changes here need careful testing.
- `bundle_builder.py` is a legacy monolithic version; `bundle_coordinator.py` + `bundle_structure_builder.py` + `bundle_code_builder.py` is the current split architecture.
- The MCP server (`mcp_server/`) is a separate installable package with its own `pyproject.toml`.
- `test_data/` contains real Appian package ZIPs for integration testing — these are large binary files.
- `prompts/` contains documentation generation prompts for different bundle types.
- Resolution accuracy: ~99.95% for UUIDs, ~93-98% for RT URNs. Unresolved cases: multi-segment RT URN chains, cross-app references, dynamically constructed URNs.
