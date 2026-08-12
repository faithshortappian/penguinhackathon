"""Finds SQL scripts in an extracted package directory."""
from __future__ import annotations

from pathlib import Path


class ScriptFinder:
    """Locates SQL migration scripts within a package directory tree."""

    def find_scripts(self, package_root: Path) -> list[Path]:
        """Find .sql files in the scripts/ folder, sorted by filename.

        Searches at root level and one level deep. Ignores oracle-scripts/
        and postgres-scripts/ folders.
        """
        scripts_dir = self._find_scripts_dir(package_root)
        if scripts_dir is None:
            return []
        return sorted(
            (f for f in scripts_dir.iterdir() if f.suffix.lower() == ".sql"),
            key=lambda p: p.name,
        )

    def _find_scripts_dir(self, root: Path) -> Path | None:
        """Locate the scripts/ directory at root or one level deep."""
        candidate = root / "scripts"
        if candidate.is_dir():
            return candidate
        for child in root.iterdir():
            if child.is_dir() and child.name not in ("oracle-scripts", "postgres-scripts"):
                candidate = child / "scripts"
                if candidate.is_dir():
                    return candidate
        return None
