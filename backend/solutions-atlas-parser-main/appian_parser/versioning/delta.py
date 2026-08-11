"""Delta merge and mode detection for versioned parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from appian_parser.domain.models import ParsedObject


class ParseMode(Enum):
    DAILY_UPDATE = "daily_update"
    NEW_RELEASE = "new_release"


@dataclass
class MergeResult:
    merged_objects: list[ParsedObject]
    modified_uuids: set[str] = field(default_factory=set)
    added_uuids: set[str] = field(default_factory=set)


class DeltaMerger:
    """Merges delta-parsed objects into existing state."""

    def merge(self, existing: list[ParsedObject], delta: list[ParsedObject]) -> MergeResult:
        existing_map = {obj.uuid: obj for obj in existing}
        modified, added = set(), set()

        for obj in delta:
            if obj.uuid in existing_map:
                if existing_map[obj.uuid].diff_hash != obj.diff_hash:
                    modified.add(obj.uuid)
                existing_map[obj.uuid] = obj
            else:
                added.add(obj.uuid)
                existing_map[obj.uuid] = obj

        return MergeResult(
            merged_objects=list(existing_map.values()),
            modified_uuids=modified,
            added_uuids=added,
        )


class ModeDetector:
    """Determines if a delta parse is a daily update or new release."""

    def detect(self, current_version: str, detected_version: str | None) -> ParseMode:
        if detected_version is None or detected_version == current_version:
            return ParseMode.DAILY_UPDATE
        return ParseMode.NEW_RELEASE
