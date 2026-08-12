"""Orchestrates schema extraction from a package directory."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .ddl_replay_engine import DDLReplayEngine
from .models import SchemaResult, Table
from .script_finder import ScriptFinder
from .statement_parser import StatementParser


class SchemaBuilder:
    """Builds a complete schema result from an extracted package directory."""

    def build(self, package_root: Path) -> SchemaResult | None:
        """Build schema from package root directory.

        Returns None if no SQL scripts are found.
        """
        scripts = ScriptFinder().find_scripts(package_root)
        if not scripts:
            return None

        parser = StatementParser()
        engine = DDLReplayEngine()

        for script in scripts:
            content = script.read_text(encoding="utf-8", errors="replace")
            statements = parser.parse(content)
            engine.replay(statements)

        tables = engine.get_tables()
        ref_data = engine.get_reference_data()
        relationships = self._build_relationships(tables)
        insertion_order = self._topological_sort(tables)
        classification = {name: self._classify(name, name in ref_data) for name in tables}
        summary = self._build_summary(tables, classification, ref_data)

        return SchemaResult(
            tables=tables,
            relationships=relationships,
            reference_data=ref_data,
            insertion_order=insertion_order,
            table_classification=classification,
            summary=summary,
        )

    def _build_relationships(self, tables: dict[str, Table]) -> list[dict[str, Any]]:
        """Extract relationships from foreign keys."""
        rels: list[dict[str, Any]] = []
        for table in tables.values():
            for fk in table.foreign_keys:
                rels.append({
                    "from_table": table.name,
                    "to_table": fk.ref_table,
                    "constraint": fk.name,
                    "columns": fk.columns,
                    "ref_columns": fk.ref_columns,
                })
        return rels

    def _topological_sort(self, tables: dict[str, Table]) -> list[str]:
        """Kahn's algorithm for topological ordering based on FK dependencies."""
        graph: dict[str, set[str]] = defaultdict(set)
        in_degree: dict[str, int] = {name: 0 for name in tables}

        for table in tables.values():
            for fk in table.foreign_keys:
                if fk.ref_table in tables and fk.ref_table != table.name:
                    graph[fk.ref_table].add(table.name)
                    in_degree[table.name] = in_degree.get(table.name, 0) + 1

        queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in sorted(graph[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Append any remaining (cycles) in sorted order
        remaining = sorted(set(tables) - set(result))
        result.extend(remaining)
        return result

    def _classify(self, name: str, has_reference_data: bool = False) -> str:
        """Classify a table by naming convention and data presence."""
        upper = name.upper()
        if "SCRIPTEXECUTION" in upper:
            return "framework"
        if "_A_R_" in upper or "_AUDIT" in upper:
            return "audit"
        if "_R_" in upper or has_reference_data:
            return "reference"
        if "_TMG_" in upper:
            return "task_management"
        return "business"

    def _build_summary(
        self,
        tables: dict[str, Table],
        classification: dict[str, str],
        ref_data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Build summary statistics."""
        counts: dict[str, int] = defaultdict(int)
        for cat in classification.values():
            counts[cat] += 1
        return {
            "total_tables": len(tables),
            "tables_by_category": dict(counts),
            "total_columns": sum(len(t.columns) for t in tables.values()),
            "total_foreign_keys": sum(len(t.foreign_keys) for t in tables.values()),
            "reference_data_tables": len(ref_data),
            "reference_data_rows": sum(len(rows) for rows in ref_data.values()),
        }
