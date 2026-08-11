"""Replays DDL statements to build schema state."""
from __future__ import annotations

import re
from typing import Any

from .models import Column, ForeignKey, Table


class DDLReplayEngine:
    """Replays SQL DDL statements to reconstruct database schema state."""

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}
        self._ref_data: dict[str, list[dict[str, Any]]] = {}
        self._rename_map: dict[str, str] = {}  # old -> new

    def replay(self, statements: list[str]) -> None:
        """Replay a list of DDL statements, mutating internal state."""
        for stmt in statements:
            s = stmt.strip()
            upper = s.upper()
            if upper.startswith("CREATE TABLE"):
                self._handle_create_table(s)
            elif upper.startswith("ALTER TABLE"):
                self._handle_alter_table(s)
            elif upper.startswith("DROP TABLE"):
                self._handle_drop_table(s)
            elif upper.startswith("INSERT INTO"):
                self._handle_insert(s)
            elif upper.startswith("UPDATE"):
                self._handle_update(s)

    def get_tables(self) -> dict[str, Table]:
        """Return the current table state."""
        return dict(self._tables)

    def get_reference_data(self) -> dict[str, list[dict[str, Any]]]:
        """Return reference data consolidated under final table names."""
        result: dict[str, list[dict[str, Any]]] = {}
        for name, rows in self._ref_data.items():
            final = self._resolve_name(name)
            result.setdefault(final, []).extend(rows)
        return result

    def _resolve_name(self, name: str) -> str:
        """Follow rename chain to get final table name."""
        seen: set[str] = set()
        while name in self._rename_map and name not in seen:
            seen.add(name)
            name = self._rename_map[name]
        return name

    def _resolve_table_name(self, name: str) -> str:
        """Resolve a referenced table name to its current name in _tables."""
        resolved = self._resolve_name(name)
        if resolved in self._tables:
            return resolved
        # Try case-insensitive
        for t in self._tables:
            if t.upper() == resolved.upper():
                return t
        return resolved

    def _unquote(self, name: str) -> str:
        """Remove backticks from identifier."""
        return name.strip().strip("`").strip('"').strip("'")

    def _handle_create_table(self, stmt: str) -> None:
        m = re.match(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?",
            stmt, re.IGNORECASE,
        )
        if not m:
            return
        name = m.group(1)
        # IF NOT EXISTS: skip if already exists
        if name in self._tables:
            return
        body_m = re.search(r"\((.*)\)", stmt, re.DOTALL)
        if not body_m:
            self._tables[name] = Table(name=name)
            return

        parts = self._split_top_level(body_m.group(1))
        columns: dict[str, Column] = {}
        pk: list[str] = []
        fks: list[ForeignKey] = []

        for part in parts:
            p = part.strip()
            upper_p = p.upper()
            if upper_p.startswith("PRIMARY KEY"):
                pk = self._extract_col_list(p)
            elif upper_p.startswith("CONSTRAINT") or upper_p.startswith("FOREIGN KEY"):
                fk = self._parse_fk(p)
                if fk:
                    fks.append(fk)
            elif upper_p.startswith("KEY") or upper_p.startswith("UNIQUE") or upper_p.startswith("INDEX"):
                continue
            else:
                col = self._parse_column_def(p)
                if col:
                    columns[col.name] = col
                    # Detect inline PRIMARY KEY
                    if "PRIMARY KEY" in upper_p:
                        pk = [col.name]
                    columns[col.name] = col

        comment = None
        cm = re.search(r"COMMENT\s*=\s*'([^']*)'", stmt, re.IGNORECASE)
        if cm:
            comment = cm.group(1)

        self._tables[name] = Table(
            name=name, columns=columns, primary_key=pk,
            foreign_keys=fks, comment=comment,
        )

    def _handle_alter_table(self, stmt: str) -> None:
        m = re.match(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?`?(\w+)`?", stmt, re.IGNORECASE)
        if not m:
            return
        raw_name = m.group(1)
        table_name = self._resolve_table_name(raw_name)
        rest = stmt[m.end():].strip()

        # Split multi-clause ALTER at top-level commas
        clauses = self._split_top_level(rest)
        for clause in clauses:
            self._process_alter_clause(table_name, clause.strip())

    def _process_alter_clause(self, table_name: str, clause: str) -> None:
        upper = clause.upper().strip()
        table = self._tables.get(table_name)

        if upper.startswith("RENAME TO") or upper.startswith("RENAME AS"):
            new_name = self._unquote(clause.split()[-1])
            if table:
                self._tables.pop(table_name)
                table.name = new_name
                self._tables[new_name] = table
            self._rename_map[table_name] = new_name
            return

        if re.match(r"RENAME\s+COLUMN", upper):
            m = re.match(r"RENAME\s+COLUMN\s+`?(\w+)`?\s+TO\s+`?(\w+)`?", clause, re.IGNORECASE)
            if m and table:
                old_col, new_col = m.group(1), m.group(2)
                if old_col in table.columns:
                    col = table.columns.pop(old_col)
                    col.name = new_col
                    table.columns[new_col] = col
            return

        if upper.startswith("RENAME INDEX") or upper.startswith("RENAME KEY"):
            return

        if upper.startswith("ADD COLUMN") or (upper.startswith("ADD") and not any(
            upper.startswith(f"ADD {kw}") for kw in
            ("CONSTRAINT", "FOREIGN", "KEY", "PRIMARY", "UNIQUE", "INDEX")
        )):
            col_def = re.sub(r"^ADD\s+(?:COLUMN\s+)?", "", clause, flags=re.IGNORECASE)
            col_def = re.sub(r"\s+AFTER\s+`?\w+`?", "", col_def, flags=re.IGNORECASE)
            col_def = re.sub(r"\s+FIRST\s*$", "", col_def, flags=re.IGNORECASE)
            col = self._parse_column_def(col_def.strip())
            if col and table:
                table.columns[col.name] = col
            return

        if upper.startswith("MODIFY COLUMN") or upper.startswith("MODIFY"):
            col_def = re.sub(r"^MODIFY\s+(?:COLUMN\s+)?", "", clause, flags=re.IGNORECASE)
            col = self._parse_column_def(col_def.strip())
            if col and table:
                table.columns[col.name] = col
            return

        if upper.startswith("DROP COLUMN"):
            m = re.match(r"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?`?(\w+)`?", clause, re.IGNORECASE)
            if m and table:
                table.columns.pop(m.group(1), None)
            return

        if upper.startswith("DROP FOREIGN KEY") or upper.startswith("DROP CONSTRAINT"):
            m = re.match(r"DROP\s+(?:FOREIGN\s+KEY|CONSTRAINT)\s+(?:IF\s+EXISTS\s+)?`?(\w+)`?", clause, re.IGNORECASE)
            if m and table:
                fk_name = m.group(1)
                table.foreign_keys = [fk for fk in table.foreign_keys if fk.name != fk_name]
            return

        if upper.startswith("ADD CONSTRAINT") or upper.startswith("ADD FOREIGN"):
            fk = self._parse_fk(clause)
            if fk and table:
                # Deduplicate by constraint name or column+ref_table
                existing = {(f.name, tuple(f.columns), f.ref_table) for f in table.foreign_keys}
                if (fk.name, tuple(fk.columns), fk.ref_table) not in existing:
                    table.foreign_keys.append(fk)
            return

    def _handle_drop_table(self, stmt: str) -> None:
        m = re.match(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?`?(\w+)`?", stmt, re.IGNORECASE)
        if m:
            name = self._resolve_table_name(m.group(1))
            self._tables.pop(name, None)

    def _handle_insert(self, stmt: str) -> None:
        m = re.match(r"INSERT\s+INTO\s+`?(\w+)`?\s*\(([^)]+)\)", stmt, re.IGNORECASE)
        if not m:
            return
        table_name = self._resolve_table_name(m.group(1))
        # Any table with INSERT statements is reference/config data
        # (transactional tables never have inserts in DDL scripts)
        if "ScriptExecution" in table_name:
            return
        cols = [self._unquote(c) for c in m.group(2).split(",")]
        values_section = stmt[m.end():]
        tuples = re.findall(r"\(([^)]*(?:'[^']*'[^)]*)*)\)", values_section)
        self._ref_data.setdefault(table_name, [])
        for tup in tuples:
            vals = self._parse_values(tup)
            row = dict(zip(cols, vals)) if len(vals) == len(cols) else dict(zip(cols, vals))
            self._ref_data[table_name].append(row)

    def _handle_update(self, stmt: str) -> None:
        m = re.match(r"UPDATE\s+`?(\w+)`?\s+SET\s+(.+?)(?:\s+WHERE\s+(.+))?$", stmt, re.IGNORECASE | re.DOTALL)
        if not m:
            return
        table_name = self._resolve_table_name(m.group(1))
        # Only update rows in tables we've already captured via INSERT
        if table_name not in self._ref_data:
            return

        set_clause = m.group(2)
        where_clause = m.group(3) or ""

        # Parse SET assignments
        updates: dict[str, str] = {}
        for pair in re.finditer(r"`?(\w+)`?\s*=\s*('(?:[^']*)'|\S+)", set_clause):
            updates[pair.group(1)] = pair.group(2).strip("'")

        # Parse WHERE conditions (simple equality)
        conditions: dict[str, str] = {}
        for cond in re.finditer(r"`?(\w+)`?\s*=\s*('(?:[^']*)'|\S+)", where_clause):
            conditions[cond.group(1)] = cond.group(2).strip("'")

        # Apply updates to matching rows
        for row in self._ref_data[table_name]:
            if all(row.get(k) == v for k, v in conditions.items()):
                row.update(updates)

    def _extract_col_list(self, text: str) -> list[str]:
        """Extract column names from a parenthesized list like PRIMARY KEY(`a`, `b`)."""
        m = re.search(r"\(([^)]+)\)", text)
        if not m:
            return []
        return [self._unquote(c) for c in m.group(1).split(",")]

    def _parse_fk(self, text: str) -> ForeignKey | None:
        """Parse a FOREIGN KEY constraint definition."""
        m = re.search(
            r"(?:CONSTRAINT\s+`?(\w+)`?\s+)?FOREIGN\s+KEY\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"\(([^)]+)\)\s+REFERENCES\s+`?(\w+)`?\s*\(([^)]+)\)",
            text, re.IGNORECASE,
        )
        if not m:
            return None
        name = m.group(1) or "unnamed_fk"
        cols = [self._unquote(c) for c in m.group(2).split(",")]
        ref_table = self._resolve_name(self._unquote(m.group(3)))
        ref_cols = [self._unquote(c) for c in m.group(4).split(",")]
        return ForeignKey(name=name, columns=cols, ref_table=ref_table, ref_columns=ref_cols)

    def _parse_column_def(self, text: str) -> Column | None:
        """Parse a column definition string."""
        # Match column name (with or without backticks)
        m = re.match(r"`?(\w+)`?\s+(.*)", text.strip(), re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        name = m.group(1)
        # Skip SQL keywords that aren't column names
        if name.upper() in ("PRIMARY", "KEY", "INDEX", "UNIQUE", "CONSTRAINT", "FOREIGN", "CHECK"):
            return None

        remainder = m.group(2).strip()

        # Extract type: first word possibly with parens, possibly with UNSIGNED
        type_m = re.match(r"(\w+(?:\s*\([^)]*\))?(?:\s+UNSIGNED)?)", remainder, re.IGNORECASE)
        if not type_m:
            return None
        data_type = type_m.group(1).strip()
        rest = remainder[type_m.end():].strip()

        rest_upper = rest.upper()
        nullable = "NOT NULL" not in rest_upper
        auto_increment = "AUTO_INCREMENT" in rest_upper
        default = None
        def_m = re.search(r"DEFAULT\s+('(?:[^']*)'|NULL|\S+)", rest, re.IGNORECASE)
        if def_m:
            val = def_m.group(1)
            default = val.strip("'") if val.upper() != "NULL" else None
        comment = None
        cm = re.search(r"COMMENT\s+['\"]([^'\"]*)['\"]", rest, re.IGNORECASE)
        if cm:
            comment = cm.group(1)

        return Column(name=name, data_type=data_type, nullable=nullable,
                      default=default, auto_increment=auto_increment, comment=comment)

    def _split_top_level(self, text: str) -> list[str]:
        """Split text on commas at parenthesis depth 0."""
        parts: list[str] = []
        current: list[str] = []
        depth = 0
        in_quote: str | None = None

        for ch in text:
            if in_quote:
                current.append(ch)
                if ch == in_quote:
                    in_quote = None
            elif ch in ("'", '"'):
                current.append(ch)
                in_quote = ch
            elif ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _parse_values(self, text: str) -> list[str]:
        """Parse a comma-separated value tuple respecting quoted strings."""
        values: list[str] = []
        current: list[str] = []
        in_quote: str | None = None

        for ch in text:
            if in_quote:
                current.append(ch)
                if ch == in_quote:
                    in_quote = None
            elif ch in ("'", '"'):
                current.append(ch)
                in_quote = ch
            elif ch == ",":
                values.append("".join(current).strip().strip("'"))
                current = []
            else:
                current.append(ch)
        if current:
            values.append("".join(current).strip().strip("'"))
        return values
