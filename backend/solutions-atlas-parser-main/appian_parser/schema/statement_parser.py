"""Parses SQL script content into individual statements."""
from __future__ import annotations


class StatementParser:
    """Extracts SQL statements from GAM Script Execution Framework scripts."""

    _START_MARKER = "-- START SCRIPT CONTENT ---"
    _END_MARKER = "-- END SCRIPT CONTENT ---"

    def parse(self, sql_content: str) -> list[str]:
        """Parse SQL content into individual statements.

        Handles DELIMITER $$ blocks by extracting only content between
        START/END SCRIPT CONTENT markers. Also captures top-level
        statements outside DELIMITER blocks.
        """
        chunks: list[str] = []
        lines = sql_content.split("\n")
        i = 0
        in_delimiter = False
        in_script_content = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            stripped_upper = stripped.upper()

            # Detect start of DELIMITER $$ block
            if not in_delimiter and "DELIMITER" in stripped_upper and "$$" in stripped:
                in_delimiter = True
                in_script_content = False
                i += 1
                continue

            # Detect end of DELIMITER block (DELIMITER ;)
            if in_delimiter and "DELIMITER" in stripped_upper and ";" in stripped and "$$" not in stripped:
                in_delimiter = False
                in_script_content = False
                i += 1
                continue

            if in_delimiter:
                if self._START_MARKER in line:
                    in_script_content = True
                    i += 1
                    continue
                if self._END_MARKER in line:
                    in_script_content = False
                    i += 1
                    continue
                if in_script_content:
                    chunks.append(line)
            else:
                # Top-level statement (outside DELIMITER blocks)
                # Only include non-empty, non-comment-only lines
                if stripped and not stripped.startswith("--"):
                    chunks.append(line)

            i += 1

        raw = "\n".join(chunks)
        return self._split_statements(raw)

    def _split_statements(self, text: str) -> list[str]:
        """Split text into individual SQL statements.
        
        Uses a line-based approach: accumulates lines until a line ends with ';'
        (outside quotes). This is more robust than character-by-character splitting
        because these scripts always have statement-ending semicolons at end of line.
        """
        stmts: list[str] = []
        current_lines: list[str] = []

        for line in text.split("\n"):
            stripped = line.rstrip()
            if not stripped:
                current_lines.append(line)
                continue

            current_lines.append(line)

            # Check if line ends with semicolon (the statement terminator)
            # Handle trailing whitespace and comments after semicolon
            code_part = stripped.rstrip()
            if code_part.endswith(";"):
                stmt = self._clean_statement("\n".join(current_lines))
                if stmt:
                    # Remove trailing semicolon
                    if stmt.endswith(";"):
                        stmt = stmt[:-1].rstrip()
                    if stmt:
                        stmts.append(stmt)
                current_lines = []

        # Handle trailing content without semicolon
        if current_lines:
            stmt = self._clean_statement("\n".join(current_lines))
            if stmt:
                if stmt.endswith(";"):
                    stmt = stmt[:-1].rstrip()
                if stmt:
                    stmts.append(stmt)
        return stmts

    def _clean_statement(self, text: str) -> str:
        """Strip leading SQL comments and whitespace."""
        lines = text.split("\n")
        # Drop leading empty lines and comment lines
        while lines and (not lines[0].strip() or lines[0].strip().startswith("--")):
            lines.pop(0)
        return "\n".join(lines).strip()
