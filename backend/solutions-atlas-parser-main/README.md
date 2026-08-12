# Appian Parser

A standalone Python library that parses Appian application packages (ZIP files containing XML/XSD) into structured, LLM-ready JSON. This is the **core parsing engine** that powers the GAM Appian Knowledge Base system.

> **Note**: This repository is not directly exposed to end users. It serves as the foundational parsing layer that processes Appian packages into the structured data consumed by the [gam-knowledge-base](https://gitlab.appian-stratus.com/ramaswamy.u/gam-knowledge-base) repository and its MCP server.

## Table of Contents

- [Purpose](#purpose)
- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Output Structure](#output-structure)
- [Bundle System](#bundle-system)
- [Reference Resolution](#reference-resolution)
- [Supported Object Types](#supported-object-types)
- [Architecture Deep Dive](#architecture-deep-dive)
- [Module Reference](#module-reference)
- [Design Principles](#design-principles)
- [Performance](#performance)
- [Testing](#testing)
- [Development Workflow](#development-workflow)
- [Contributing](#contributing)

---

## Purpose

The Appian Parser is designed to enable **reverse-engineering and analysis** of Appian low-code applications by converting proprietary XML/XSD package formats into structured JSON that can be:

1. **Queried by AI assistants** - All opaque identifiers (UUIDs, URNs) are resolved to human-readable names
2. **Version controlled** - JSON output can be committed to Git for history tracking and diffing
3. **Analyzed programmatically** - Complete dependency graphs and self-contained bundles enable impact analysis
4. **Documented automatically** - Bundles provide complete functional flows for documentation generation

### What Problem Does This Solve?

Appian applications are exported as ZIP files containing thousands of XML files with:
- **Opaque UUIDs** like `#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"` instead of `rule!GetCustomerAddress`
- **URN references** like `urn:appian:record-field:v1:{uuid}/{uuid}` instead of `recordType!Vendor.vendorName`
- **Scattered dependencies** across hundreds of files with no clear entry points
- **No built-in tooling** for analysis, documentation, or understanding business logic

This parser solves all of these problems by producing a **single, coherent JSON representation** of the entire application with all references resolved and dependencies mapped.

---

## Key Features

### 1. Zero Runtime Dependencies
- Built entirely on Python 3.10+ standard library
- No external packages required for parsing (xml.etree, re, json, hashlib)
- Dev dependencies only for testing (pytest, pytest-cov)

### 2. Complete Reference Resolution
Automatically resolves three types of opaque identifiers:

| Type | Raw Format | Resolved Format |
|------|-----------|-----------------|
| **UUID References** | `#"_a-0006eed1-..._43398"` | `rule!GetCustomerAddress` |
| **Record Type URNs** | `urn:appian:record-field:v1:{rt}/{field}` | `recordType!Addresses.addressId` |
| **Translation URNs** | `urn:appian:translation-string:v1:{uuid}` | `"Bonding Required To Bid"` |

Resolution is performed **in-memory** using data from the parsed objects themselves—no external database or API needed.

### 3. Comprehensive Dependency Analysis
- Extracts inter-object dependencies via pattern matching on SAIL code and structured fields
- Builds complete directed dependency graph
- Identifies entry points (actions, standalone processes, sites, web APIs)
- Detects orphaned objects (not reachable from any entry point)

### 4. Self-Contained Bundle Generation
Creates 6 types of bundles, each representing a complete functional flow:

| Bundle Type | Entry Point | Description |
|-------------|-------------|-------------|
| **action** | Record Type Action | Action → process model → form interface → all dependencies |
| **process** | Standalone Process Model | PM not triggered by any action or subprocess |
| **page** | Record Type Views | Summary/detail views → interfaces → supporting objects |
| **site** | Site | Navigation container → all page targets → interfaces |
| **dashboard** | Control Panel | Dashboard → interfaces → record types |
| **web_api** | Web API | API endpoint → all called rules/integrations |

Each bundle includes the **full transitive dependency tree** via breadth-first graph traversal.

### 5. Incremental Loading Support
Bundles are split into two files to prevent context overflow:
- `structure.json` - Metadata, relationships, parameters, calls/called_by (5-50KB)
- `code.json` - SAIL code keyed by UUID, loaded on demand (50KB-2MB)

### 6. Content Hashing
Every object gets a SHA-512 content hash for:
- Change detection across versions
- Deduplication
- Integrity verification

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         ZIP Input                                │
│                  (Appian Package Export)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PackageReader                               │
│  • Extracts ZIP to temp directory                                │
│  • Discovers all XML/XSD files                                   │
│  • Returns PackageContents with file paths                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TypeDetector                                │
│  • Inspects XML root tag (<interfaceHaul>, <processModelHaul>)   │
│  • Maps to internal object type (Interface, Process Model, etc.) │
│  • Handles <contentHaul> wrappers                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ParserRegistry                               │
│  • Routes detected type to appropriate parser                    │
│  • Factory pattern - returns parser instance                     │
│  • 15 type-specific parsers + 1 fallback                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Object Parsers (15)                            │
│  • Each extends BaseParser (ABC)                                 │
│  • Extracts structured data from XML                             │
│  • Returns Python dict with standardized schema                  │
│                                                                   │
│  Types: Interface, Expression Rule, Process Model, Record Type,  │
│         CDT, Integration, Web API, Site, Group, Constant,        │
│         Connected System, Control Panel, Translation Set/String  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DiffHashService                               │
│  • Generates SHA-512 hash of object content                      │
│  • Used for change detection and deduplication                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ReferenceResolver                              │
│  • Builds in-memory lookup caches from parsed objects            │
│  • Walks configured field paths per object type                  │
│  • Delegates to 3 specialized resolvers:                         │
│    - UUIDResolver: UUID → rule!/cons!/type!                      │
│    - RecordTypeURNResolver: RT URN → recordType!Name.field       │
│    - TranslationResolver: Translation URN → translated text      │
│  • Mutates parsed object data in place                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DependencyAnalyzer                              │
│  • Pattern-based extraction from SAIL code and structured fields │
│  • Builds directed dependency graph                              │
│  • Returns list of Dependency objects (source → target)          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Output Layer                                 │
│                                                                   │
│  BundleCoordinator:                                              │
│    • Discovers entry points (actions, processes, sites, etc.)    │
│    • BFS graph walk for transitive dependencies                  │
│    • Delegates to BundleStructureBuilder + BundleCodeBuilder     │
│                                                                   │
│  SearchIndexBuilder:                                             │
│    • Builds name → {uuid, type, bundles, deps} lookup            │
│                                                                   │
│  AppOverviewBuilder:                                             │
│    • Package metadata + bundle index + dependency summary        │
│                                                                   │
│  ObjectDependencyWriter:                                         │
│    • Per-object files: calls[], called_by[], bundles[]           │
│                                                                   │
│  OrphanWriter:                                                   │
│    • Objects not reachable from any entry point                  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Structured JSON Output                        │
│                                                                   │
│  output_dir/                                                     │
│  ├── app_overview.json          # Package metadata + index       │
│  ├── search_index.json          # Fast name lookup               │
│  ├── bundles/                   # Self-contained flows           │
│  │   └── <BundleName>/                                           │
│  │       ├── structure.json     # Flow + relationships           │
│  │       └── code.json          # SAIL code by UUID              │
│  ├── objects/                   # Per-object dependency files    │
│  │   └── <uuid>.json                                             │
│  └── orphans/                   # Unreachable objects            │
│      ├── _index.json                                             │
│      └── <uuid>.json                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- **Python 3.10 or later**
- **No runtime dependencies** (stdlib only)
- **Dev dependencies** (optional, for testing):
  - `pytest` - Test framework
  - `pytest-cov` - Coverage reporting

---

## Installation

### For Development

```bash
cd appian-parser

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install pytest pytest-cov

# Verify installation
python -m appian_parser types
```

### As a Library

```bash
pip install -e git+https://gitlab.appian-stratus.com/ramaswamy.u/appian-parser.git#egg=appian-parser
```

---

## Quick Start

### Parse a Package

```bash
# Basic usage
python -m appian_parser dump MyApplication.zip ./output

# With options
python -m appian_parser dump MyApp.zip ./output \
  --locale es-ES \
  --exclude-types "Group,Translation String" \
  --no-pretty
```

**Output:**
```
Parsing MyApplication.zip...
Done! Parsed 2304 objects (0 errors)
Output: ./output
```

### List Supported Types

```bash
python -m appian_parser types
```

**Output:**
```
  CDT
  Connected System
  Constant
  Expression Rule
  Group
  Integration
  Interface
  Process Model
  Record Type
  Site
  Translation Set
  Translation String
  Web API
```

---

## CLI Reference

### `dump` Command

Parse an Appian package and write structured JSON output.

```bash
python -m appian_parser dump <package.zip> <output_dir> [options]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `package.zip` | Yes | Path to Appian package ZIP file |
| `output_dir` | Yes | Output directory for JSON files |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--locale LOCALE` | `en-US` | Locale for translation string resolution |
| `--exclude-types TYPES` | none | Comma-separated object types to exclude from parsing |
| `--no-deps` | false | Skip dependency analysis and bundle generation (faster) |
| `--no-pretty` | false | Disable JSON pretty-printing (smaller files, harder to read) |

**Examples:**

```bash
# Parse with Spanish locale
python -m appian_parser dump MyApp.zip ./output --locale es-ES

# Skip groups and translations
python -m appian_parser dump MyApp.zip ./output \
  --exclude-types "Group,Translation String"

# Fast parse without dependencies (no bundles)
python -m appian_parser dump MyApp.zip ./output --no-deps

# Compact JSON output
python -m appian_parser dump MyApp.zip ./output --no-pretty
```

### `types` Command

List all supported Appian object types.

```bash
python -m appian_parser types
```

---

## Output Structure

The parser generates a structured directory with the following layout:

```
output_dir/
├── app_overview.json          # Package metadata, bundle index, dependency summary
├── search_index.json          # Fast object name lookup
├── bundles/                   # Self-contained functional flows
│   ├── <ActionName>/
│   │   ├── structure.json     # Flow, relationships, metadata (no code)
│   │   └── code.json          # SAIL code keyed by UUID
│   ├── <ProcessName>/
│   │   ├── structure.json
│   │   └── code.json
│   └── ...
├── objects/                   # Per-object dependency files
│   ├── <uuid-1>.json          # calls[], called_by[], bundles[]
│   ├── <uuid-2>.json
│   └── ...
└── orphans/                   # Objects not reachable from any entry point
    ├── _index.json            # Orphan catalog grouped by type
    ├── <uuid-1>.json          # Individual orphan with code
    └── ...
```

### File Descriptions

#### `app_overview.json`

Complete application overview in a single file:

```json
{
  "_metadata": {
    "parser_version": "2.0.0",
    "generated_at": "2026-02-13T05:40:32.173560+00:00",
    "source_package": "SourceSelection v2.8.0.zip"
  },
  "package_info": {
    "filename": "SourceSelection v2.8.0.zip",
    "total_files_in_zip": 2639,
    "total_xml_files": 2567,
    "total_parsed_objects": 2461,
    "total_errors": 0,
    "parse_duration_seconds": 1.88
  },
  "object_counts": {
    "CDT": 107,
    "Constant": 582,
    "Expression Rule": 990,
    "Interface": 489,
    "Process Model": 117,
    "Record Type": 49
  },
  "bundles": [
    {
      "id": "AS_GSS_Complete_LPTA_Evaluation",
      "bundle_type": "action",
      "root_name": "AS GSS Complete LPTA Evaluation",
      "parent_name": "AS GSS Evaluation RECORD",
      "object_count": 282,
      "key_objects": ["AS_GSS_PM_CompleteLPTAEvaluation", "AS_GSS_IF_CompleteLPTAEvaluation"]
    }
  ],
  "dependency_summary": {
    "total": 5234,
    "by_type": {
      "rule_call": 3421,
      "interface_call": 892,
      "constant_ref": 654
    },
    "most_depended_on": [
      {"name": "AS_CO_UT_isBlank", "type": "Expression Rule", "inbound_count": 1247}
    ]
  },
  "coverage": {
    "total_objects": 2461,
    "bundled": 1898,
    "orphaned": 563
  }
}
```

#### `search_index.json`

Fast object name lookup:

```json
{
  "AS_GSS_PM_CompleteLPTAEvaluation": {
    "uuid": "_a-0006eed1-0f7f-8000-0020-7f0000014e7a",
    "type": "Process Model",
    "bundles": ["AS_GSS_Complete_LPTA_Evaluation"],
    "inbound_count": 3,
    "outbound_count": 47
  }
}
```

#### `bundles/<BundleName>/structure.json`

Bundle structure without SAIL code (5-50KB):

```json
{
  "_metadata": {
    "bundle_id": "AS_GSS_Complete_LPTA_Evaluation",
    "bundle_type": "action",
    "root_uuid": "_a-0006eed1-...",
    "root_name": "AS GSS Complete LPTA Evaluation",
    "parent_name": "AS GSS Evaluation RECORD",
    "object_count": 282
  },
  "entry_point": {
    "uuid": "_a-0006eed1-...",
    "name": "AS GSS Complete LPTA Evaluation",
    "type": "Record Type Action",
    "description": "Completes LPTA evaluation and generates consensus report"
  },
  "flow": [
    "Action: AS GSS Complete LPTA Evaluation",
    "  → Process Model: AS_GSS_PM_CompleteLPTAEvaluation",
    "    → Interface: AS_GSS_IF_CompleteLPTAEvaluation",
    "      → Rule: AS_GSS_BL_validateLPTAScores"
  ],
  "objects": [
    {
      "uuid": "_a-0006eed1-...",
      "name": "AS_GSS_PM_CompleteLPTAEvaluation",
      "type": "Process Model",
      "description": "Main process for LPTA completion",
      "calls": ["AS_GSS_IF_CompleteLPTAEvaluation", "AS_GSS_BL_validateLPTAScores"],
      "called_by": ["AS GSS Complete LPTA Evaluation"],
      "parameters": [
        {"name": "evaluationId", "type": "Number(Integer)"}
      ]
    }
  ]
}
```

#### `bundles/<BundleName>/code.json`

SAIL code keyed by UUID (50KB-2MB):

```json
{
  "objects": {
    "_a-0006eed1-...": {
      "sail_code": "a!startProcess(\n  processModel: cons!AS_GSS_PM_CompleteLPTAEvaluation,\n  processParameters: {\n    evaluationId: ri!evaluationId\n  }\n)"
    }
  }
}
```

#### `objects/<uuid>.json`

Per-object dependency file:

```json
{
  "uuid": "_a-0006eed1-...",
  "name": "AS_GSS_BL_validateLPTAScores",
  "type": "Expression Rule",
  "calls": [
    {"uuid": "_b-...", "name": "AS_CO_UT_isBlank", "type": "Expression Rule"},
    {"uuid": "_c-...", "name": "AS_GSS_CO_LPTA_MIN_SCORE", "type": "Constant"}
  ],
  "called_by": [
    {"uuid": "_a-...", "name": "AS_GSS_PM_CompleteLPTAEvaluation", "type": "Process Model"}
  ],
  "bundles": ["AS_GSS_Complete_LPTA_Evaluation"]
}
```

#### `orphans/_index.json`

Catalog of orphaned objects:

```json
{
  "total": 563,
  "by_type": {
    "Expression Rule": 342,
    "Interface": 156,
    "Constant": 65
  },
  "objects": [
    {
      "uuid": "_orphan-1-...",
      "name": "AS_GSS_DEPRECATED_OldRule",
      "type": "Expression Rule"
    }
  ]
}
```

#### `orphans/<uuid>.json`

Individual orphan with full detail including code:

```json
{
  "uuid": "_orphan-1-...",
  "name": "AS_GSS_DEPRECATED_OldRule",
  "type": "Expression Rule",
  "data": {
    "sail_code": "/* Deprecated - use AS_GSS_NewRule instead */",
    "inputs": [],
    "output_type": "Text"
  },
  "calls": [],
  "called_by": []
}
```

---

## Bundle System

The bundle system is the core innovation of this parser. It transforms a flat collection of 2,000+ objects into **self-contained functional flows** that can be understood independently.

### Bundle Types

#### 1. Action Bundles (`action`)

**Entry Point**: Record Type Action

**What It Captures**: A complete user-initiated workflow from a record action button.

**Flow**:
```
Record Action
  → Target Process Model
    → Start Form Interface
      → All called rules, integrations, constants
        → Transitive dependencies
```

**Example**: "Complete LPTA Evaluation" action
- Entry: Record action button
- Includes: Process model, form interface, validation rules, email integrations
- Use case: Understanding what happens when user clicks "Complete Evaluation"

#### 2. Process Bundles (`process`)

**Entry Point**: Standalone Process Model (not triggered by any action or subprocess)

**What It Captures**: Background processes, scheduled jobs, or orphaned process models.

**Flow**:
```
Process Model
  → Subprocesses
    → Interfaces (if any)
      → All called rules, integrations
```

**Example**: "Nightly Cleanup Process"
- Entry: Scheduled process model
- Includes: All subprocesses, cleanup rules, database writes
- Use case: Understanding batch/background operations

#### 3. Page Bundles (`page`)

**Entry Point**: Record Type Views (Summary View, Detail View, Related Actions)

**What It Captures**: What users see when viewing a record.

**Flow**:
```
Record Type View
  → Summary View Interface
  → Detail View Interface
  → Related Action Interfaces
    → All display rules, formatting utilities
```

**Example**: "Evaluation Record Summary View"
- Entry: Record type summary view
- Includes: All display interfaces, formatting rules
- Use case: Understanding record display logic

#### 4. Site Bundles (`site`)

**Entry Point**: Site (top-level navigation container)

**What It Captures**: Complete site navigation structure.

**Flow**:
```
Site
  → All Page Targets
    → Page Interfaces
      → All called rules, record types
```

**Example**: "Source Selection Site"
- Entry: Site object
- Includes: All navigation pages, dashboards, interfaces
- Use case: Understanding application navigation

#### 5. Dashboard Bundles (`dashboard`)

**Entry Point**: Control Panel (Admin Console dashboard)

**What It Captures**: Admin dashboards and their data sources.

**Flow**:
```
Control Panel
  → Dashboard Interfaces
    → Record Types
      → All data rules, queries
```

**Example**: "Source Selection Settings"
- Entry: Control panel
- Includes: Settings interfaces, configuration record types
- Use case: Understanding admin configuration

#### 6. Web API Bundles (`web_api`)

**Entry Point**: Web API endpoint

**What It Captures**: Complete API endpoint implementation.

**Flow**:
```
Web API
  → SAIL Code
    → All called rules, integrations
      → Database queries, external API calls
```

**Example**: "GET Evaluation Status List"
- Entry: Web API endpoint
- Includes: All business logic, data access rules
- Use case: Understanding API behavior

### Bundle Generation Algorithm

```python
# Pseudocode for bundle generation

1. Discover Entry Points:
   - Find all record type actions
   - Find standalone process models (not called by anything)
   - Find record type views
   - Find sites
   - Find control panels
   - Find web APIs

2. For Each Entry Point:
   a. Create empty bundle
   b. Add entry point object
   c. Initialize queue with entry point UUID
   d. Initialize visited set
   
   e. BFS Traversal:
      while queue not empty:
        current_uuid = queue.pop()
        if current_uuid in visited:
          continue
        visited.add(current_uuid)
        
        # Get all objects this one depends on
        dependencies = get_dependencies(current_uuid)
        
        for dep in dependencies:
          if dep not in visited:
            queue.append(dep)
            add_to_bundle(dep)
   
   f. Build flow visualization (tree structure)
   g. Split into structure.json + code.json
   h. Write to bundles/<bundle_id>/

3. Identify Orphans:
   orphans = all_objects - bundled_objects
   write_orphans(orphans)
```

### Bundle Size Management

Bundles are split into two files to prevent context overflow when loading into LLMs:

| File | Size | Contents | When to Load |
|------|------|----------|--------------|
| `structure.json` | 5-50KB | Metadata, flow, relationships, parameters, calls/called_by | Always (first) |
| `code.json` | 50KB-2MB | SAIL code keyed by UUID | On demand (when code inspection needed) |

This allows AI assistants to:
1. Load structure first to understand flow
2. Only load code when user asks to see implementation
3. Load code for specific objects, not entire bundle

---

## Reference Resolution

One of the most critical features of this parser is **reference resolution**—converting opaque identifiers into human-readable names.

### Why Resolution Matters

Raw Appian XML contains three types of opaque identifiers that make code unreadable:

#### 1. UUID References

**Raw XML**:
```xml
<value>#"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"</value>
```

**Resolved**:
```
rule!AS_GSS_BL_validateVendors
```

#### 2. Record Type URNs

**Raw XML**:
```xml
<value>urn:appian:record-field:v1:_a-0006eed1-.../_b-0007ffa2-...</value>
```

**Resolved**:
```
recordType!Vendor.vendorName
```

#### 3. Translation URNs

**Raw XML**:
```xml
<value>urn:appian:translation-string:v1:_c-0008aab3-...</value>
```

**Resolved**:
```
"Bonding Required To Bid"
```

### Resolution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ReferenceResolver                          │
│                   (Coordinator)                              │
│                                                              │
│  1. Builds lookup caches from parsed objects                │
│  2. Walks configured field paths per object type            │
│  3. Delegates to specialized resolvers                      │
│  4. Mutates parsed object data in place                     │
└────────────┬────────────────┬────────────────┬──────────────┘
             │                │                │
             ▼                ▼                ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  UUIDResolver    │ │ RecordTypeURN    │ │  Translation     │
│                  │ │    Resolver      │ │   Resolver       │
│ UUID → rule!/    │ │ RT URN →         │ │ Translation URN  │
│        cons!/    │ │ recordType!      │ │ → translated     │
│        type!     │ │ Name.field       │ │   text           │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Resolution Process

#### Phase 1: Build Lookup Caches

```python
# UUIDResolver builds name lookup
uuid_lookup = {}
for obj in parsed_objects:
    uuid_lookup[obj.uuid] = {
        'name': obj.name,
        'type': obj.object_type,
        'prefix': extract_canonical_prefix(obj.uuid)
    }

# RecordTypeURNResolver builds RT field lookup
rt_field_lookup = {}
for obj in parsed_objects:
    if obj.object_type == 'Record Type':
        for field in obj.data['fields']:
            urn = build_urn(obj.uuid, field.uuid)
            rt_field_lookup[urn] = f"recordType!{obj.name}.{field.name}"

# TranslationResolver builds translation lookup
translation_lookup = {}
for obj in parsed_objects:
    if obj.object_type == 'Translation String':
        for locale, text in obj.data['translations'].items():
            urn = build_translation_urn(obj.uuid)
            translation_lookup[urn] = text  # Uses specified locale
```

#### Phase 2: Walk Field Paths

For each object type, the resolver walks configured field paths:

```python
# Example: Interface field paths
INTERFACE_PATHS = [
    'sail_code',                    # Main SAIL code
    'parameters.*.default_value',   # Parameter defaults
    'test_inputs.*.value'           # Test case values
]

# Example: Process Model field paths
PROCESS_MODEL_PATHS = [
    'nodes.*.config.expression',    # Node expressions
    'nodes.*.config.assignment',    # Task assignments
    'flows.*.condition'             # Gateway conditions
]
```

#### Phase 3: Pattern Matching & Replacement

```python
# UUID pattern: #"_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398"
UUID_PATTERN = r'#"(_a-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:_[0-9]+)?)"'

# Record Type URN pattern
RT_URN_PATTERN = r'urn:appian:record-field:v1:([^/]+)/([^"]+)'

# Translation URN pattern
TRANSLATION_URN_PATTERN = r'urn:appian:translation-string:v1:([^"]+)'

# Replace in SAIL code
sail_code = obj.data['sail_code']
sail_code = re.sub(UUID_PATTERN, lambda m: resolve_uuid(m.group(1)), sail_code)
sail_code = re.sub(RT_URN_PATTERN, lambda m: resolve_rt_urn(m.group(0)), sail_code)
sail_code = re.sub(TRANSLATION_URN_PATTERN, lambda m: resolve_translation(m.group(0)), sail_code)
```

### Canonical Prefix Matching

UUIDs can have application suffixes that differ between references and definitions:

**Definition**: `_a-0006eed1-0f7f-8000-0020-7f0000014e7a_43398`
**Reference**: `_a-0006eed1-0f7f-8000-0020-7f0000014e7a_tmg-am-am`

The resolver uses **canonical prefix matching** (everything before the last underscore):

```python
def extract_canonical_prefix(uuid: str) -> str:
    """Extract canonical prefix for cross-app matching."""
    if '_' in uuid:
        return uuid.rsplit('_', 1)[0]
    return uuid

# Both resolve to the same canonical prefix:
# _a-0006eed1-0f7f-8000-0020-7f0000014e7a
```

### Resolution Accuracy

Measured on production packages:

| Package | Objects | UUID Resolution | RT URN Resolution |
|---------|---------|-----------------|-------------------|
| SourceSelection v2.8.0 | 2,461 | 99.97% | 98.1% |
| CaseManagementStudio | 3,184 | 99.96% | 97.8% |
| RequirementsManagement v2.3.0 | 3,494 | 99.94% | 92.3% |

**Unresolved cases**:
- Multi-segment RT URN chains (nested record relationships)
- Cross-application references (objects from imported packages)
- Dynamically constructed URNs (rare)

---

## Supported Object Types

The parser supports 15 Appian object types. Each has a dedicated parser that extends `BaseParser`.

### 1. Interface

**XML Tag**: `<interfaceHaul>`

**Key Fields Extracted**:
- SAIL code (complete UI definition)
- Parameters (name, type, default value)
- Test inputs (test case data)
- Security (visibility rules)
- Description

**Use Cases**:
- Form interfaces
- Display interfaces
- Reusable UI components

### 2. Expression Rule

**XML Tag**: `<expressionRuleHaul>`

**Key Fields Extracted**:
- SAIL code (business logic)
- Inputs (name, type, description)
- Output type
- Test cases (inputs + expected outputs)
- Security

**Use Cases**:
- Business logic functions
- Data transformations
- Validation rules
- Utility functions

### 3. Process Model

**XML Tag**: `<processModelHaul>`

**Key Fields Extracted**:
- Nodes (start, end, activity, gateway, subprocess, etc.)
- Flows (connections between nodes with conditions)
- Process variables (name, type, default value)
- Node configurations (expressions, assignments, escalations)
- Complexity score (calculated from node/flow count)

**Use Cases**:
- Workflows
- Background processes
- Scheduled jobs

**Node Types Supported** (80+):
- Start/End nodes
- Activity nodes (User Input Task, Script Task, etc.)
- Gateway nodes (XOR, AND, OR)
- Subprocess nodes
- Integration nodes
- Timer nodes
- Error handling nodes

### 4. Record Type

**XML Tag**: `<recordTypeHaul>`

**Key Fields Extracted**:
- Fields (name, type, required, relationship type)
- Relationships (one-to-many, many-to-one)
- Views (summary, detail, related actions)
- Actions (with target process models and interfaces)
- Security (field-level and record-level)
- Data source (database table or web service)

**Use Cases**:
- Data entities
- Business objects
- User-facing records

### 5. CDT (Custom Data Type)

**XML Tag**: `<dataTypeHaul>` (XSD format)

**Key Fields Extracted**:
- Namespace
- Field definitions (name, type, required, multiple)
- Nested CDT references
- Annotations

**Use Cases**:
- Data structures
- API request/response types
- Database table mappings

### 6. Integration

**XML Tag**: `<integrationHaul>`

**Key Fields Extracted**:
- Connected system reference
- HTTP method (GET, POST, PUT, DELETE)
- URL (with parameter placeholders)
- Headers (static and dynamic)
- Request body (template or expression)
- Response parsing rules
- Authentication config

**Use Cases**:
- REST API calls
- SOAP web service calls
- External system integrations

### 7. Web API

**XML Tag**: `<webApiHaul>`

**Key Fields Extracted**:
- SAIL code (endpoint implementation)
- URL alias (endpoint path)
- HTTP method
- Security (authentication requirements)
- Parameters (query, path, body)

**Use Cases**:
- Inbound API endpoints
- Webhooks
- External system integrations

### 8. Site

**XML Tag**: `<siteHaul>`

**Key Fields Extracted**:
- Hierarchical page structure
- Page targets (interfaces, record types, external URLs)
- Roles (who can access)
- Branding expressions (logo, colors)
- Navigation configuration

**Use Cases**:
- Application navigation
- User portals
- Multi-page applications

### 9. Group

**XML Tag**: `<groupHaul>`

**Key Fields Extracted**:
- Members (users and subgroups)
- Parent group
- Group type (static, dynamic, rule-based)
- Security

**Use Cases**:
- Access control
- Role-based permissions
- Team organization

### 10. Constant

**XML Tag**: `<constantHaul>`

**Key Fields Extracted**:
- Value (text, number, boolean, date, etc.)
- Type
- Scope (application-wide or package-specific)
- Description

**Use Cases**:
- Configuration values
- Reusable references
- Environment-specific settings

### 11. Connected System

**XML Tag**: `<connectedSystemHaul>`

**Key Fields Extracted**:
- Base URL
- Authentication type (Basic, OAuth, API Key, etc.)
- Authentication details (username, token, etc.)
- Timeout settings
- SSL configuration

**Use Cases**:
- External API connections
- Database connections
- Third-party service integrations

### 12. Control Panel

**XML Tag**: `<controlPanelHaul>`

**Key Fields Extracted**:
- JSON settings (dashboard configuration)
- Interfaces (dashboard UI components)
- Record type references (data sources)
- Security

**Use Cases**:
- Admin dashboards
- Configuration panels
- Settings pages

### 13. Translation Set

**XML Tag**: `<translationSetHaul>`

**Key Fields Extracted**:
- Default locale
- Enabled locales
- Security

**Use Cases**:
- Multi-language support
- Locale management

### 14. Translation String

**XML Tag**: `<translationStringHaul>`

**Key Fields Extracted**:
- Translations per locale (key-value pairs)
- Context/description

**Use Cases**:
- UI text translations
- Multi-language labels
- Localized messages

### 15. Unknown Object

**Fallback Parser**: Handles any unrecognized object type

**Key Fields Extracted**:
- Raw XML (preserved for debugging)
- Basic metadata (UUID, name if available)

**Use Cases**:
- Future Appian object types
- Custom/plugin object types
- Debugging parsing issues

---

## Architecture Deep Dive

### Core Components

#### 1. PackageReader

**Responsibility**: Extract ZIP and discover files

**Location**: `appian_parser/package_reader.py`

**Key Methods**:
```python
def read(zip_path: str) -> PackageContents:
    """Extract ZIP to temp directory and discover XML/XSD files."""
    
def cleanup(temp_dir: str) -> None:
    """Remove temporary extraction directory."""
```

**PackageContents** (dataclass):
```python
@dataclass
class PackageContents:
    temp_dir: str              # Temporary extraction directory
    zip_filename: str          # Original ZIP filename
    total_files: int           # Total files in ZIP
    xml_files: list[str]       # Paths to all XML files
    properties_files: list[str] # Paths to .properties files (for translations)
```

**Implementation Details**:
- Uses `zipfile.ZipFile` from stdlib
- Extracts to `tempfile.mkdtemp()` for isolation
- Filters for `.xml` and `.xsd` extensions
- Handles nested directory structures
- Cleanup is caller's responsibility (try/finally pattern)

---

#### 2. TypeDetector

**Responsibility**: Determine object type from XML root tag

**Location**: `appian_parser/type_detector.py`

**Key Methods**:
```python
def detect(xml_file: str) -> TypeDetection:
    """Detect object type from XML root tag."""
```

**TypeDetection** (dataclass):
```python
@dataclass
class TypeDetection:
    xml_tag: str           # Raw XML root tag (e.g., "interfaceHaul")
    mapped_type: str       # Internal type name (e.g., "Interface")
    is_excluded: bool      # True if type is in exclusion list
    is_unknown: bool       # True if type not recognized
```

**Tag Mapping**:
```python
TAG_TO_TYPE = {
    'interfaceHaul': 'Interface',
    'expressionRuleHaul': 'Expression Rule',
    'processModelHaul': 'Process Model',
    'recordTypeHaul': 'Record Type',
    'dataTypeHaul': 'CDT',
    'integrationHaul': 'Integration',
    'webApiHaul': 'Web API',
    'siteHaul': 'Site',
    'groupHaul': 'Group',
    'constantHaul': 'Constant',
    'connectedSystemHaul': 'Connected System',
    'controlPanelHaul': 'Control Panel',
    'translationSetHaul': 'Translation Set',
    'translationStringHaul': 'Translation String',
}
```

**Special Cases**:
- `<contentHaul>` wrapper: Inspects child element for actual type
- Unknown tags: Returns `is_unknown=True`, uses `UnknownObjectParser`

---

#### 3. ParserRegistry

**Responsibility**: Route object type to appropriate parser

**Location**: `appian_parser/parser_registry.py`

**Key Methods**:
```python
def get_parser(object_type: str) -> BaseParser:
    """Get parser instance for object type."""
    
def get_supported_types() -> list[str]:
    """List all supported object types."""
```

**Parser Mapping**:
```python
PARSER_MAP = {
    'Interface': InterfaceParser,
    'Expression Rule': ExpressionRuleParser,
    'Process Model': ProcessModelParser,
    'Record Type': RecordTypeParser,
    'CDT': CDTParser,
    'Integration': IntegrationParser,
    'Web API': WebAPIParser,
    'Site': SiteParser,
    'Group': GroupParser,
    'Constant': ConstantParser,
    'Connected System': ConnectedSystemParser,
    'Control Panel': ControlPanelParser,
    'Translation Set': TranslationSetParser,
    'Translation String': TranslationStringParser,
}
```

**Design Pattern**: Factory pattern with lazy instantiation

---

#### 4. BaseParser (Abstract Base Class)

**Responsibility**: Define parser interface

**Location**: `appian_parser/parsers/base_parser.py`

**Abstract Methods**:
```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, xml_file: str) -> dict:
        """Parse XML file and return structured dict."""
        pass
```

**Common Utilities** (provided by base class):
```python
def _parse_xml(self, xml_file: str) -> ET.Element:
    """Parse XML file and return root element."""
    
def _get_text(self, element: ET.Element, path: str, default: str = '') -> str:
    """Get text content from XML element via XPath."""
    
def _get_all(self, element: ET.Element, path: str) -> list[ET.Element]:
    """Get all matching elements via XPath."""
```

**All parsers extend this base class** and implement the `parse()` method.

---

#### 5. DiffHashService

**Responsibility**: Generate content hash for change detection

**Location**: `appian_parser/diff_hash.py`

**Key Methods**:
```python
@staticmethod
def generate_hash(data: dict) -> str:
    """Generate SHA-512 hash of object content."""
```

**Implementation**:
```python
def generate_hash(data: dict) -> str:
    # Serialize to JSON with sorted keys for consistency
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    
    # Generate SHA-512 hash
    hash_obj = hashlib.sha512(json_str.encode('utf-8'))
    
    return hash_obj.hexdigest()
```

**Use Cases**:
- Detect changes between package versions
- Deduplication
- Integrity verification

---

#### 6. ReferenceResolver

**Responsibility**: Coordinate reference resolution across all objects

**Location**: `appian_parser/resolution/reference_resolver.py`

**Key Methods**:
```python
def __init__(self, parsed_objects: list[ParsedObject], label_lookup: dict = None):
    """Build lookup caches from parsed objects."""
    
def resolve_all(self, parsed_objects: list[ParsedObject], locale: str = 'en-US') -> None:
    """Resolve all references in all objects (mutates in place)."""
```

**Architecture**:
```python
class ReferenceResolver:
    def __init__(self, parsed_objects, label_lookup=None):
        # Build lookup caches
        self.uuid_resolver = UUIDResolver(parsed_objects)
        self.rt_resolver = RecordTypeURNResolver(parsed_objects)
        self.translation_resolver = TranslationResolver(parsed_objects, locale)
        self.label_lookup = label_lookup or {}
    
    def resolve_all(self, parsed_objects, locale='en-US'):
        for obj in parsed_objects:
            # Get field paths for this object type
            paths = RESOLUTION_PATHS.get(obj.object_type, [])
            
            for path in paths:
                # Walk field path and resolve references
                self._walk_and_resolve(obj.data, path)
```

**Field Path Configuration** (`domain/constants.py`):
```python
RESOLUTION_PATHS = {
    'Interface': [
        'sail_code',
        'parameters.*.default_value',
        'test_inputs.*.value',
    ],
    'Expression Rule': [
        'sail_code',
        'inputs.*.default_value',
        'test_cases.*.inputs.*',
        'test_cases.*.expected_output',
    ],
    'Process Model': [
        'nodes.*.config.expression',
        'nodes.*.config.assignment',
        'flows.*.condition',
        'variables.*.default_value',
    ],
    # ... more types
}
```

---

#### 7. UUIDResolver

**Responsibility**: Resolve UUID references to rule!/cons!/type! format

**Location**: `appian_parser/resolution/uuid_resolver.py`

**Key Methods**:
```python
def resolve(self, text: str) -> str:
    """Resolve all UUID references in text."""
```

**Resolution Logic**:
```python
def resolve(self, text: str) -> str:
    def replace_uuid(match):
        uuid = match.group(1)
        canonical = extract_canonical_prefix(uuid)
        
        # Lookup by canonical prefix
        if canonical in self.uuid_lookup:
            obj_info = self.uuid_lookup[canonical]
            prefix = get_prefix(obj_info['type'])  # rule!, cons!, type!
            return f"{prefix}{obj_info['name']}"
        
        return match.group(0)  # Return original if not found
    
    return re.sub(UUID_PATTERN, replace_uuid, text)
```

**Prefix Mapping**:
```python
def get_prefix(object_type: str) -> str:
    if object_type == 'Expression Rule':
        return 'rule!'
    elif object_type == 'Constant':
        return 'cons!'
    elif object_type in ['CDT', 'Record Type']:
        return 'type!'
    else:
        return ''  # No prefix for other types
```

---

#### 8. RecordTypeURNResolver

**Responsibility**: Resolve Record Type URNs to recordType!Name.field format

**Location**: `appian_parser/resolution/record_type_resolver.py`

**Key Methods**:
```python
def resolve(self, text: str) -> str:
    """Resolve all RT URNs in text."""
```

**URN Format**:
```
urn:appian:record-field:v1:{record_type_uuid}/{field_uuid}
```

**Resolution Logic**:
```python
def resolve(self, text: str) -> str:
    def replace_urn(match):
        rt_uuid = match.group(1)
        field_uuid = match.group(2)
        
        # Lookup record type
        if rt_uuid in self.rt_lookup:
            rt_name = self.rt_lookup[rt_uuid]['name']
            
            # Lookup field
            if field_uuid in self.rt_lookup[rt_uuid]['fields']:
                field_name = self.rt_lookup[rt_uuid]['fields'][field_uuid]
                return f"recordType!{rt_name}.{field_name}"
        
        return match.group(0)  # Return original if not found
    
    return re.sub(RT_URN_PATTERN, replace_urn, text)
```

---

#### 9. TranslationResolver

**Responsibility**: Resolve Translation URNs to translated text

**Location**: `appian_parser/resolution/translation_resolver.py`

**Key Methods**:
```python
def resolve(self, text: str, locale: str = 'en-US') -> str:
    """Resolve all translation URNs in text."""
```

**URN Format**:
```
urn:appian:translation-string:v1:{translation_string_uuid}
```

**Resolution Logic**:
```python
def resolve(self, text: str, locale: str = 'en-US') -> str:
    def replace_urn(match):
        uuid = match.group(1)
        
        # Lookup translation
        if uuid in self.translation_lookup:
            translations = self.translation_lookup[uuid]
            
            # Try requested locale, fall back to default
            if locale in translations:
                return f'"{translations[locale]}"'
            elif 'en-US' in translations:
                return f'"{translations["en-US"]}"'
        
        return match.group(0)  # Return original if not found
    
    return re.sub(TRANSLATION_URN_PATTERN, replace_urn, text)
```

---

#### 10. DependencyAnalyzer

**Responsibility**: Extract inter-object dependencies

**Location**: `appian_parser/dependencies/analyzer.py`

**Key Methods**:
```python
def analyze(self, parsed_objects: list[ParsedObject]) -> list[Dependency]:
    """Extract all dependencies from parsed objects."""
```

**Dependency** (frozen dataclass):
```python
@dataclass(frozen=True)
class Dependency:
    source_uuid: str
    source_name: str
    source_type: str
    target_uuid: str
    target_name: str
    target_type: str
    dependency_type: str  # 'rule_call', 'interface_call', 'constant_ref', etc.
```

**Extraction Strategy**:
```python
def analyze(self, parsed_objects):
    dependencies = []
    
    for obj in parsed_objects:
        # Get field paths for this object type
        paths = DEPENDENCY_PATHS.get(obj.object_type, [])
        
        for path in paths:
            # Walk field path and extract references
            refs = self._extract_references(obj.data, path)
            
            for ref in refs:
                # Determine dependency type
                dep_type = self._classify_dependency(ref)
                
                dependencies.append(Dependency(
                    source_uuid=obj.uuid,
                    source_name=obj.name,
                    source_type=obj.object_type,
                    target_uuid=ref.uuid,
                    target_name=ref.name,
                    target_type=ref.type,
                    dependency_type=dep_type
                ))
    
    return dependencies
```

**Dependency Types**:
- `rule_call` - Expression rule invocation
- `interface_call` - Interface usage
- `constant_ref` - Constant reference
- `integration_call` - Integration invocation
- `subprocess_call` - Subprocess invocation
- `record_type_ref` - Record type reference
- `cdt_ref` - CDT reference

---

#### 11. BundleCoordinator

**Responsibility**: Orchestrate bundle generation

**Location**: `appian_parser/output/bundle_coordinator.py`

**Key Methods**:
```python
def build_all(self, parsed_objects, dependencies, output_dir) -> dict[str, list[str]]:
    """Build all bundles and return bundle assignments."""
    
def get_index_entries(self) -> list[dict]:
    """Get bundle index entries for app_overview.json."""
```

**Bundle Generation Flow**:
```python
def build_all(self, parsed_objects, dependencies, output_dir):
    # 1. Discover entry points
    entry_points = self._discover_entry_points(parsed_objects, dependencies)
    
    # 2. Build dependency graph
    dep_graph = self._build_graph(dependencies)
    
    # 3. For each entry point, generate bundle
    bundle_assignments = {}
    for entry in entry_points:
        # BFS traversal to collect all dependencies
        bundle_objects = self._bfs_traverse(entry, dep_graph, parsed_objects)
        
        # Build structure and code files
        structure = self.structure_builder.build(entry, bundle_objects, dep_graph)
        code = self.code_builder.build(bundle_objects)
        
        # Write to disk
        bundle_dir = os.path.join(output_dir, 'bundles', entry.name)
        os.makedirs(bundle_dir, exist_ok=True)
        
        with open(f"{bundle_dir}/structure.json", 'w') as f:
            json.dump(structure, f, indent=2)
        
        with open(f"{bundle_dir}/code.json", 'w') as f:
            json.dump(code, f, indent=2)
        
        # Track assignments
        for obj in bundle_objects:
            if obj.uuid not in bundle_assignments:
                bundle_assignments[obj.uuid] = []
            bundle_assignments[obj.uuid].append(entry.name)
    
    return bundle_assignments
```

---

### Data Flow Diagram

```
┌──────────────┐
│  ZIP File    │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  PackageReader.read()                                     │
│  • Extract to temp dir                                    │
│  • Return PackageContents                                 │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  For each XML file:                                       │
│                                                           │
│  1. TypeDetector.detect()                                 │
│     • Read XML root tag                                   │
│     • Map to object type                                  │
│     • Return TypeDetection                                │
│                                                           │
│  2. ParserRegistry.get_parser()                           │
│     • Get parser for type                                 │
│     • Return parser instance                              │
│                                                           │
│  3. Parser.parse()                                        │
│     • Extract structured data                             │
│     • Return dict                                         │
│                                                           │
│  4. DiffHashService.generate_hash()                       │
│     • Generate SHA-512 hash                               │
│     • Return hash string                                  │
│                                                           │
│  5. Create ParsedObject                                   │
│     • Wrap dict + metadata                                │
│     • Add to list                                         │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  ReferenceResolver.resolve_all()                          │
│  • Build lookup caches                                    │
│  • Walk field paths                                       │
│  • Resolve UUIDs, URNs                                    │
│  • Mutate objects in place                                │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  DependencyAnalyzer.analyze()                             │
│  • Extract dependencies                                   │
│  • Build dependency graph                                 │
│  • Return list of Dependency objects                      │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  Output Layer:                                            │
│                                                           │
│  1. BundleCoordinator.build_all()                         │
│     • Discover entry points                               │
│     • BFS traversal                                       │
│     • Write bundles/                                      │
│                                                           │
│  2. SearchIndexBuilder.build()                            │
│     • Build name lookup                                   │
│     • Write search_index.json                             │
│                                                           │
│  3. AppOverviewBuilder.build()                            │
│     • Aggregate metadata                                  │
│     • Write app_overview.json                             │
│                                                           │
│  4. ObjectDependencyWriter.write_all()                    │
│     • Write objects/<uuid>.json                           │
│                                                           │
│  5. OrphanWriter.write_all()                              │
│     • Write orphans/                                      │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  JSON Output │
└──────────────┘
```

---

## Module Reference

### Project Structure

```
appian_parser/
├── __init__.py                         # Package version
├── __main__.py                         # python -m entry point
├── cli.py                              # CLI orchestration
├── package_reader.py                   # ZIP extraction
├── type_detector.py                    # XML type detection
├── parser_registry.py                  # Parser factory/registry
├── diff_hash.py                        # SHA-512 content hashing
│
├── parsers/                            # 15 type-specific XML parsers
│   ├── __init__.py
│   ├── base_parser.py                  # Abstract base class (ABC)
│   ├── interface_parser.py
│   ├── expression_rule_parser.py
│   ├── process_model_parser.py
│   ├── record_type_parser.py
│   ├── cdt_parser.py
│   ├── integration_parser.py
│   ├── web_api_parser.py
│   ├── site_parser.py
│   ├── group_parser.py
│   ├── constant_parser.py
│   ├── connected_system_parser.py
│   ├── control_panel_parser.py
│   ├── translation_set_parser.py
│   ├── translation_string_parser.py
│   └── unknown_object_parser.py
│
├── resolution/                         # Reference resolution (in-memory)
│   ├── __init__.py
│   ├── reference_resolver.py           # Coordinator: builds caches, walks fields
│   ├── uuid_resolver.py                # UUID → rule!/cons!/type!
│   ├── record_type_resolver.py         # RT URN → recordType!Name.field
│   ├── translation_resolver.py         # Translation URN → translated text
│   ├── label_bundle_resolver.py        # .properties file resolution
│   └── uuid_utils.py                   # UUID format detection and extraction
│
├── dependencies/                       # Dependency extraction
│   ├── __init__.py
│   └── analyzer.py                     # Pattern-based dependency graph builder
│
├── domain/                             # Domain knowledge & shared config
│   ├── __init__.py
│   ├── constants.py                    # Shared regex patterns, field paths, type maps
│   ├── models.py                       # Data classes (ParsedObject, Dependency, etc.)
│   ├── enums.py                        # DependencyTypeEnum
│   ├── field_walker.py                 # Dotted field path walker utility
│   ├── appian_type_resolver.py         # XSD/Appian type name resolution
│   └── node_types/                     # Process model node type registry
│       ├── categories.py
│       └── registry.py
│
└── output/                             # JSON output generation
    ├── __init__.py
    ├── json_dumper.py                  # Legacy per-object JSON writer
    ├── manifest_builder.py             # Legacy manifest builder
    ├── bundle_coordinator.py           # Bundle generation orchestrator
    ├── bundle_structure_builder.py     # Builds structure.json
    ├── bundle_code_builder.py          # Builds code.json
    ├── bundle_summarizer.py            # Builds bundle summaries
    ├── search_index_builder.py         # Builds search_index.json
    ├── app_overview_builder.py         # Builds app_overview.json
    ├── object_dependency_writer.py     # Writes objects/<uuid>.json
    └── orphan_writer.py                # Writes orphans/
```

### Key Modules

#### `cli.py`

**Purpose**: CLI orchestration and main entry point

**Key Functions**:
- `dump_package()` - Main orchestration function
- `main()` - Argument parsing and command dispatch

**Usage**:
```python
from appian_parser.cli import dump_package
from appian_parser.domain.models import DumpOptions

options = DumpOptions(
    pretty=True,
    locale='en-US',
    include_dependencies=True,
    excluded_types={'Group'}
)

result = dump_package('MyApp.zip', './output', options)
print(f"Parsed {result.objects_parsed} objects")
```

#### `domain/constants.py`

**Purpose**: Centralized configuration for resolution and dependency analysis

**Key Constants**:
```python
# Regex patterns
UUID_FULL_RE = r'#"(_a-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:_[0-9]+)?)"'
RULE_REF_RE = r'rule!([A-Za-z0-9_]+)'
CONS_REF_RE = r'cons!([A-Za-z0-9_]+)'
RECORD_TYPE_REF_RE = r'recordType!([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?'

# Field paths for resolution
RESOLUTION_PATHS = {
    'Interface': ['sail_code', 'parameters.*.default_value'],
    'Expression Rule': ['sail_code', 'test_cases.*.inputs.*'],
    # ... more types
}

# Field paths for dependency extraction
DEPENDENCY_PATHS = {
    'Interface': ['sail_code'],
    'Expression Rule': ['sail_code'],
    'Process Model': ['nodes.*.config.expression', 'flows.*.condition'],
    # ... more types
}
```

#### `domain/models.py`

**Purpose**: Data classes for type safety

**Key Classes**:
```python
@dataclass
class ParsedObject:
    uuid: str
    name: str
    object_type: str
    data: dict
    diff_hash: str
    source_file: str

@dataclass(frozen=True)
class Dependency:
    source_uuid: str
    source_name: str
    source_type: str
    target_uuid: str
    target_name: str
    target_type: str
    dependency_type: str

@dataclass
class DumpOptions:
    pretty: bool = True
    locale: str = 'en-US'
    include_dependencies: bool = True
    excluded_types: set[str] | None = None

@dataclass
class DumpResult:
    total_files: int
    objects_parsed: int
    errors_count: int
    output_dir: str
```

#### `domain/field_walker.py`

**Purpose**: Walk nested dict structures using dotted paths

**Key Functions**:
```python
def walk_path(data: dict, path: str) -> list[Any]:
    """
    Walk a dotted path in nested dict/list structure.
    
    Examples:
        'sail_code' → data['sail_code']
        'parameters.*.default_value' → all parameter default values
        'nodes.*.config.expression' → all node expressions
    """
```

**Usage**:
```python
from appian_parser.domain.field_walker import walk_path

data = {
    'parameters': [
        {'name': 'input1', 'default_value': 'test'},
        {'name': 'input2', 'default_value': 'test2'}
    ]
}

values = walk_path(data, 'parameters.*.default_value')
# Returns: ['test', 'test2']
```

---

## Design Principles

### 1. Zero Runtime Dependencies

**Rationale**: Minimize installation complexity and security surface area

**Implementation**:
- All parsing uses `xml.etree.ElementTree` (stdlib)
- All regex uses `re` (stdlib)
- All JSON uses `json` (stdlib)
- All hashing uses `hashlib` (stdlib)
- All file operations use `os`, `shutil`, `tempfile` (stdlib)

**Trade-offs**:
- More verbose XML parsing (no lxml)
- Manual XPath implementation
- No external validation libraries

### 2. Single Responsibility Principle

**Rationale**: Each class has one job, making code easier to understand and test

**Examples**:
- `PackageReader` only extracts ZIPs
- `TypeDetector` only detects types
- `UUIDResolver` only resolves UUIDs
- `BundleCoordinator` only orchestrates (delegates to builders)

### 3. Open/Closed Principle

**Rationale**: Open for extension, closed for modification

**Implementation**:
- New object types = new parser class (no changes to existing code)
- All parsers extend `BaseParser` ABC
- `ParserRegistry` uses dict mapping (easy to extend)

**Example**:
```python
# Adding a new object type requires:
# 1. Create new parser
class NewTypeParser(BaseParser):
    def parse(self, xml_file: str) -> dict:
        # Implementation
        pass

# 2. Register in ParserRegistry
PARSER_MAP['New Type'] = NewTypeParser

# 3. Add tag mapping in TypeDetector
TAG_TO_TYPE['newTypeHaul'] = 'New Type'

# No changes to existing parsers or orchestration code
```

### 4. Declarative Configuration

**Rationale**: Field paths for resolution/analysis are data, not code

**Implementation**:
- `RESOLUTION_PATHS` dict in `constants.py`
- `DEPENDENCY_PATHS` dict in `constants.py`
- Easy to add new paths without changing resolver logic

**Example**:
```python
# Adding resolution for a new field:
RESOLUTION_PATHS['Interface'].append('new_field.*.nested_value')

# No code changes needed in ReferenceResolver
```

### 5. In-Memory Resolution

**Rationale**: No external dependencies, fast, deterministic

**Implementation**:
- All lookups built from parsed objects
- No database queries
- No API calls
- No file I/O during resolution

**Trade-offs**:
- Memory usage scales with package size
- Can't resolve cross-package references (by design)

### 6. Immutable Value Objects

**Rationale**: Prevent accidental mutation, enable safe sharing

**Implementation**:
- `Dependency` is a frozen dataclass
- `TypeDetection` is a frozen dataclass
- `PackageContents` is immutable after creation

**Example**:
```python
@dataclass(frozen=True)
class Dependency:
    source_uuid: str
    target_uuid: str
    # ... more fields

# This will raise FrozenInstanceError:
dep.source_uuid = 'new_value'  # ❌ Error
```

### 7. Mutation in Place (for Performance)

**Rationale**: Avoid copying large data structures

**Implementation**:
- `ReferenceResolver` mutates `ParsedObject.data` directly
- Saves memory and time (no deep copies)

**Trade-off**:
- Less functional, but pragmatic for large datasets

### 8. Fail Fast

**Rationale**: Catch errors early, provide clear messages

**Implementation**:
- Validate inputs at entry points
- Raise exceptions for invalid data
- Collect errors but continue parsing (don't fail entire package for one bad object)

**Example**:
```python
if not os.path.isfile(zip_path):
    raise FileNotFoundError(f"Package not found: {zip_path}")

if not parsed_data.get('uuid'):
    errors.append(ParseError(
        file=xml_file,
        error="Missing UUID",
        object_type=object_type
    ))
    continue  # Skip this object, continue with others
```

---

## Performance

### Benchmarks

Measured on MacBook Pro M1, 16GB RAM:

| Package | Objects | Dependencies | Parse Time | Memory Peak |
|---------|---------|--------------|------------|-------------|
| SourceSelection v2.8.0 | 2,461 | 5,234 | 1.88s | ~450MB |
| CaseManagementStudio | 3,184 | 6,892 | 2.34s | ~580MB |
| RequirementsManagement v2.3.0 | 3,494 | 7,123 | 2.67s | ~620MB |

### Performance Characteristics

**Time Complexity**:
- Parsing: O(n) where n = number of objects
- Resolution: O(n × m) where m = average field path depth
- Dependency analysis: O(n × p) where p = average pattern matches per object
- Bundle generation: O(b × d) where b = bundles, d = average dependency depth

**Space Complexity**:
- Parsed objects: O(n × s) where s = average object size
- Lookup caches: O(n)
- Dependency graph: O(e) where e = number of edges
- Bundle output: O(n) (each object appears in 1+ bundles)

### Optimization Strategies

1. **Lazy Loading**: Bundles split into structure + code files
2. **Canonical Prefix Matching**: O(1) UUID lookups via dict
3. **Compiled Regex**: Patterns compiled once, reused
4. **In-Place Mutation**: Avoid deep copies during resolution
5. **Streaming XML**: Parse one file at a time (no full DOM in memory)

### Bottlenecks

1. **Reference Resolution** (~40% of total time)
   - Regex matching on SAIL code
   - Mitigation: Compiled patterns, efficient string operations

2. **Bundle Generation** (~30% of total time)
   - BFS graph traversal
   - Mitigation: Efficient graph representation (dict of sets)

3. **JSON Serialization** (~20% of total time)
   - Writing large JSON files
   - Mitigation: `--no-pretty` flag for compact output

4. **XML Parsing** (~10% of total time)
   - ElementTree parsing
   - Mitigation: None (stdlib limitation)

---

## Testing

### Test Structure

```
tests/
├── conftest.py                         # Shared fixtures and sample XML
├── test_cli.py                         # End-to-end integration tests
├── test_package_reader.py
├── test_type_detector.py
├── test_diff_hash.py
├── test_field_walker.py
├── parsers/
│   ├── __init__.py
│   └── test_parsers.py                 # Tests for all 15 parsers
├── resolution/
│   ├── __init__.py
│   ├── test_uuid_resolver.py
│   ├── test_record_type_resolver.py
│   ├── test_translation_resolver.py
│   └── test_reference_resolver.py
└── dependencies/
    ├── __init__.py
    └── test_analyzer.py
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=appian_parser --cov-report=term-missing

# Run specific test module
python -m pytest tests/resolution/test_uuid_resolver.py -v

# Run specific test
python -m pytest tests/test_cli.py::test_dump_package -v
```

### Test Coverage

Core modules have high coverage:

| Module | Coverage |
|--------|----------|
| `reference_resolver.py` | 96% |
| `translation_resolver.py` | 100% |
| `uuid_resolver.py` | 89% |
| `record_type_resolver.py` | 73% |
| `field_walker.py` | 93% |
| `uuid_utils.py` | 96% |
| `package_reader.py` | 100% |
| `parser_registry.py` | 100% |
| `type_detector.py` | 93% |
| `manifest_builder.py` | 100% |
| `constants.py` | 94% |
| `diff_hash.py` | 100% |

### Test Fixtures

**Sample XML** (`conftest.py`):
```python
@pytest.fixture
def sample_interface_xml():
    return '''<?xml version="1.0" encoding="UTF-8"?>
    <interfaceHaul>
      <uuid>_a-0006eed1-0f7f-8000-0020-7f0000014e7a</uuid>
      <name>AS_GSS_IF_TestInterface</name>
      <sailCode>a!textField(label: "Test", value: ri!input)</sailCode>
    </interfaceHaul>'''

@pytest.fixture
def sample_parsed_objects():
    return [
        ParsedObject(
            uuid='_a-0001',
            name='TestRule',
            object_type='Expression Rule',
            data={'sail_code': 'rule!OtherRule()'},
            diff_hash='abc123',
            source_file='test.xml'
        ),
        ParsedObject(
            uuid='_a-0002',
            name='OtherRule',
            object_type='Expression Rule',
            data={'sail_code': '1 + 1'},
            diff_hash='def456',
            source_file='test2.xml'
        )
    ]
```

### Integration Tests

**End-to-End Test** (`test_cli.py`):
```python
def test_dump_package_integration(tmp_path):
    # Create test ZIP with sample XML
    zip_path = create_test_package(tmp_path)
    output_dir = tmp_path / 'output'
    
    # Run parser
    options = DumpOptions(pretty=True, include_dependencies=True)
    result = dump_package(str(zip_path), str(output_dir), options)
    
    # Verify output
    assert result.objects_parsed > 0
    assert (output_dir / 'app_overview.json').exists()
    assert (output_dir / 'search_index.json').exists()
    assert (output_dir / 'bundles').exists()
```

---

## Development Workflow

### Setting Up Development Environment

```bash
# Clone repository
git clone https://gitlab.appian-stratus.com/ramaswamy.u/appian-parser.git
cd appian-parser

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install pytest pytest-cov

# Verify setup
python -m appian_parser types
```

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make changes** following design principles

3. **Add tests** for new functionality

4. **Run tests**:
   ```bash
   python -m pytest tests/ -v
   ```

5. **Check coverage**:
   ```bash
   python -m pytest tests/ --cov=appian_parser --cov-report=html
   open htmlcov/index.html
   ```

6. **Commit changes**:
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

### Adding a New Object Type

**Step 1**: Create parser in `appian_parser/parsers/`:

```python
# new_type_parser.py
from appian_parser.parsers.base_parser import BaseParser

class NewTypeParser(BaseParser):
    def parse(self, xml_file: str) -> dict:
        root = self._parse_xml(xml_file)
        
        return {
            'uuid': self._get_text(root, 'uuid'),
            'name': self._get_text(root, 'name'),
            'description': self._get_text(root, 'description'),
            # ... extract other fields
        }
```

**Step 2**: Register in `parser_registry.py`:

```python
from appian_parser.parsers.new_type_parser import NewTypeParser

PARSER_MAP = {
    # ... existing parsers
    'New Type': NewTypeParser,
}
```

**Step 3**: Add tag mapping in `type_detector.py`:

```python
TAG_TO_TYPE = {
    # ... existing mappings
    'newTypeHaul': 'New Type',
}
```

**Step 4**: Add resolution paths in `domain/constants.py`:

```python
RESOLUTION_PATHS = {
    # ... existing paths
    'New Type': [
        'field_with_uuids',
        'nested.*.field',
    ],
}
```

**Step 5**: Add dependency paths in `domain/constants.py`:

```python
DEPENDENCY_PATHS = {
    # ... existing paths
    'New Type': [
        'field_with_references',
    ],
}
```

**Step 6**: Add tests in `tests/parsers/test_parsers.py`:

```python
def test_new_type_parser(sample_new_type_xml):
    parser = NewTypeParser()
    result = parser.parse(sample_new_type_xml)
    
    assert result['uuid'] == '_a-0001'
    assert result['name'] == 'TestNewType'
```

### Debugging Tips

**Enable verbose logging**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Inspect parsed objects**:
```python
for obj in parsed_objects:
    if obj.name == 'TargetObject':
        print(json.dumps(obj.data, indent=2))
```

**Test resolution on specific object**:
```python
resolver = ReferenceResolver(parsed_objects)
test_obj = next(o for o in parsed_objects if o.name == 'TestRule')
resolver.resolve_all([test_obj])
print(test_obj.data['sail_code'])
```

**Validate bundle generation**:
```python
coordinator = BundleCoordinator()
bundle_assignments = coordinator.build_all(parsed_objects, dependencies, './debug_output')
print(f"Generated {len(bundle_assignments)} bundles")
```

---

## Contributing

### Code Style

- Follow PEP 8
- Use type hints for all function signatures
- Document public APIs with docstrings
- Keep functions small and focused
- Prefer composition over inheritance

### Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Ensure all tests pass
5. Update documentation if needed
6. Submit pull request with clear description

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions/changes
- `refactor`: Code refactoring
- `perf`: Performance improvements

**Example**:
```
feat: Add support for Custom Function object type

- Created CustomFunctionParser
- Added tag mapping in TypeDetector
- Added resolution and dependency paths
- Added tests with 95% coverage

Closes #42
```

---

## License

Internal use only. Not licensed for external distribution.

---

## Contact

For questions or issues, contact the GAM Appian Knowledge Base team.

