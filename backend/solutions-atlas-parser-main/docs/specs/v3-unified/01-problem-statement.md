# 01 — Problem Statement

## What the System Does Today

The Appian Parser takes an Appian application package (a ZIP file containing thousands of XML/XSD files) and converts it into structured JSON that AI assistants can query through an MCP server. The pipeline is:

```
ZIP → Parse XML → Resolve References → Analyze Dependencies → Write JSON Files
```

The output is a flat directory of JSON files: an app overview, a search index, per-object dependency files, self-contained bundle files (grouping objects into functional flows), and orphan files for unreachable objects.

This system works. It successfully parses applications with 2,500+ objects in under 2 seconds and produces output that the MCP server can query. But it has three fundamental limitations that prevent it from scaling to production use across multiple application releases.

---

## The Three Limitations

### Limitation 1: The System Is Stateless

Every parse is a complete replacement. The parser takes a ZIP, produces output, and writes it to a directory. If you parse the same application again tomorrow, the entire output is overwritten. There is no memory of what came before.

This means:

- **No change visibility.** When a new release is parsed, all previous data is gone. There is no way to know what changed between releases.
- **No impact analysis.** Cannot answer "which bundles were affected by the 2.0 release?" or "what objects changed in the last 3 releases?"
- **No object history.** Cannot answer "how has this expression rule evolved over time?" or "when was this object first introduced?"
- **No regression detection.** Cannot compare bundle structures across releases to detect unintended dependency changes.
- **Wasted re-processing.** Every parse processes all ~2,500 objects even though only ~100-300 typically change between releases.

Appian applications go through frequent releases. A typical application like GSS (Government Source Selection) might have releases every sprint — `25.04.01.00.00`, `25.04.02.09.00`, `25.04.03.00.00`. Each release modifies a subset of objects (typically 5-15% of the total). Without versioning, every parse throws away all context about what changed and why.

### Limitation 2: The System Is Redundant

The bundle system — which groups objects into self-contained functional flows — is the core innovation of this parser. But bundles today embed full object data inline. Every bundle file contains a complete copy of every object's metadata (name, description, parameters, calls, called_by) within its `structure.json`, and a complete copy of every object's SAIL code within its `code.json`.

An expression rule called by 50 bundles has its data copied 50 times across 50 `structure.json` files and its code copied 50 times across 50 `code.json` files.

This causes:

- **Large output directories.** Unnecessary disk usage from duplicated data.
- **Inconsistency risk.** If any post-processing modifies one copy but not others, the data diverges.
- **No single source of truth.** To get the definitive version of an object, you have to know which file to look in. The `objects/<uuid>.json` files exist but contain only dependency data — not the full object metadata that bundles embed.
- **Bloated git commits.** When the output is committed to a git repository (as it is in the KB repo), every bundle file that contains a changed object gets modified, even if the bundle structure itself didn't change.

### Limitation 3: The System Is Flat

The output is a collection of independent JSON files with no graph-level structure. The MCP server can answer object-level questions ("what does this rule call?") and bundle-level questions ("show me this bundle"), but it cannot answer graph-level questions without loading and stitching together dozens of files:

- "What is the dependency path between object A and object B?"
- "What are the top 20 most-depended-on objects across the whole app?"
- "What does process model X transitively touch, up to 3 hops?"
- "Which objects are shared across more than 10 bundles?"
- "What are the main functional areas of this application?"

These questions require a graph — a single structure where every object is a node and every dependency is an edge. Today, that graph exists only transiently in memory during the parse. It is never persisted.

Additionally, the daily pipeline that keeps the KB repo up to date downloads the entire application package (~10MB) every day, even when only 3 objects changed (~50KB of actual delta). It then re-parses all ~2,500 objects, deletes the entire output directory, and replaces it with fresh output. With 12 applications, that's ~30,000 file replacements per git commit, even when almost nothing changed.

---

## The Root Cause

These three limitations are symptoms of one missing concept: **the system has no persistent, structured data layer between the parser and the consumer.**

Today the parser directly writes the query-facing files. There is no intermediate layer that:
- Organizes data to eliminate duplication
- Maintains state across parses for versioning and delta processing
- Provides graph-level structure for efficient querying
- Separates what changes frequently (code) from what changes rarely (structure)

The parser and the MCP server are directly coupled through the file format. Every change to how data is organized requires changes to both the parser (writer) and the MCP server (reader).

---

## What the System Needs to Become

The system needs a **data layer** — a well-defined on-disk data model that sits between the parser and the MCP server. This data layer must satisfy six requirements:

### R1: Single Source of Truth

Every object's metadata and code must exist in exactly one canonical location. Bundles, the graph, the search index, and any other view must reference objects — never copy them.

### R2: Separation of Structure and Code

Object metadata (name, type, description, parameters, dependencies) must be separated from SAIL code. Metadata is small and loaded frequently. Code is large and loaded on demand. Mixing them forces the MCP server to load large payloads when it only needs a name lookup.

### R3: First-Class Dependency Graph

The complete dependency graph (every object as a node, every dependency as a typed edge) must be persisted as a single file. This enables graph-level queries (shortest path, transitive dependencies, hub detection) without stitching together individual object files.

### R4: Version Awareness

The data layer must track which release each object belongs to, what changed between releases, and preserve historical versions of changed objects. The current (latest) state must be the fast default path — historical queries can tolerate extra lookups.

### R5: Delta-Friendly

The data layer must support merging a small set of changed objects into the existing state without re-downloading or re-parsing the full application. It must persist enough state to reconstruct the full object set from a previous parse.

### R6: Minimal Write Footprint

When only 3 objects changed, only the files affected by those 3 objects should be written to disk. This minimizes git commit size and makes change tracking meaningful.

---

## The Three-Layer Architecture

The solution is to restructure the system into three distinct layers:

```
┌─────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                       │
│                                                          │
│  Accepts full ZIPs or delta ZIPs                        │
│  Parses XML → structured objects                        │
│  Merges deltas into existing state                      │
│  Detects version changes                                │
│                                                          │
│  Input:  ZIP file (full or delta)                       │
│  Output: Complete set of ParsedObjects in memory        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                            │
│                                                          │
│  Single source of truth for all object data             │
│  Owns the dependency graph                              │
│  Owns version history and release tracking              │
│  Owns bundle membership                                 │
│  Deduplicates — each object stored exactly once         │
│                                                          │
│  Persisted as structured files on disk                  │
│  Organized for both human readability and machine query │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    QUERY LAYER                           │
│                                                          │
│  MCP server reads from the data layer                   │
│  Answers object, bundle, graph, and version questions   │
│  Loads lazily — structure first, code on demand         │
│  Works across releases                                  │
└─────────────────────────────────────────────────────────┘
```

### Ingestion Layer

The ingestion layer is responsible for getting objects into the system. It supports two modes:

- **Full parse**: Parse an entire ZIP file from scratch. Used for initial setup, re-baseline, or recovery.
- **Delta parse**: Parse a small delta ZIP (only changed objects), merge into existing state, and re-run the transform pipeline. Used for daily updates.

The core transform pipeline (reference resolution → dependency analysis → enrichment) is identical in both modes. The difference is only in how the input object set is assembled.

### Data Layer

The data layer is the on-disk data model. It defines where every piece of data lives, how it's organized, and how different files reference each other. It is the subject of [02-data-layer.md](./02-data-layer.md).

Key properties:
- Objects stored once, referenced everywhere
- Code separated from metadata
- Graph persisted as a first-class artifact
- Version history layered on top of current state
- A manifest serves as the master index

### Query Layer

The query layer is the MCP server. It reads from the data layer and exposes tools for AI assistants. The new data layer enables a much richer query surface:

- **Object queries**: metadata, code, dependencies (existing, enhanced)
- **Bundle queries**: structure and member objects (existing, restructured)
- **Graph queries**: shortest path, transitive dependencies, hub detection (new)
- **Version queries**: release history, changelogs, object history, cross-release comparison (new)

---

## Scope Boundaries

### What IS Changing

- On-disk output structure (flat → layered data model)
- Bundle format (embedded data → UUID references)
- New output artifacts (graph, manifest, parsed state)
- CLI (new delta command, new versioning flags)
- MCP server tools (new graph and version tools, enhanced existing tools)
- Daily pipeline (delta downloads, smart writes)

### What Is NOT Changing

- All 15 XML parsers — no changes to how XML is parsed
- `ReferenceResolver` and sub-resolvers — no changes to reference resolution
- `DependencyAnalyzer` — no changes to dependency extraction
- `Enricher` — no changes to enrichment logic
- `DiffHashService` — no changes to content hashing
- `PackageReader`, `TypeDetector`, `ParserRegistry` — no changes
- The core transform pipeline (resolve → analyze → enrich) — identical in all modes

The changes are entirely in how the input is acquired (adding delta merge) and how the output is organized and written (the data layer).

---

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| Zero duplication | No full object data appears in more than one file. Lightweight identity references (`{uuid, name, type}`) in bundle `members` arrays are acceptable denormalization for query performance. History snapshots are excluded from this criterion. |
| Sub-3-second parse | Full parse of 2,500 objects completes in under 3 seconds |
| Minimal git footprint | Delta parse of 3 changed objects produces < 30 changed files |
| Graph queries | Shortest path and transitive dependency queries respond in < 100ms |
| Version queries | Changelog and object history queries respond in < 200ms |
| Backward compatible | Legacy flat output mode (`dump <zip> <dir>`) continues to work |
| Zero runtime dependencies | No new external packages required |
