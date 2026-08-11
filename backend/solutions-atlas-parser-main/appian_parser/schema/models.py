"""Data models for the schema module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Column:
    """Represents a database column."""

    name: str
    data_type: str
    nullable: bool = True
    default: str | None = None
    auto_increment: bool = False
    comment: str | None = None


@dataclass
class ForeignKey:
    """Represents a foreign key constraint."""

    name: str
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    """Represents a database table."""

    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    comment: str | None = None


ReferenceDataRow = dict[str, Any]


@dataclass
class SchemaResult:
    """Final output of schema analysis."""

    tables: dict[str, Table]
    relationships: list[dict[str, Any]]
    reference_data: dict[str, list[ReferenceDataRow]]
    insertion_order: list[str]
    table_classification: dict[str, str]
    summary: dict[str, Any]

    def tables_as_dict(self) -> dict[str, Any]:
        """Serialize tables to JSON-compatible dict."""
        result = {}
        for name, table in self.tables.items():
            result[name] = {
                "columns": {
                    col.name: {
                        "type": col.data_type,
                        "nullable": col.nullable,
                        **({"default": col.default} if col.default else {}),
                        **({"auto_increment": True} if col.auto_increment else {}),
                        **({"comment": col.comment} if col.comment else {}),
                    }
                    for col in table.columns.values()
                },
                "primary_key": table.primary_key,
                **({"comment": table.comment} if table.comment else {}),
            }
        return result
