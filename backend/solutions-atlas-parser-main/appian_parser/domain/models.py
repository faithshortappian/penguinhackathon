"""Shared data models used across parser modules."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedObject:
    """A parsed Appian object with metadata."""

    uuid: str
    name: str
    object_type: str
    data: dict[str, Any]
    diff_hash: str | None = None
    source_file: str = ''


@dataclass
class ParseError:
    """A parsing error for a single file."""

    file: str
    error: str
    object_type: str = 'Unknown'


@dataclass
class DumpOptions:
    """Options controlling the dump output."""

    excluded_types: set[str] = field(default_factory=set)
    include_raw_xml: bool = False
    include_dependencies: bool = True
    include_enrichment: bool = True
    locale: str = 'en-US'
    pretty: bool = True


@dataclass
class DumpOptions:
    """Options controlling the dump output."""

    excluded_types: set[str] = field(default_factory=set)
    include_raw_xml: bool = False
    include_dependencies: bool = True
    include_enrichment: bool = True
    locale: str = 'en-US'
    pretty: bool = True
    data_dir: str | None = None
    release_override: str | None = None


@dataclass
class DumpResult:
    """Result summary of a dump operation."""

    total_files: int
    objects_parsed: int
    errors_count: int
    output_dir: str


# --- V3 Data Layer Models ---

@dataclass
class MemberEntry:
    """Lightweight object reference in bundle members."""
    uuid: str
    name: str
    type: str

@dataclass
class DependencyEntry:
    """Dependency reference in object calls/called_by."""
    uuid: str
    name: str
    type: str
    dep_type: str

@dataclass
class VersionHistoryEntry:
    """Entry in an object's version_history array."""
    version: str
    status: str      # "added", "modified", "current"
    diff_hash: str

@dataclass
class WriteStats:
    """Statistics from a write operation."""
    files_written: int = 0
    files_skipped: int = 0
    files_deleted: int = 0

@dataclass
class BuildArtifacts:
    """Container for all artifacts produced by the build phase."""
    object_files: dict[str, dict] = field(default_factory=dict)
    code_files: dict[str, dict] = field(default_factory=dict)
    bundle_dicts: list[dict] = field(default_factory=list)
    bundle_assignments: dict[str, list[str]] = field(default_factory=dict)
    hub_uuids: set[str] = field(default_factory=set)
    graph: dict = field(default_factory=dict)
    search_index: dict = field(default_factory=dict)
    app_overview: dict = field(default_factory=dict)
    orphan_index: dict = field(default_factory=dict)
