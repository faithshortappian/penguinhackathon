# V3 Implementation Plan

Phased implementation of the unified data layer, versioning, delta pipeline, and MCP query surface.

## Phases

| Phase | Name | Description | Dependencies |
|-------|------|-------------|--------------|
| [Phase 1](./phase-1-data-layer-and-builders.md) | Data Layer & Builders | New file schemas, pure builders, refactored output pipeline | None |
| [Phase 2](./phase-2-legacy-writer-and-graph.md) | Legacy Writer & Graph | Legacy mode writer, graph export, CLI integration | Phase 1 |
| [Phase 3](./phase-3-versioned-mode.md) | Versioned Mode | Manifest, versioned writer, smart write, `--data-dir` flag | Phase 2 |
| [Phase 4](./phase-4-delta-and-versioning.md) | Delta Parse & Versioning | Delta command, parsed state, merge, history, changelogs | Phase 3 |
| [Phase 4B](./phase-4b-parser-validation.md) | Parser Validation | Exhaustive real-data validation — 63 checks across schemas, accuracy, versioning, delta, regression | Phase 4 |
| [Phase 5](./phase-5-mcp-server.md) | MCP Server | New and enhanced tools, graph queries, cache invalidation | Phase 4B (must pass all checks) |

## Principles

- Each phase produces a working, testable system
- Phase 1-2 replaces the current output with the new format (backward compatible via legacy mode)
- Phase 3-4 adds versioning and delta capabilities
- **Phase 4B is the gate** — nothing proceeds to Phase 5 until all 63 validation checks pass against real Appian packages
- Phase 5 is the MCP server
- Existing tests must pass at every phase boundary
- No runtime dependencies added at any phase

## Test Data

Real Appian packages in `test_files/source_selection_v1/`:
- `SourceSelectionv2.7.0 - FULL.zip` — baseline (2,649 files)
- `SourceSelectionv2.8.0 - FULL.zip` — second release (2,653 files)
- `SourceSelection-2.9.0-21 - Delta Package Compared with 2.8.0.zip` — delta (158 files)

## Estimated Effort

| Phase | New Files | Modified Files | Estimated LOC | Complexity |
|-------|-----------|---------------|---------------|------------|
| 1 | ~10 | ~5 | ~800 | Medium |
| 2 | ~3 | ~4 | ~500 | Medium |
| 3 | ~5 | ~3 | ~700 | High |
| 4 | ~6 | ~3 | ~900 | High |
| 4B | ~10 | ~0 | ~1500 | Medium |
| 5 | ~8 | ~4 | ~1200 | Medium |
| **Total** | **~42** | **~19** | **~5600** | |
