# Spec: Unified Data Layer, Versioning & Delta Pipeline

**Status**: Draft — under active design  
**Priority**: Critical — foundational restructuring  
**Scope**: Parser output structure, data organization, ingestion pipeline, MCP server query surface

---

## Document Index

| Document | Description |
|----------|-------------|
| [01-problem-statement.md](./01-problem-statement.md) | The single unified problem, current limitations, and what the system needs to become |
| [02-data-layer.md](./02-data-layer.md) | On-disk data model: file organization, schemas, deduplication strategy, separation of concerns |
| [03-ingestion-pipeline.md](./03-ingestion-pipeline.md) | How data enters the system: full parse, delta merge, version detection, smart writes |
| [04-versioning-and-history.md](./04-versioning-and-history.md) | Release tracking, changelogs, object history, snapshots, retention and pruning |
| [05-graph-and-query-surface.md](./05-graph-and-query-surface.md) | Dependency graph, hub detection, graph queries, and the full MCP server tool surface |

## Summary

This spec consolidates three previously separate enhancement proposals (Release Versioning, Delta Parsing, Dependency Graph & Deduplication) into a single unified architecture. The core insight is that all three problems stem from one missing concept: **the system has no persistent, structured data layer between the parser and the MCP server.**

Today the parser writes files and the MCP server reads files. There is no intermediate data model that organizes, deduplicates, versions, and indexes the data. Every file is a standalone island.

This spec introduces a **three-layer architecture** — Ingestion, Data, and Query — that solves all three problems through a single coherent design.

## Reading Order

Read the documents in order (01 → 05). Each builds on the previous.

## Relationship to Previous Specs

This spec supersedes all previous separate proposals (release-versioning, delta-parsing, spec-graph-and-deduplication), which have been removed. This document is the authoritative design going forward.
